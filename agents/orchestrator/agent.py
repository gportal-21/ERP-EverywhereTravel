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
import time
from datetime import datetime, timezone
import httpx
from pydantic import BaseModel, Field
from agents.swarms_compat import Agent, SequentialWorkflow

from agents.base_agent import BaseAgent
from core.mcp.envelope import MCPEnvelope
from core.structured_output import parse_structured_output

logger = logging.getLogger(__name__)

DB_API_URL = os.environ.get("DB_API_URL", "http://api:8000")
LLM_MODEL  = os.environ.get("LLM_MODEL", "ollama/qwen3:8b")
ENABLE_INLINE_QUOTATION_PIPELINE = os.environ.get(
    "ENABLE_INLINE_QUOTATION_PIPELINE", "false"
).lower() == "true"

# Debe coincidir con "Escalate to human review when confidence < 0.7" del
# system_prompt.txt del Orchestrator — antes esa instrucción no tenía ningún
# cálculo de confidence real detrás; ahora sí (ver _handle_conflict).
HUMAN_ESCALATION_CONFIDENCE_THRESHOLD = 0.7


class ConflictValidationOutput(BaseModel):
    """Schema de salida forzada — Fase 3, sub-agente de integridad de datos."""
    is_integrity_issue: bool
    confidence: float = Field(ge=0.0, le=1.0)
    recommendation: str


