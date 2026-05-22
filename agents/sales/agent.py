"""
Sales Agent — Gestiona el ciclo comercial de paquetes turísticos.

Responsabilidades exclusivas:
- Interfaz comercial con el sistema
- Búsqueda y selección del catálogo de paquetes
- Enriquecimiento del perfil de cliente (memoria compartida)
- Construcción del PackageRequest para Quotation Agent
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone

import anthropic
import httpx

from agents.base_agent import BaseAgent
from core.mcp.envelope import MCPEnvelope, PackageInquiry, PackageRequest

logger = logging.getLogger(__name__)

DB_API_URL = os.environ.get("DB_API_URL", "http://api:8000")


class SalesAgent(BaseAgent):
    agent_id = "sales-agent"
    queue_name = "sales-events"
    system_prompt_file = "agents/sales/prompts/system_prompt.txt"

    def __init__(self) -> None:
        super().__init__()
        self._anthropic = anthropic.AsyncAnthropic(
            api_key=os.environ["ANTHROPIC_API_KEY"]
        )
        self._http = httpx.AsyncClient(base_url=DB_API_URL, timeout=30)

    def _register_handlers(self) -> None:
        self._consumer.register_handler("PackageInquiry", self.handle_message)
        self._consumer.register_handler("QuotationResult", self._handle_quotation_result)

    async def handle_message(self, envelope: MCPEnvelope) -> None:
        inquiry_data = envelope.payload
        client_id = inquiry_data.get("client_id")

        logger.info(
            f"[Sales] Consulta recibida de cliente={client_id} "
            f"destino={inquiry_data.get('destination')}"
        )

        # 1. Recuperar memoria del cliente (preferencias históricas)
        client_memory = await self._redis.get_client_memory(client_id)

        # 2. Buscar paquetes compatibles en el catálogo
        matching_packages = await self._search_catalog(inquiry_data)

        # 3. Usar LLM para seleccionar/construir el mejor paquete
        package_request = await self._build_package_request(
            inquiry_data, matching_packages, client_memory
        )

        # 4. Actualizar memoria del cliente
        await self._redis.set_client_memory(client_id, {
            **client_memory,
            "last_inquiry": inquiry_data,
            "last_destination": inquiry_data.get("destination"),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })

        # 5. Publicar PackageRequest al Quotation Agent via Orchestrator
        await self.publish(
            payload_type="PackageRequest",
            payload=package_request,
            receiver_agent="orchestrator-agent",
            routing_key="orchestrator.route",
            saga_id=envelope.saga_id,
        )

        await self._saga.record_step(
            envelope.saga_id, "sales_package_request",
            self.agent_id, "COMPLETED",
            output_ref=package_request.get("inquiry_id"),
        )
        self._messages_processed += 1

    async def _search_catalog(self, inquiry: dict) -> list[dict]:
        """Consulta el catálogo vía API interna."""
        try:
            resp = await self._http.get(
                "/api/v1/packages/search",
                params={
                    "destination": inquiry.get("destination", ""),
                    "budget_max": inquiry.get("budget_max", 99999),
                    "duration_days_min": self._days_between(
                        inquiry.get("start_date"), inquiry.get("end_date")
                    ),
                },
            )
            if resp.status_code == 200:
                return resp.json().get("packages", [])
        except Exception as e:
            logger.warning(f"[Sales] Error consultando catálogo: {e}")
        return []

    async def _build_package_request(
        self, inquiry: dict, packages: list, memory: dict
    ) -> dict:
        """Usa Claude para construir el PackageRequest óptimo."""
        context = (
            f"Client inquiry: {inquiry}\n"
            f"Available packages: {packages[:3]}\n"
            f"Client memory: {memory}"
        )
        response = await self._anthropic.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=512,
            system=self._system_prompt,
            messages=[{
                "role": "user",
                "content": (
                    f"{context}\n\n"
                    "Return ONLY a JSON object matching PackageRequest schema. "
                    "No explanation."
                )
            }]
        )

        import json
        try:
            text = response.content[0].text.strip()
            # Limpiar markdown si Claude lo agrega
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            pkg_req = json.loads(text)
        except Exception:
            # Fallback estructurado si el parse falla
            pkg_req = self._fallback_package_request(inquiry, packages)

        pkg_req["inquiry_id"] = str(uuid.uuid4())
        return pkg_req

    def _fallback_package_request(self, inquiry: dict, packages: list) -> dict:
        template_id = packages[0]["id"] if packages else None
        return {
            "client_id": inquiry["client_id"],
            "package_template_id": template_id,
            "destination": inquiry["destination"],
            "start_date": inquiry["start_date"],
            "end_date": inquiry["end_date"],
            "traveler_count": inquiry["traveler_count"],
            "customizations": {},
            "budget_range": {
                "min": inquiry["budget_min"],
                "max": inquiry["budget_max"],
            },
            "priority": "NORMAL",
        }

    async def _handle_quotation_result(self, envelope: MCPEnvelope) -> None:
        """Recibe el resultado de la cotización y lo presenta (vía API/WS)."""
        result = envelope.payload
        status = result.get("status")
        logger.info(
            f"[Sales] Cotización recibida: quote_id={result.get('quote_id')} "
            f"status={status} total={result.get('total_cost')}"
        )
        # Notificar vía Redis pub/sub al WebSocket del dashboard
        await self._redis.publish_realtime(
            f"client:{result.get('client_id')}",
            {"event": "quotation_ready", "data": result},
        )

    def _days_between(self, start: str | None, end: str | None) -> int:
        if not start or not end:
            return 0
        try:
            d1 = datetime.fromisoformat(start)
            d2 = datetime.fromisoformat(end)
            return max(0, (d2 - d1).days)
        except Exception:
            return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    agent = SalesAgent()
    asyncio.run(agent.run())
