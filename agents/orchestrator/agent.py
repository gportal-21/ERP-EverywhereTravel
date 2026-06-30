"""
Orchestrator Agent — Punto de entrada único del sistema multiagente.

MIGRACIÓN SWARMS — 3 FASES:

FASE 1 — swarms.Agent para resolución de conflictos:
  self._conflict_agent reemplaza self._anthropic.messages.create() en _resolve_with_llm()

FASE 2 — SequentialWorkflow para el pipeline de cotización:
  Sales → Quotation → Validation ejecutados en secuencia dentro del Orchestrator.
  Usado para PackageInquiry simples (paquetes del catálogo).
  Resultado llega en < 30s sin pasar por RabbitMQ hop por hop.

FASE 3 — AgentRearrange para routing dinámico en conflictos complejos:
  Cuando hay ConflictNotification, AgentRearrange decide dinámicamente
  si involucrar solo validation, solo monitoring, o ambos en cadena.

Flujo de decisión:
  PackageInquiry (paquete del catálogo)  → FASE 2: SequentialWorkflow (inline)
  PackageInquiry (paquete personalizado) → RabbitMQ: SalesAgent → QuotationAgent
  ConflictNotification                   → FASE 3: AgentRearrange
  Cualquier otro evento                  → ROUTING_TABLE (RabbitMQ)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
import httpx
from agents.swarms_compat import Agent, AgentRearrange, SequentialWorkflow

from agents.base_agent import BaseAgent
from core.mcp.envelope import MCPEnvelope

logger = logging.getLogger(__name__)

DB_API_URL = os.environ.get("DB_API_URL", "http://api:8000")
LLM_MODEL  = os.environ.get("LLM_MODEL", "ollama/qwen3:8b")
ENABLE_INLINE_QUOTATION_PIPELINE = os.environ.get(
    "ENABLE_INLINE_QUOTATION_PIPELINE", "false"
).lower() == "true"

# Routing estático para eventos que siguen usando RabbitMQ
ROUTING_TABLE = {
    "PackageRequest":    ("quotation-agent",    "quotation.request"),
    "QuotationResult":   ("validation-agent",   "validation.check"),
    "ReservationCreate": ("reservation-agent",  "reservation.create"),
    "PaymentEvent":      ("finance-agent",      "finance.payment"),
    "DocumentRequest":   ("document-agent",     "document.generate"),
    "SagaCompensate":    ("monitoring-agent",   "monitoring.compensate"),
}

# ── System prompts para los agentes del pipeline (Fase 2) ────────────────────

_PIPELINE_SALES_PROMPT = """
You are the Sales Specialist in the Everywhere Travel quotation pipeline.
Your job: analyze a client inquiry and select the most appropriate package.
Output: a PackageRequest JSON with keys:
  client_id, package_template_id (or null), destination, start_date, end_date,
  traveler_count, customizations (dict), budget_range {min, max}, priority
Return ONLY valid JSON. No explanation.
""".strip()

_PIPELINE_QUOTATION_PROMPT = """
You are the Quotation Specialist in the Everywhere Travel quotation pipeline.
You receive a PackageRequest and must calculate the final price.
Formula: base_cost = package_price * traveler_count
         margin = base_cost * 0.20
         igv    = base_cost * 0.18
         total  = base_cost + margin + igv
Output: a QuotationResult JSON with keys:
  quote_id (generate uuid), version (1), client_id, package_id,
  line_items (array with concept/unit_price/quantity/subtotal),
  total_cost, margin_pct (20.0), currency ("PEN"),
  status ("DRAFT"), anomaly_flags (list)
Return ONLY valid JSON. No explanation.
""".strip()

_PIPELINE_VALIDATION_PROMPT = """
You are the Validation Specialist in the Everywhere Travel quotation pipeline.
You receive a QuotationResult and must verify compliance with business rules:
  R001: margin_pct >= 15 (BLOCKING if < 0, ERROR if < 15)
  R002: total_cost > 0 (BLOCKING)
  R003: line_items not empty (BLOCKING)
  R004: valid_until is in the future
