"""
Quotation Agent — Cálculo preciso de cotizaciones con versionado y detección de anomalías.

MIGRACIÓN SWARMS FASE 1:
- self._anthropic reemplazado por swarms.Agent
- Tools financieros nativos: _tool_calculate_igv, _tool_check_margin_policy,
  _tool_estimate_component_price
- El agente usa los tools para calcular componentes de paquetes personalizados
- asyncio.to_thread() para Agent.run() síncrono en contexto async
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

import httpx
from agents.swarms_compat import Agent

from agents.base_agent import BaseAgent
from core.mcp.envelope import MCPEnvelope

logger = logging.getLogger(__name__)

IGV_RATE       = Decimal("0.18")
MIN_MARGIN_PCT = Decimal("15.0")
DEFAULT_MARGIN = Decimal("20.0")
DB_API_URL     = os.environ.get("DB_API_URL", "http://api:8000")
LLM_MODEL      = os.environ.get("LLM_MODEL", "ollama/qwen3:8b")


# ── Swarms Tools financieros (síncronos) ──────────────────────────────────────

def _tool_calculate_igv(base_amount: float) -> str:
    """Calculates IGV (18% VAT) on a base cost amount in PEN.

    Args:
        base_amount: The base cost in PEN before adding IGV

    Returns:
        JSON string with igv_amount, total_with_igv, and rate_used
    """
    igv = round(base_amount * 0.18, 2)
    return json.dumps({
        "igv_amount": igv,
        "total_with_igv": round(base_amount + igv, 2),
        "rate_used": 0.18,
        "currency": "PEN",
    })


def _tool_check_margin_policy(margin_pct: float) -> str:
    """Validates whether a margin percentage complies with Everywhere Travel pricing policy.

    Args:
        margin_pct: The proposed margin percentage (e.g. 20.0 for 20%)

    Returns:
        JSON string with compliant boolean, minimum_required, recommendation
    """
    minimum = 15.0
    compliant = margin_pct >= minimum
    return json.dumps({
        "compliant": compliant,
        "minimum_required": minimum,
        "proposed": margin_pct,
        "recommendation": "approved" if compliant else f"increase_to_{minimum}",
        "severity": "ok" if compliant else ("blocking" if margin_pct < 0 else "error"),
    })


def _tool_estimate_component_price(
    component_type: str, destination: str, traveler_count: int, duration_days: int
) -> str:
    """Estimates the price of a travel package component based on destination and duration.

    Args:
        component_type: Type of component: 'flight', 'hotel', 'transfer', 'guide', 'activities'
        destination: Travel destination city/country
        traveler_count: Number of travelers
        duration_days: Duration of the trip in days

    Returns:
        JSON string with estimated unit_price, quantity, subtotal in PEN
    """
    # Tabla de precios base por componente (PEN)
    BASE_PRICES = {
        "flight":     {"domestic": 350, "international": 1800},
        "hotel":      {"per_night": 180},
        "transfer":   {"per_trip": 80},
        "guide":      {"per_day": 150},
        "activities": {"per_day": 120},
    }

    intl_keywords = ["cancún", "miami", "madrid", "paris", "new york", "europa", "usa"]
    is_international = any(k in destination.lower() for k in intl_keywords)

    prices = BASE_PRICES.get(component_type, {"base": 200})
    if component_type == "flight":
        unit = prices["international"] if is_international else prices["domestic"]
        qty = traveler_count
    elif component_type == "hotel":
        unit = prices["per_night"]
        qty = duration_days * traveler_count
    elif component_type == "transfer":
        unit = prices["per_trip"]
        qty = 2 * traveler_count  # ida y vuelta
    else:
        unit = prices.get("per_day", 150)
        qty = duration_days * traveler_count

    subtotal = round(unit * qty, 2)
    return json.dumps({
        "concept": f"{component_type.capitalize()} — {destination}",
        "unit_price": float(unit),
        "quantity": qty,
        "subtotal": subtotal,
        "currency": "PEN",
    })


def _tool_detect_budget_anomaly(
    total_cost: float, budget_max: float, margin_pct: float
) -> str:
    """Detects pricing anomalies: over budget, low margin, or zero cost.

    Args:
        total_cost: Final total cost in PEN
        budget_max: Maximum client budget in PEN (0 if unspecified)
        margin_pct: Applied margin percentage

    Returns:
        JSON string with anomaly_flags list and severity
    """
    flags = []
    if budget_max > 0 and total_cost > budget_max * 1.1:
        flags.append("OVER_BUDGET")
    if margin_pct < 15:
        flags.append("LOW_MARGIN")
    if total_cost == 0:
        flags.append("ZERO_COST_ERROR")
    return json.dumps({
        "anomaly_flags": flags,
        "has_anomalies": len(flags) > 0,
        "severity": "BLOCKING" if "ZERO_COST_ERROR" in flags else ("ERROR" if flags else "OK"),
    })


# ── Agent ─────────────────────────────────────────────────────────────────────

class QuotationAgent(BaseAgent):
    agent_id = "quotation-agent"
    queue_name = "quotation-events"
    system_prompt_file = "agents/quotation/prompts/system_prompt.txt"

    def __init__(self) -> None:
        super().__init__()
        self._swarm_agent: Agent | None = None
        self._http = httpx.AsyncClient(base_url=DB_API_URL, timeout=30)

    async def initialize(self) -> None:
        """Crea el Agent de Swarms tras cargar el system prompt."""
        await super().initialize()

        # FASE 1: swarms.Agent con 4 tools financieros nativos
        self._swarm_agent = Agent(
            agent_name="quotation-agent-et",
            system_prompt=self._system_prompt,
            model_name=LLM_MODEL,
            max_loops=2,                # hasta 2 iteraciones para refinar si detecta anomalías
            tools=[
                _tool_calculate_igv,
                _tool_check_margin_policy,
                _tool_estimate_component_price,
                _tool_detect_budget_anomaly,
            ],
            memory_chunk_size=1500,
            output_type="str",
            verbose=False,
            temperature=0.05,           # muy determinístico para cálculos financieros
        )
        logger.info("[Quotation] Swarms Agent (Fase 1) inicializado con 4 tools financieros")

    def _register_handlers(self) -> None:
        self._consumer.register_handler("PackageRequest", self.handle_message)

    async def handle_message(self, envelope: MCPEnvelope) -> None:
        request  = envelope.payload
        client_id = request.get("client_id")
        quote_id  = str(uuid.uuid4())

        logger.info(f"[Quotation] Calculando | cliente={client_id} destino={request.get('destination')}")

        package_data = await self._fetch_package(request.get("package_template_id"))
        line_items, base_cost = await self._calculate_line_items(request, package_data)

        margin_pct = DEFAULT_MARGIN
        margin = (base_cost * margin_pct / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        taxes  = (base_cost * IGV_RATE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        total_cost = base_cost + margin + taxes

        anomaly_flags = self._detect_anomalies(total_cost, margin_pct, request.get("budget_range", {}))
        version = await self._get_next_version(quote_id)

        quotation = {
            "quote_id":     quote_id,
            "version":      version,
            "package_id":   request.get("package_template_id"),
            "client_id":    client_id,
            "line_items":   line_items,
            "total_cost":   float(total_cost),
            "margin_pct":   float(margin_pct),
            "currency":     "PEN",
            "valid_until":  (datetime.now(timezone.utc) + timedelta(hours=48)).isoformat(),
            "status":       "DRAFT",
            "anomaly_flags": anomaly_flags,
        }

        await self._save_quotation(quotation, request)
        await self.publish(
            payload_type="QuotationResult",
            payload=quotation,
            receiver_agent="orchestrator-agent",
            routing_key="orchestrator.route",
            saga_id=envelope.saga_id,
        )
        await self._saga.record_step(
            envelope.saga_id, "quotation_calculated",
            self.agent_id, "COMPLETED",
            output_ref=f"quote:{quote_id}:v{version}",
        )
        self._messages_processed += 1
        logger.info(f"[Quotation] Generada {quote_id} v{version} total={total_cost} anomalías={anomaly_flags}")

    async def _fetch_package(self, package_id: str | None) -> dict:
        if not package_id:
            return {}
        try:
            resp = await self._http.get(f"/api/v1/packages/{package_id}")
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            logger.warning(f"[Quotation] Error obteniendo paquete {package_id}: {e}")
        return {}

    async def _calculate_line_items(
        self, request: dict, package: dict
    ) -> tuple[list[dict], Decimal]:
        traveler_count = request.get("traveler_count", 1)
        base_price = Decimal(str(package.get("base_price", 0)))

        if base_price > 0:
            line_items = [{
                "concept":    package.get("name", "Paquete turístico"),
                "unit_price": float(base_price),
                "quantity":   traveler_count,
                "subtotal":   float(base_price * traveler_count),
            }]
            return line_items, base_price * traveler_count

        logger.info("[Quotation] Sin paquete de catálogo; usando estimación determinística por presupuesto")
        return self._budget_fallback(request)

    async def _estimate_with_swarms(
        self, request: dict
    ) -> tuple[list[dict], Decimal]:
        """
        FASE 1 — El Agent de Swarms usa _tool_estimate_component_price para
        desglosar los componentes de un paquete personalizado.
        Invoca _tool_calculate_igv y _tool_detect_budget_anomaly automáticamente.
        """
        duration_days = self._days_between(
            request.get("start_date"), request.get("end_date")
        )
        prompt = (
            f"Custom package request:\n{json.dumps(request, indent=2)}\n\n"
            f"Duration: {duration_days} days, Travelers: {request.get('traveler_count', 1)}\n\n"
            "Use _tool_estimate_component_price for each needed component "
            "(flight, hotel, transfer, activities). "
            "Use _tool_check_margin_policy to validate 20% margin. "
            "Return ONLY a JSON array of line_items with keys: "
            "concept, unit_price, quantity, subtotal."
        )
        try:
            raw = await asyncio.to_thread(self._swarm_agent.run, prompt)
            return self._parse_line_items(raw, request)
        except Exception as e:
            logger.warning(f"[Quotation] Swarms Agent falló ({type(e).__name__}), usando estimación por presupuesto")
            return self._budget_fallback(request)

    def _parse_line_items(self, raw: str, request: dict) -> tuple[list[dict], Decimal]:
        try:
            text = raw.strip()
            if "```" in text:
                for block in reversed(text.split("```")):
                    cleaned = block.lstrip("json").strip()
                    if cleaned.startswith("["):
                        text = cleaned
                        break
            elif "[" in text:
                text = text[text.rfind("["):text.rfind("]") + 1]

            items = json.loads(text)
            base_cost = Decimal(str(sum(float(i["subtotal"]) for i in items)))
            return items, base_cost
        except Exception:
            return self._budget_fallback(request)

    def _budget_fallback(self, request: dict) -> tuple[list[dict], Decimal]:
        budget = Decimal(str(request.get("budget_range", {}).get("max", 1000)))
        estimated = (budget * Decimal("0.75")).quantize(Decimal("0.01"))
        return [{
            "concept":    "Paquete personalizado (estimado)",
            "unit_price": float(estimated),
            "quantity":   1,
            "subtotal":   float(estimated),
        }], estimated

    def _detect_anomalies(
        self, total_cost: Decimal, margin_pct: Decimal, budget_range: dict
    ) -> list[str]:
        flags = []
        budget_max = Decimal(str(budget_range.get("max", 0)))
        if budget_max > 0 and total_cost > budget_max * Decimal("1.1"):
            flags.append("OVER_BUDGET")
        if margin_pct < MIN_MARGIN_PCT:
            flags.append("LOW_MARGIN")
        if total_cost == 0:
            flags.append("ZERO_COST_ERROR")
        return flags

    async def _get_next_version(self, quote_id: str) -> int:
        key = f"quote_version:{quote_id}"
        version = await self._redis._r.incr(key)
        await self._redis._r.expire(key, 86400)
        return int(version)

    async def _save_quotation(self, quotation: dict, request: dict) -> None:
        try:
            await self._http.post(
                "/api/v1/quotations",
                json={**quotation, "request_context": request},
            )
        except Exception as e:
            logger.warning(f"[Quotation] Error persistiendo cotización: {e}")

    def _days_between(self, start: str | None, end: str | None) -> int:
        if not start or not end:
            return 5  # default
        try:
            return max(1, (datetime.fromisoformat(end) - datetime.fromisoformat(start)).days)
        except Exception:
            return 5


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    agent = QuotationAgent()
    asyncio.run(agent.run())
