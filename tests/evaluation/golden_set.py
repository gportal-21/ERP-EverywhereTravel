"""Golden Set — evaluación local de la capa de salida estructurada del LLM.

Sustituto de LangSmith (no se usa: proyecto sin cuenta, ver decisión en
docs/architecture.md). En vez de datasets remotos y evaluadores en la nube,
este golden set fija un conjunto de salidas de LLM representativas —válidas,
válidas-pero-envueltas-en-texto, e inválidas— y verifica que
core/structured_output.py::parse_structured_output() se comporte como debe:

- Acepta JSON limpio (constrained decoding funcionando).
- Recupera JSON válido envuelto en prosa o bloques ```json``` (modelos que
  ignoran `format` o proveedores sin structured output nativo).
- Rechaza (retorna None) salidas incompletas o corruptas, para que el
  agente use su fallback determinístico en vez de propagar datos inválidos.

Es determinístico y no requiere Ollama corriendo — se puede ejecutar en CI
(ver .github/workflows/ci.yml) a diferencia de una evaluación end-to-end
contra el LLM real, que sí queda como procedimiento manual documentado en
docs/evaluation.md (scripts/demo_flow.py + consulta a agent_interaction_logs).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from agents.orchestrator.agent import ConflictMonitoringOutput, ConflictValidationOutput
from agents.quotation.agent import LineItemsOutput
from agents.itinerary.agent import ItineraryOutput
from core.mcp.envelope import PackageRequest


@dataclass
class GoldenCase:
    id: str
    agent: str
    description: str
    model: type[BaseModel]
    raw_output: str
    expect_valid: bool
    expected_fields: dict[str, Any] | None = None  # solo se chequea si expect_valid=True


_PACKAGE_REQUEST_VALID = """{
  "client_id": "c-001", "package_template_id": null,
  "destination": "Cusco, Peru", "start_date": "2026-08-01", "end_date": "2026-08-06",
  "traveler_count": 2, "customizations": {"hotel_category": "4*"},
  "budget_range": {"min": 1500.0, "max": 3000.0}, "priority": "NORMAL"
}"""

_PACKAGE_REQUEST_FENCED = f"""Here is the result:
```json
{_PACKAGE_REQUEST_VALID}
```
Let me know if you need anything else."""

_PACKAGE_REQUEST_MISSING_FIELD = """{
  "client_id": "c-002", "destination": "Lima, Peru",
  "start_date": "2026-09-01", "end_date": "2026-09-05"
}"""
# falta traveler_count y budget_range (requeridos) -> debe fallar validación

_LINE_ITEMS_VALID = """{"line_items": [
  {"concept": "Vuelo Lima-Cusco", "unit_price": 350.0, "quantity": 2, "subtotal": 700.0},
  {"concept": "Hotel 4 noches", "unit_price": 180.0, "quantity": 8, "subtotal": 1440.0}
]}"""

_LINE_ITEMS_WITH_PROSE = f"""I'll use the tools to estimate each component.
{_LINE_ITEMS_VALID}
This estimate uses standard rates for Cusco."""

_LINE_ITEMS_GARBAGE = """I cannot compute this right now, please try again later."""

_ITINERARY_VALID = """{
  "title": "Cusco Magico", "subtitle": "2 viajeros", "destination": "Cusco, Peru",
  "duration_summary": "5 dias / 4 noches", "overview": "Un viaje inolvidable por Cusco.",
  "days": [
    {"day": 1, "title": "Llegada", "morning": "Vuelo", "afternoon": "Check-in",
     "evening": "Cena", "accommodation": "Hotel 4*", "meals": "Cena incluida", "tip": "Hidratarse"}
  ],
  "included_services": ["Hotel", "Traslados"], "not_included": ["Vuelos internacionales"],
  "recommendations": "Llevar ropa abrigadora.", "emergency_contacts": "911"
}"""

_ITINERARY_MISSING_DAYS = """{
  "title": "Cusco Magico", "subtitle": "2 viajeros", "destination": "Cusco, Peru",
  "duration_summary": "5 dias", "overview": "Texto"
}"""
# falta days, included_services, etc. -> debe fallar validación

_CONFLICT_VALIDATION_VALID = """{"is_integrity_issue": false, "confidence": 0.92, "recommendation": "Reintentar la operacion, no hay corrupcion de datos."}"""
_CONFLICT_VALIDATION_LOW_CONFIDENCE = """{"is_integrity_issue": true, "confidence": 0.35, "recommendation": "Revisar manualmente el estado de la entidad."}"""
_CONFLICT_MONITORING_VALID = """{"needs_escalation": false, "impact": "low", "action": "retry"}"""
_CONFLICT_MONITORING_BAD_ENUM_TYPE = """{"needs_escalation": "yes", "impact": 5, "action": null}"""
# tipos incorrectos (needs_escalation debe ser bool, impact str, action str) -> debe fallar


GOLDEN_CASES: list[GoldenCase] = [
    # ── SalesAgent → PackageRequest ──────────────────────────────────────────
    GoldenCase("sales-01", "sales-agent", "JSON limpio válido", PackageRequest,
               _PACKAGE_REQUEST_VALID, True,
               {"destination": "Cusco, Peru", "traveler_count": 2}),
    GoldenCase("sales-02", "sales-agent", "JSON válido envuelto en bloque ```json``` + prosa", PackageRequest,
               _PACKAGE_REQUEST_FENCED, True,
               {"destination": "Cusco, Peru"}),
    GoldenCase("sales-03", "sales-agent", "Faltan campos requeridos (traveler_count, budget_range)", PackageRequest,
               _PACKAGE_REQUEST_MISSING_FIELD, False),

    # ── QuotationAgent → LineItemsOutput ─────────────────────────────────────
    GoldenCase("quotation-01", "quotation-agent", "JSON limpio válido", LineItemsOutput,
               _LINE_ITEMS_VALID, True, {}),
    GoldenCase("quotation-02", "quotation-agent", "JSON válido con prosa antes/después", LineItemsOutput,
               _LINE_ITEMS_WITH_PROSE, True, {}),
    GoldenCase("quotation-03", "quotation-agent", "Respuesta sin JSON (rehúsa la tarea)", LineItemsOutput,
               _LINE_ITEMS_GARBAGE, False),

    # ── ItineraryAgent → ItineraryOutput ─────────────────────────────────────
    GoldenCase("itinerary-01", "itinerary-agent", "JSON limpio válido con 1 día", ItineraryOutput,
               _ITINERARY_VALID, True, {"destination": "Cusco, Peru"}),
    GoldenCase("itinerary-02", "itinerary-agent", "Faltan campos requeridos (days, included_services, ...)", ItineraryOutput,
               _ITINERARY_MISSING_DAYS, False),

    # ── OrchestratorAgent → Fase 3 (HITL confidence) ─────────────────────────
    GoldenCase("conflict-val-01", "orchestrator-agent", "Validación con alta confianza", ConflictValidationOutput,
               _CONFLICT_VALIDATION_VALID, True, {"is_integrity_issue": False}),
    GoldenCase("conflict-val-02", "orchestrator-agent", "Validación con baja confianza (< 0.7, debe escalar)", ConflictValidationOutput,
               _CONFLICT_VALIDATION_LOW_CONFIDENCE, True, {"confidence": 0.35}),
    GoldenCase("conflict-mon-01", "orchestrator-agent", "Monitoring válido", ConflictMonitoringOutput,
               _CONFLICT_MONITORING_VALID, True, {"needs_escalation": False}),
    GoldenCase("conflict-mon-02", "orchestrator-agent", "Tipos incorrectos en la salida", ConflictMonitoringOutput,
               _CONFLICT_MONITORING_BAD_ENUM_TYPE, False),
]
