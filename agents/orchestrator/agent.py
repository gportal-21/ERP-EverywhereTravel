"""
Orchestrator Agent — Punto de entrada único del sistema multiagente.

Responsabilidades exclusivas:
- Enrutamiento de tareas a dominios especializados
- Coordinación de Sagas distribuidas
- Resolución de conflictos entre agentes
- Circuit breaking global
- SLA monitoring
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone

import anthropic

from agents.base_agent import BaseAgent
from core.mcp.envelope import MCPEnvelope

logger = logging.getLogger(__name__)

ROUTING_TABLE = {
    "PackageInquiry":    ("sales-agent",       "sales.inquiry"),
    "PackageRequest":    ("quotation-agent",    "quotation.request"),
    "QuotationResult":   ("validation-agent",   "validation.check"),
    "ReservationCreate": ("reservation-agent",  "reservation.create"),
    "PaymentEvent":      ("finance-agent",      "finance.payment"),
    "DocumentRequest":   ("document-agent",     "document.generate"),
    "SagaCompensate":    ("monitoring-agent",   "monitoring.compensate"),
}


class OrchestratorAgent(BaseAgent):
    agent_id = "orchestrator-agent"
    queue_name = "orchestrator-commands"
    system_prompt_file = "agents/orchestrator/prompts/system_prompt.txt"

    def __init__(self) -> None:
        super().__init__()
        self._anthropic = anthropic.AsyncAnthropic(
            api_key=os.environ["ANTHROPIC_API_KEY"]
        )

    def _register_handlers(self) -> None:
        for payload_type in ROUTING_TABLE:
            self._consumer.register_handler(payload_type, self.handle_message)
        self._consumer.register_handler("ConflictNotification", self._handle_conflict)
        self._consumer.register_handler("AgentDegraded", self._handle_degraded_agent)

    async def handle_message(self, envelope: MCPEnvelope) -> None:
        logger.info(
            f"[Orchestrator] Recibido {envelope.payload_type} "
            f"saga={envelope.saga_id}"
        )

        # Iniciar o continuar saga
        saga = await self._saga.get_saga_status(envelope.saga_id)
        if not saga:
            await self._saga.start_saga(
                saga_type=envelope.payload_type,
                initiated_by=envelope.sender_agent,
                context=envelope.payload,
            )

        # Routing basado en payload_type
        route = ROUTING_TABLE.get(envelope.payload_type)
        if not route:
            logger.warning(
                f"[Orchestrator] Sin ruta para: {envelope.payload_type}"
            )
            return

        receiver_agent, routing_key = route

        # Verificar circuit breaker del agente destino
        cb_state = await self._circuit_breaker.get_state()
        if cb_state == "OPEN":
            await self._saga.record_step(
                envelope.saga_id, envelope.payload_type,
                self.agent_id, "BLOCKED",
                error="Circuit breaker OPEN"
            )
            logger.error(
                f"[Orchestrator] Circuit breaker OPEN para {receiver_agent}"
            )
            return

        # Publicar al agente destino
        reply = envelope.make_reply(
            payload_type=envelope.payload_type,
            payload=envelope.payload,
            receiver_agent=receiver_agent,
        )
        await self._publisher.publish(reply, routing_key)

        # Registrar paso en la saga
        await self._saga.record_step(
            saga_id=envelope.saga_id,
            step_name=f"route_to_{receiver_agent}",
            agent=self.agent_id,
            status="COMPLETED",
            output_ref=f"{routing_key}:{envelope.message_id}",
        )

        self._messages_processed += 1
        logger.info(
            f"[Orchestrator] Enrutado {envelope.payload_type} → "
            f"{receiver_agent} [saga={envelope.saga_id}]"
        )

    async def _handle_conflict(self, envelope: MCPEnvelope) -> None:
        """Resuelve conflictos entre agentes que modifican la misma entidad."""
        conflict = envelope.payload
        entity_id = conflict.get("entity_id")
        conflicting_agents = conflict.get("agents", [])

        logger.warning(
            f"[Orchestrator] CONFLICTO detectado en {entity_id} "
            f"por agentes: {conflicting_agents}"
        )

        # Usar Claude para analizar y resolver el conflicto
        resolution = await self._resolve_with_llm(conflict)

        # Notificar resolución
        await self.publish(
            payload_type="ConflictResolved",
            payload={
                "entity_id": entity_id,
                "resolution": resolution,
                "resolved_by": self.agent_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            receiver_agent="monitoring-agent",
            routing_key="monitoring.conflict_resolved",
            saga_id=envelope.saga_id,
        )

    async def _handle_degraded_agent(self, envelope: MCPEnvelope) -> None:
        agent_id = envelope.payload.get("agent_id")
        logger.error(f"[Orchestrator] Agente degradado: {agent_id}")
        # Abrir circuit breaker para ese agente
        await self._circuit_breaker._transition_to("OPEN", {
            "failure_count": 5,
            "last_failure": datetime.now(timezone.utc).isoformat(),
        })

    async def _resolve_with_llm(self, conflict: dict) -> str:
        """Delega la resolución de conflictos complejos a Claude."""
        response = await self._anthropic.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=256,
            system=self._system_prompt,
            messages=[{
                "role": "user",
                "content": (
                    f"Conflict detected: {conflict}. "
                    "Provide a brief resolution strategy in one sentence."
                )
            }]
        )
        return response.content[0].text


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    agent = OrchestratorAgent()
    asyncio.run(agent.run())
