"""
Quotation Agent — Cálculo preciso de cotizaciones con versionado y detección de anomalías.

Responsabilidades exclusivas:
- Cálculo de precios con desglose por línea
- Versionado inmutable de cotizaciones (quote_id + version)
- Detección de anomalías financieras
- Envío a Validation Agent (nunca auto-aprueba)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

import anthropic
import httpx

from agents.base_agent import BaseAgent
from core.mcp.envelope import MCPEnvelope

logger = logging.getLogger(__name__)

IGV_RATE = Decimal("0.18")
MIN_MARGIN_PCT = Decimal("15.0")
DEFAULT_MARGIN_PCT = Decimal("20.0")
DB_API_URL = os.environ.get("DB_API_URL", "http://api:8000")


class QuotationAgent(BaseAgent):
    agent_id = "quotation-agent"
    queue_name = "quotation-events"
    system_prompt_file = "agents/quotation/prompts/system_prompt.txt"

    def __init__(self) -> None:
        super().__init__()
        self._anthropic = anthropic.AsyncAnthropic(
            api_key=os.environ["ANTHROPIC_API_KEY"]
        )
        self._http = httpx.AsyncClient(base_url=DB_API_URL, timeout=30)

    def _register_handlers(self) -> None:
        self._consumer.register_handler("PackageRequest", self.handle_message)

    async def handle_message(self, envelope: MCPEnvelope) -> None:
        request = envelope.payload
        client_id = request.get("client_id")
        quote_id = str(uuid.uuid4())

        logger.info(
            f"[Quotation] Calculando cotización para cliente={client_id} "
            f"destino={request.get('destination')}"
        )

        # 1. Obtener detalles del paquete si existe template
        package_data = await self._fetch_package(request.get("package_template_id"))

        # 2. Calcular cotización con Decimal (precisión financiera)
        line_items, base_cost = await self._calculate_line_items(
            request, package_data
        )

        # 3. Aplicar margen e IGV
        margin_pct = DEFAULT_MARGIN_PCT
        margin = (base_cost * margin_pct / 100).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        taxes = (base_cost * IGV_RATE).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        total_cost = base_cost + margin + taxes

        # 4. Detectar anomalías
        anomaly_flags = self._detect_anomalies(
            total_cost, margin_pct, request.get("budget_range", {})
        )

        # 5. Determinar versión (cotizaciones múltiples del mismo inquiry)
        version = await self._get_next_version(quote_id)

        valid_until = (datetime.now(timezone.utc) + timedelta(hours=48)).isoformat()

        quotation = {
            "quote_id": quote_id,
            "version": version,
            "package_id": request.get("package_template_id"),
            "client_id": client_id,
            "line_items": [item.dict() for item in line_items] if hasattr(line_items[0], 'dict') else line_items,
            "total_cost": float(total_cost),
            "margin_pct": float(margin_pct),
            "currency": "PEN",
            "valid_until": valid_until,
            "status": "DRAFT",
            "anomaly_flags": anomaly_flags,
        }

        # 6. Persistir en DB vía API
        await self._save_quotation(quotation, request)

        # 7. Enviar a Validation Agent (nunca auto-aprueba)
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
        logger.info(
            f"[Quotation] Cotización generada: {quote_id} v{version} "
            f"total={total_cost} anomalías={anomaly_flags}"
        )

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
            line_items = [
                {
                    "concept": package.get("name", "Paquete turístico"),
                    "unit_price": float(base_price),
                    "quantity": traveler_count,
                    "subtotal": float(base_price * traveler_count),
                }
            ]
            base_cost = base_price * traveler_count
        else:
            # Paquete personalizado: usar LLM para desglosar componentes
            line_items, base_cost = await self._estimate_custom_package(request)

        return line_items, base_cost

    async def _estimate_custom_package(
        self, request: dict
    ) -> tuple[list[dict], Decimal]:
        """Usa Claude para estimar componentes de un paquete personalizado."""
        response = await self._anthropic.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=512,
            system=self._system_prompt,
            messages=[{
                "role": "user",
                "content": (
                    f"Custom package request: {json.dumps(request)}\n\n"
                    "Generate line_items as JSON array with fields: "
                    "concept, unit_price, quantity, subtotal. "
                    "Return ONLY the JSON array."
                )
            }]
        )
        try:
            text = response.content[0].text.strip()
            if "```" in text:
                text = text.split("```")[1].lstrip("json").strip()
            items = json.loads(text)
            base_cost = Decimal(str(sum(i["subtotal"] for i in items)))
            return items, base_cost
        except Exception:
            budget = Decimal(str(request.get("budget_range", {}).get("max", 1000)))
            estimated = (budget * Decimal("0.75")).quantize(Decimal("0.01"))
            return [
                {
                    "concept": "Paquete personalizado (estimado)",
                    "unit_price": float(estimated),
                    "quantity": 1,
                    "subtotal": float(estimated),
                }
            ], estimated

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


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    agent = QuotationAgent()
    asyncio.run(agent.run())