Output: the same QuotationResult JSON but with status changed to "VALIDATED" or "REJECTED",
and add a validation_summary field.
Return ONLY valid JSON. No explanation.
""".strip()

_CONFLICT_RESOLUTION_PROMPT = """
You are the Conflict Resolution Specialist for Everywhere Travel.
When multiple agents report conflicting state for the same entity,
you analyze the conflict and provide a concise resolution strategy.
Always respond with a JSON: { "resolution": "...", "action": "retry|escalate|ignore", "priority": "low|medium|high" }
""".strip()

_VALIDATION_AGENT_PROMPT = """
You are a Validation Agent for conflict scenarios.
Assess whether the conflicting state is a data integrity issue.
Respond with JSON: { "is_integrity_issue": bool, "confidence": float, "recommendation": str }
""".strip()

_MONITORING_AGENT_PROMPT = """
You are a Monitoring Agent for conflict scenarios.
Assess the operational impact and decide if escalation to human is needed.
Respond with JSON: { "needs_escalation": bool, "impact": "low|medium|high|critical", "action": str }
""".strip()


class OrchestratorAgent(BaseAgent):
    agent_id = "orchestrator-agent"
    queue_name = "orchestrator-commands"
    system_prompt_file = "agents/orchestrator/prompts/system_prompt.txt"

    def __init__(self) -> None:
        super().__init__()
        self._http = httpx.AsyncClient(base_url=DB_API_URL, timeout=30)

        # Swarms agents/workflows — se inicializan en initialize()
        self._conflict_agent: Agent | None = None           # Fase 1
        self._quotation_pipeline: SequentialWorkflow | None = None  # Fase 2
        self._conflict_rearrange: AgentRearrange | None = None      # Fase 3

    async def initialize(self) -> None:
        await super().initialize()

        # ── FASE 1: Agent para resolución de conflictos ──────────────────────
        self._conflict_agent = Agent(
            agent_name="conflict-resolver-et",
            system_prompt=_CONFLICT_RESOLUTION_PROMPT,
            model_name=LLM_MODEL,
            max_loops=1,
            output_type="str",
            verbose=False,
            temperature=0.2,
        )

        # ── FASE 2: SequentialWorkflow para el pipeline de cotización ────────
        #
        # Tres agentes especializados que se ejecutan en cadena.
        # El output de cada agente se pasa como input al siguiente.
        # Sales → Quotation → Validation, todo dentro del Orchestrator.
        # Elimina 3 hops de RabbitMQ para flujos simples.
        #
        pipeline_sales = Agent(
            agent_name="pipeline-sales",
            system_prompt=_PIPELINE_SALES_PROMPT,
            model_name=LLM_MODEL,
            max_loops=1,
            output_type="str",
            temperature=0.1,
        )
        pipeline_quotation = Agent(
            agent_name="pipeline-quotation",
            system_prompt=_PIPELINE_QUOTATION_PROMPT,
            model_name=LLM_MODEL,
            max_loops=1,
            output_type="str",
            temperature=0.05,
        )
        pipeline_validation = Agent(
            agent_name="pipeline-validation",
            system_prompt=_PIPELINE_VALIDATION_PROMPT,
            model_name=LLM_MODEL,
            max_loops=1,
            output_type="str",
            temperature=0.05,
        )

        self._quotation_pipeline = SequentialWorkflow(
            name="et-quotation-pipeline",
            agents=[pipeline_sales, pipeline_quotation, pipeline_validation],
            max_loops=1,
            verbose=False,
        )

        # ── FASE 3: AgentRearrange para routing dinámico de conflictos ───────
        #
        # Para ConflictNotification, el LLM decide si involucrar
        # solo el agente de validación, solo el de monitoring, o ambos.
        # El flow "validation_agent -> monitoring_agent" se evalúa dinámicamente.
        #
        phase3_validation = Agent(
            agent_name="conflict-validation-agent",
            system_prompt=_VALIDATION_AGENT_PROMPT,
            model_name=LLM_MODEL,
            max_loops=1,
            output_type="str",
            temperature=0.1,
        )
        phase3_monitoring = Agent(
            agent_name="conflict-monitoring-agent",
            system_prompt=_MONITORING_AGENT_PROMPT,
            model_name=LLM_MODEL,
            max_loops=1,
            output_type="str",
            temperature=0.1,
        )

        self._conflict_rearrange = AgentRearrange(
            name="et-conflict-router",
            agents=[phase3_validation, phase3_monitoring],
            flow="conflict-validation-agent -> conflict-monitoring-agent",
            max_loops=1,
            verbose=False,
        )

        logger.info(
            "[Orchestrator] Swarms inicializado: "
            "Fase1=ConflictAgent | Fase2=SequentialWorkflow(3 agentes) | Fase3=AgentRearrange"
        )

    def _register_handlers(self) -> None:
        self._consumer.register_handler("PackageInquiry", self._handle_inquiry)
        for payload_type in ROUTING_TABLE:
            self._consumer.register_handler(payload_type, self.handle_message)
        self._consumer.register_handler("ConflictNotification", self._handle_conflict)
        self._consumer.register_handler("AgentDegraded", self._handle_degraded_agent)

    # ── FASE 2: PackageInquiry → SequentialWorkflow ──────────────────────────

    async def _handle_inquiry(self, envelope: MCPEnvelope) -> None:
        """
        FASE 2 — Procesa una consulta de paquete directamente con el
        SequentialWorkflow de Swarms (Sales → Quotation → Validation).
        Si el paquete es del catálogo, resuelve sin tocar RabbitMQ.
        Si falla, hace fallback al routing vía RabbitMQ.
        """
        inquiry = envelope.payload
        logger.info(
            f"[Orchestrator/Fase2] PackageInquiry recibida | "
            f"destino={inquiry.get('destination')} saga={envelope.saga_id}"
        )

        # Obtener paquetes del catálogo para enriquecer el contexto
        catalog_packages = await self._fetch_catalog(inquiry)
        has_catalog_match = bool(catalog_packages)

        if has_catalog_match and self._quotation_pipeline and ENABLE_INLINE_QUOTATION_PIPELINE:
            # CAMINO RÁPIDO: SequentialWorkflow inline
            prompt = (
                f"Client inquiry: {json.dumps(inquiry)}\n"
                f"Available catalog packages: {json.dumps(catalog_packages[:3])}\n"
                f"Saga ID: {envelope.saga_id}\n\n"
                "Process this inquiry through the full quotation pipeline."
            )
            try:
                raw_result = await asyncio.to_thread(
                    self._quotation_pipeline.run, prompt
                )
                quotation = self._extract_final_quotation(raw_result)
                if quotation:
                    await self._persist_pipeline_quotation(quotation, inquiry)
                    await self._notify_client(quotation, inquiry.get("client_id"))
                    await self._saga.record_step(
                        envelope.saga_id, "pipeline_quotation_complete",
                        self.agent_id, "COMPLETED",
                        output_ref=f"quote:{quotation.get('quote_id')}",
                    )
                    logger.info(
                        f"[Orchestrator/Fase2] Pipeline completado | "
                        f"quote={quotation.get('quote_id')} "
                        f"status={quotation.get('status')}"
                    )
                    return
            except Exception as e:
                logger.warning(
                    f"[Orchestrator/Fase2] Pipeline falló ({type(e).__name__}), "
                    "fallback a routing RabbitMQ"
                )

        # FALLBACK / paquete personalizado: routing clásico vía RabbitMQ
        await self._route_to_sales(envelope)

    async def _fetch_catalog(self, inquiry: dict) -> list:
        try:
            resp = await self._http.get(
                "/api/v1/packages/search",
                params={
                    "destination": inquiry.get("destination", ""),
                    "budget_max": inquiry.get("budget_max", 99999),
                },
            )
            if resp.status_code == 200:
                return resp.json().get("packages", [])
        except Exception:
            pass
        return []

    def _extract_final_quotation(self, raw: str) -> dict | None:
        """Extrae el último JSON válido del output del SequentialWorkflow."""
        try:
            text = raw.strip()
            # Buscar el último bloque JSON que contenga quote_id
            if "```" in text:
                blocks = text.split("```")
                for block in reversed(blocks):
                    cleaned = block.lstrip("json").strip()
                    if "quote_id" in cleaned and cleaned.startswith("{"):
                        return json.loads(cleaned)
            # Buscar en el texto plano
            last_brace = text.rfind("}")
            first_brace = text.rfind("{", 0, last_brace)
            if first_brace != -1:
                candidate = text[first_brace:last_brace + 1]
                parsed = json.loads(candidate)
                if "quote_id" in parsed or "total_cost" in parsed:
                    return parsed
        except Exception:
            pass
        return None

    async def _persist_pipeline_quotation(self, quotation: dict, _inquiry: dict) -> None:
        """Persiste la cotización generada por el pipeline en la BD."""
        import uuid as _uuid
        if "quote_id" not in quotation:
            quotation["quote_id"] = str(_uuid.uuid4())
        try:
            await self._http.post(
                "/api/v1/quotations",
                json={**quotation, "created_by_agent": "orchestrator-pipeline"},
            )
        except Exception as e:
            logger.warning(f"[Orchestrator/Fase2] Error persistiendo cotización del pipeline: {e}")

    async def _notify_client(self, quotation: dict, client_id: str | None) -> None:
        if client_id:
            await self._redis.publish_realtime(
                f"client:{client_id}",
                {"event": "quotation_ready", "data": quotation},
            )

    async def _route_to_sales(self, envelope: MCPEnvelope) -> None:
        """Routing clásico vía RabbitMQ al Sales Agent."""
        reply = envelope.make_reply(
            payload_type="PackageInquiry",
            payload=envelope.payload,
            receiver_agent="sales-agent",
        )
        await self._publisher.publish(reply, "sales.inquiry")
        await self._saga.record_step(
            envelope.saga_id, "route_to_sales_rabbitmq",
            self.agent_id, "COMPLETED",
        )

    # ── Routing clásico RabbitMQ para el resto de eventos ────────────────────

    async def handle_message(self, envelope: MCPEnvelope) -> None:
        logger.info(f"[Orchestrator] Enrutando {envelope.payload_type} saga={envelope.saga_id}")

        saga = await self._saga.get_saga_status(envelope.saga_id)
        if not saga:
            await self._saga.start_saga(
                saga_type=envelope.payload_type,
                initiated_by=envelope.sender_agent,
                context=envelope.payload,
            )

        route = ROUTING_TABLE.get(envelope.payload_type)
        if not route:
            logger.warning(f"[Orchestrator] Sin ruta para: {envelope.payload_type}")
            return

        receiver_agent, routing_key = route

        cb_state = await self._circuit_breaker.get_state()
        if cb_state == "OPEN":
            await self._saga.record_step(
                envelope.saga_id, envelope.payload_type,
                self.agent_id, "BLOCKED", error="Circuit breaker OPEN",
            )
            return

        reply = envelope.make_reply(
            payload_type=envelope.payload_type,
            payload=envelope.payload,
            receiver_agent=receiver_agent,
        )
        await self._publisher.publish(reply, routing_key)
        await self._saga.record_step(
            saga_id=envelope.saga_id,
            step_name=f"route_to_{receiver_agent}",
            agent=self.agent_id,
            status="COMPLETED",
            output_ref=f"{routing_key}:{envelope.message_id}",
        )
        self._messages_processed += 1
        logger.info(f"[Orchestrator] {envelope.payload_type} → {receiver_agent}")

    # ── FASE 3: ConflictNotification → AgentRearrange ────────────────────────

    async def _handle_conflict(self, envelope: MCPEnvelope) -> None:
        """
        FASE 3 — AgentRearrange decide dinámicamente qué agentes involucrar
        en la resolución del conflicto (validation, monitoring, o ambos).

        FASE 1 — Si AgentRearrange no está disponible, usa el ConflictAgent
        directamente para una resolución simple.
        """
        conflict = envelope.payload
        entity_id = conflict.get("entity_id", "unknown")
        logger.warning(f"[Orchestrator/Fase3] CONFLICTO en {entity_id} | agentes={conflict.get('agents')}")

        resolution_data = {}

        if self._conflict_rearrange:
            # FASE 3: AgentRearrange coordina validation + monitoring dinámicamente
            try:
                conflict_prompt = (
                    f"Conflict detected:\n{json.dumps(conflict, indent=2)}\n\n"
                    "Analyze this conflict: first check data integrity, "
                    "then assess operational impact and escalation need."
                )
                raw = await asyncio.to_thread(
                    self._conflict_rearrange.run, conflict_prompt
                )
                resolution_data = self._parse_rearrange_output(raw)
                logger.info(
                    f"[Orchestrator/Fase3] AgentRearrange completado | "
                    f"escalate={resolution_data.get('needs_escalation')} "
                    f"impact={resolution_data.get('impact')}"
                )
            except Exception as e:
                logger.warning(f"[Orchestrator/Fase3] AgentRearrange falló ({type(e).__name__})")

        if not resolution_data and self._conflict_agent:
            # FASE 1: Fallback al agente de resolución simple
            resolution_text = await self._resolve_with_conflict_agent(conflict)
            resolution_data = {"resolution": resolution_text, "action": "retry", "priority": "medium"}

        await self.publish(
            payload_type="ConflictResolved",
            payload={
                "entity_id": entity_id,
                "resolution": resolution_data.get("resolution", "Manual review required"),
                "action": resolution_data.get("action", "escalate"),
                "impact": resolution_data.get("impact", "unknown"),
                "needs_escalation": resolution_data.get("needs_escalation", False),
                "resolved_by": f"{self.agent_id}:swarms-rearrange",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            receiver_agent="monitoring-agent",
            routing_key="monitoring.conflict_resolved",
            saga_id=envelope.saga_id,
        )

    async def _resolve_with_conflict_agent(self, conflict: dict) -> str:
        """FASE 1: Resolución de conflicto con swarms.Agent simple."""
        try:
            prompt = (
                f"Conflict: {json.dumps(conflict)}\n"
                "Provide a brief resolution strategy in one sentence."
            )
            raw = await asyncio.to_thread(self._conflict_agent.run, prompt)
            try:
                parsed = json.loads(raw)
                return parsed.get("resolution", raw)
            except Exception:
                return raw.strip()[:200]
        except Exception as e:
            logger.warning(f"[Orchestrator/Fase1] ConflictAgent falló: {e}")
            return "Manual review required due to agent unavailability"

    def _parse_rearrange_output(self, raw: str) -> dict:
        """Extrae el resultado consolidado del AgentRearrange."""
        result = {}
        try:
            for line in raw.split("\n"):
                line = line.strip()
                if line.startswith("{") and line.endswith("}"):
                    partial = json.loads(line)
                    result.update(partial)
        except Exception:
            pass
        return result

    async def _handle_degraded_agent(self, envelope: MCPEnvelope) -> None:
        agent_id = envelope.payload.get("agent_id")
        logger.error(f"[Orchestrator] Agente degradado: {agent_id}")
        await self._circuit_breaker._transition_to("OPEN", {
            "failure_count": 5,
            "last_failure": datetime.now(timezone.utc).isoformat(),
        })


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    agent = OrchestratorAgent()
    asyncio.run(agent.run())