class ConflictMonitoringOutput(BaseModel):
    """Schema de salida forzada — Fase 3, sub-agente de impacto operativo."""
    needs_escalation: bool
    impact: str
    action: str

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
        self._conflict_agent: Agent | None = None                # Fase 1
        self._quotation_pipeline: SequentialWorkflow | None = None  # Fase 2
        self._conflict_validation_agent: Agent | None = None     # Fase 3
        self._conflict_monitoring_agent: Agent | None = None     # Fase 3

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

        # ── FASE 3: dos sub-agentes especializados evalúan el conflicto ──────
        #
        # Ambos reciben el mismo contexto del conflicto (no se encadenan uno
        # a otro como haría AgentRearrange por defecto — encadenar el output
        # de texto de "validation" como input de "monitoring" no tiene sentido
        # aquí porque son dos evaluaciones independientes del mismo hecho).
        # Cada uno fuerza su propio JSON Schema de salida (constrained
        # decoding en Ollama), incluyendo el campo `confidence` que el
        # system_prompt.txt del Orchestrator promete usar para HITL
        # (ver HUMAN_ESCALATION_CONFIDENCE_THRESHOLD y _handle_conflict).
        #
        self._conflict_validation_agent = Agent(
            agent_name="conflict-validation-agent",
            system_prompt=_VALIDATION_AGENT_PROMPT,
            model_name=LLM_MODEL,
            max_loops=1,
            output_type="str",
            temperature=0.1,
            response_schema=ConflictValidationOutput.model_json_schema(),
        )
        self._conflict_monitoring_agent = Agent(
            agent_name="conflict-monitoring-agent",
            system_prompt=_MONITORING_AGENT_PROMPT,
            model_name=LLM_MODEL,
            max_loops=1,
            output_type="str",
            temperature=0.1,
            response_schema=ConflictMonitoringOutput.model_json_schema(),
        )

        logger.info(
            "[Orchestrator] Swarms inicializado: "
            "Fase1=ConflictAgent | Fase2=SequentialWorkflow(3 agentes) | "
            "Fase3=ValidationAgent+MonitoringAgent (salida estructurada)"
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

    # ── FASE 3: ConflictNotification → evaluación estructurada + HITL ────────

    async def _handle_conflict(self, envelope: MCPEnvelope) -> None:
        """
        FASE 3 — Dos sub-agentes especializados evalúan el mismo conflicto de
        forma independiente, cada uno con salida forzada a su JSON Schema:
          - conflict-validation-agent → ¿es un problema de integridad de datos?
            y con qué `confidence` (0-1)
          - conflict-monitoring-agent → ¿cuál es el impacto operativo y
            requiere escalar a un humano?

        HITL real: el system_prompt.txt del Orchestrator promete escalar a
        revisión humana cuando confidence < 0.7 (HUMAN_ESCALATION_CONFIDENCE_THRESHOLD).
        Antes ese umbral no tenía ningún cálculo detrás; ahora needs_escalation
        se activa si el monitoring-agent lo pide O si confidence cae bajo el
        umbral, y el resultado se enruta a MonitoringAgent, que ejecuta la
        escalación real (ver agents/monitoring/agent.py::_handle_conflict_resolved).

        FASE 1 — Si algún sub-agente falla, usa el ConflictAgent simple como
        resolución de respaldo (mismo patrón de degradación del resto del sistema).
        """
        conflict = envelope.payload
        entity_id = conflict.get("entity_id", "unknown")
        logger.warning(f"[Orchestrator/Fase3] CONFLICTO en {entity_id} | agentes={conflict.get('agents')}")

        validation_result = await self._assess_conflict_integrity(conflict, saga_id=envelope.saga_id)
        monitoring_result = await self._assess_conflict_impact(conflict, saga_id=envelope.saga_id)

        if validation_result is None and monitoring_result is None:
            # Ambos sub-agentes fallaron (Ollama caído, etc.) — fallback Fase 1
            resolution_text = await self._resolve_with_conflict_agent(conflict)
            await self.publish(
                payload_type="ConflictResolved",
                payload={
                    "entity_id": entity_id,
                    "resolution": resolution_text,
                    "action": "escalate",
                    "impact": "unknown",
                    "confidence": 0.0,
                    "needs_escalation": True,  # sin evaluación estructurada, se prefiere escalar
                    "resolved_by": f"{self.agent_id}:fallback-conflict-agent",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                receiver_agent="monitoring-agent",
                routing_key="monitoring.conflict_resolved",
                saga_id=envelope.saga_id,
            )
            return

        confidence = validation_result.confidence if validation_result else 0.0
        low_confidence = confidence < HUMAN_ESCALATION_CONFIDENCE_THRESHOLD
        needs_escalation = bool(monitoring_result and monitoring_result.needs_escalation) or low_confidence

        logger.info(
            f"[Orchestrator/Fase3] Evaluación completada | confidence={confidence:.2f} "
            f"low_confidence={low_confidence} needs_escalation={needs_escalation}"
        )

        await self.publish(
            payload_type="ConflictResolved",
            payload={
                "entity_id": entity_id,
                "resolution": (validation_result.recommendation if validation_result else "Manual review required"),
                "action": (monitoring_result.action if monitoring_result else "escalate"),
                "impact": (monitoring_result.impact if monitoring_result else "unknown"),
                "confidence": confidence,
                "needs_escalation": needs_escalation,
                "escalation_reason": "low_confidence" if (low_confidence and not (monitoring_result and monitoring_result.needs_escalation)) else "monitoring_agent",
                "resolved_by": f"{self.agent_id}:structured-conflict-assessment",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            receiver_agent="monitoring-agent",
            routing_key="monitoring.conflict_resolved",
            saga_id=envelope.saga_id,
        )

    async def _assess_conflict_integrity(self, conflict: dict, saga_id: str | None = None) -> ConflictValidationOutput | None:
        if not self._conflict_validation_agent:
            return None
        start = time.perf_counter()
        try:
            prompt = (
                f"Conflict detected:\n{json.dumps(conflict, indent=2)}\n\n"
                "Assess whether this is a data integrity issue and how confident you are."
            )
            raw = await asyncio.to_thread(self._conflict_validation_agent.run, prompt)
            result = parse_structured_output(raw, ConflictValidationOutput)
            await self.report_llm_interaction(
                "assess_conflict_integrity", input_data=conflict,
                output_data=result.model_dump() if result else None,
                duration_ms=int((time.perf_counter() - start) * 1000),
                success=result is not None, saga_id=saga_id,
            )
            return result
        except Exception as e:
            logger.warning(f"[Orchestrator/Fase3] conflict-validation-agent falló: {e}")
            await self.report_llm_interaction(
                "assess_conflict_integrity", input_data=conflict,
                duration_ms=int((time.perf_counter() - start) * 1000),
                success=False, error=str(e), saga_id=saga_id,
            )
            return None

    async def _assess_conflict_impact(self, conflict: dict, saga_id: str | None = None) -> ConflictMonitoringOutput | None:
        if not self._conflict_monitoring_agent:
            return None
        start = time.perf_counter()
        try:
            prompt = (
                f"Conflict detected:\n{json.dumps(conflict, indent=2)}\n\n"
                "Assess the operational impact and decide if escalation to a human is needed."
            )
            raw = await asyncio.to_thread(self._conflict_monitoring_agent.run, prompt)
            result = parse_structured_output(raw, ConflictMonitoringOutput)
            await self.report_llm_interaction(
                "assess_conflict_impact", input_data=conflict,
                output_data=result.model_dump() if result else None,
                duration_ms=int((time.perf_counter() - start) * 1000),
                success=result is not None, saga_id=saga_id,
            )
            return result
        except Exception as e:
            logger.warning(f"[Orchestrator/Fase3] conflict-monitoring-agent falló: {e}")
            await self.report_llm_interaction(
                "assess_conflict_impact", input_data=conflict,
                duration_ms=int((time.perf_counter() - start) * 1000),
                success=False, error=str(e), saga_id=saga_id,
            )
            return None

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

    async def _handle_degraded_agent(self, envelope: MCPEnvelope) -> None:
        agent_id = envelope.payload.get("agent_id")
        logger.error(f"[Orchestrator] Agente degradado: {agent_id}")
        await self._circuit_breaker._transition_to("OPEN", {
            "failure_count": 5,
            "last_failure": datetime.now(timezone.utc).isoformat(),
        })


if __name__ == "__main__":
    from core.logging_config import configure_logging
    configure_logging("orchestrator-agent")
    agent = OrchestratorAgent()
    asyncio.run(agent.run())
