"""
Monitoring / Recovery Agent — Supervisión de salud del sistema y recuperación automática.

Responsabilidades exclusivas:
- Polling de heartbeats (cada 30s)
- Detección de sagas estancadas (> 5min sin progreso)
- Gestión de circuit breakers (OPEN/HALF_OPEN/CLOSED)
- Requeue de mensajes dead-letter con exponential backoff
- Escalación a operador humano tras 3 fallos consecutivos
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone

import aio_pika
import httpx

from agents.base_agent import BaseAgent
from core.circuit_breaker import CircuitBreaker
from core.mcp.envelope import MCPEnvelope

logger = logging.getLogger(__name__)
DB_API_URL = os.environ.get("DB_API_URL", "http://api:8000")

ALL_AGENTS = [
    "orchestrator-agent", "sales-agent", "quotation-agent",
    "reservation-agent", "finance-agent", "document-agent",
    "validation-agent", "notification-agent",
]


class MonitoringAgent(BaseAgent):
    agent_id = "monitoring-agent"
    queue_name = "monitoring-events"
    system_prompt_file = "agents/monitoring/prompts/system_prompt.txt"

    def __init__(self) -> None:
        super().__init__()
        self._http = httpx.AsyncClient(base_url=DB_API_URL, timeout=30)
        self._recovery_attempts: dict[str, int] = {}

    def _register_handlers(self) -> None:
        self._consumer.register_handler("AgentDegraded", self.handle_message)
        self._consumer.register_handler("SagaCompensate", self._handle_saga_compensate)
        self._consumer.register_handler("DocumentFailed", self._handle_doc_failure)
        self._consumer.register_handler("ConflictResolved", self._handle_conflict_resolved)

    async def handle_message(self, envelope: MCPEnvelope) -> None:
        agent_id = envelope.payload.get("agent_id")
        logger.error(f"[Monitoring] Agente degradado: {agent_id}")
        await self._open_circuit_for(agent_id, envelope.saga_id)

    async def run(self) -> None:
        """Override: arranca tareas de monitoreo en paralelo."""
        await self.initialize()
        self._running = True
        logger.info("[Monitoring] Iniciando loops de supervisión...")

        await asyncio.gather(
            self._heartbeat_loop(),
            self._stale_saga_loop(),
            self._dead_letter_loop(),
            self._send_heartbeat(),
            asyncio.Future(),  # mantiene el loop
        )

    async def _heartbeat_loop(self) -> None:
        """Verifica heartbeats cada 30s. Dos fallos consecutivos → DEGRADED."""
        missed: dict[str, int] = {a: 0 for a in ALL_AGENTS}
        while self._running:
            heartbeats = await self._redis.get_all_heartbeats()
            for agent_id in ALL_AGENTS:
                hb = heartbeats.get(agent_id)
                if hb is None:
                    missed[agent_id] = missed.get(agent_id, 0) + 1
                    logger.warning(
                        f"[Monitoring] Heartbeat ausente: {agent_id} "
                        f"(#{missed[agent_id]})"
                    )
                    if missed[agent_id] >= 2:
                        await self._emit_degraded(agent_id)
                else:
                    missed[agent_id] = 0
            await asyncio.sleep(30)

    async def _stale_saga_loop(self) -> None:
        """Detecta sagas RUNNING sin progreso > 5min y las compensa."""
        while self._running:
            await asyncio.sleep(60)
            active_sagas = await self._http.get("/api/v1/sagas?status=RUNNING")
            if active_sagas.status_code != 200:
                continue
            for saga in active_sagas.json().get("sagas", []):
                saga_id = saga.get("saga_id") or saga.get("id")
                if await self._saga.is_stale(saga_id):
                    logger.warning(f"[Monitoring] Saga estancada detectada: {saga_id}")
                    await self._saga.fail_saga(saga_id, "Saga estancada (timeout 5min)")
                    await self.publish(
                        payload_type="SagaCompensated",
                        payload={"saga_id": saga_id, "reason": "timeout"},
                        receiver_agent="orchestrator-agent",
                        routing_key="orchestrator.saga_compensated",
                        saga_id=saga_id,
                    )

    async def _dead_letter_loop(self) -> None:
        """Reencola mensajes dead-letter con exponential backoff."""
        while self._running:
            await asyncio.sleep(120)
            # Se conecta a la dead-letter queue para requeue
            try:
                dlq_channel = await self._connection.channel()
                dlq_queue = await dlq_channel.declare_queue(
                    "dead-letter-queue", durable=True, passive=True
                )
                async with dlq_queue.iterator() as queue_iter:
                    count = 0
                    async for message in queue_iter:
                        if count >= 10:
                            break
                        await self._requeue_message(message)
                        count += 1
                await dlq_channel.close()
            except Exception as e:
                logger.warning(f"[Monitoring] Error procesando dead-letter: {e}")

    async def _requeue_message(
        self, message: aio_pika.abc.AbstractIncomingMessage
    ) -> None:
        try:
            body = json.loads(message.body)
            retry_count = body.get("retry_count", 0) + 1

            if retry_count > 3:
                logger.error(
                    f"[Monitoring] Mensaje descartado tras 3 reintentos: "
                    f"{body.get('message_id')}"
                )
                await message.ack()
                await self._escalate_to_human(body)
                return

            body["retry_count"] = retry_count
            backoff = min(2 ** retry_count, 32)
            await asyncio.sleep(backoff)

            # Republish al exchange original
            await self._publisher.publish_raw(
                routing_key=body.get("original_routing_key", "orchestrator.route"),
                payload=body,
                message_id=body.get("message_id"),
            )
            await message.ack()
            logger.info(
                f"[Monitoring] Mensaje reencolado (intento #{retry_count}): "
                f"{body.get('message_id')}"
            )
        except Exception as e:
            logger.error(f"[Monitoring] Error en requeue: {e}")
            await message.nack(requeue=False)

    async def _handle_saga_compensate(self, envelope: MCPEnvelope) -> None:
        saga_id = envelope.payload.get("saga_id")
        await self._saga.fail_saga(saga_id, "Compensación manual solicitada")
        logger.info(f"[Monitoring] Saga compensada: {saga_id}")

    async def _handle_conflict_resolved(self, envelope: MCPEnvelope) -> None:
        """Recibe la evaluación estructurada del Orchestrator (Fase 3, ver
        agents/orchestrator/agent.py::_handle_conflict) y ejecuta la escalación
        humana real cuando needs_escalation=True (baja confidence del
        conflict-validation-agent, o el conflict-monitoring-agent la pidió).
        Antes este evento se publicaba pero no tenía handler registrado."""
        payload = envelope.payload
        if not payload.get("needs_escalation"):
            logger.info(
                f"[Monitoring] Conflicto {payload.get('entity_id')} resuelto sin escalación "
                f"(confidence={payload.get('confidence')})"
            )
            return

        logger.warning(
            f"[Monitoring] Conflicto {payload.get('entity_id')} requiere escalación "
            f"(razón={payload.get('escalation_reason')}, confidence={payload.get('confidence')})"
        )
        await self._escalate_to_human(payload)

    async def _handle_doc_failure(self, envelope: MCPEnvelope) -> None:
        job_id = envelope.payload.get("job_id")
        attempts = self._recovery_attempts.get(job_id, 0) + 1
        self._recovery_attempts[job_id] = attempts

        if attempts > 3:
            await self._escalate_to_human(envelope.payload)
            return

        logger.warning(
            f"[Monitoring] DocumentJob fallido (intento #{attempts}): {job_id}"
        )

    async def _emit_degraded(self, agent_id: str) -> None:
        await self._redis.publish_realtime(
            "system:alerts",
            {
                "type": "AGENT_DEGRADED",
                "agent_id": agent_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    async def _open_circuit_for(self, agent_id: str, saga_id: str) -> None:
        cb = CircuitBreaker(agent_id, self._redis)
        await cb._transition_to("OPEN", {
            "failure_count": 5,
            "last_failure": datetime.now(timezone.utc).isoformat(),
        })

    async def _escalate_to_human(self, context: dict) -> None:
        logger.critical(
            f"[Monitoring] ESCALACIÓN A OPERADOR HUMANO: {context}"
        )
        await self._redis.publish_realtime(
            "system:alerts",
            {
                "type": "REQUIRES_MANUAL_INTERVENTION",
                "context": context,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )


if __name__ == "__main__":
    from core.logging_config import configure_logging
    configure_logging("monitoring-agent")
    agent = MonitoringAgent()
    asyncio.run(agent.run())
