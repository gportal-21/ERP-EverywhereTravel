"""
Sales Agent — Gestiona el ciclo comercial de paquetes turísticos.

MIGRACIÓN SWARMS FASE 1:
- self._anthropic reemplazado por swarms.Agent
- Herramientas nativas de Swarms: _tool_select_package, _tool_validate_dates
- Memoria conversacional gestionada por Swarms (memory_chunk_size)
- Retry automático integrado en Agent.run()
- asyncio.to_thread() para no bloquear el event loop async
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone

import httpx
from agents.swarms_compat import Agent

from agents.base_agent import BaseAgent
from core.mcp.envelope import MCPEnvelope, PackageRequest
from core.structured_output import parse_structured_output

logger = logging.getLogger(__name__)

DB_API_URL = os.environ.get("DB_API_URL", "http://api:8000")
LLM_MODEL  = os.environ.get("LLM_MODEL", "ollama/qwen3:8b")


# ── Swarms Tools (deben ser funciones síncronas) ──────────────────────────────

def _tool_semantic_search_packages(query: str, top_k: int = 5) -> str:
    """Searches the package catalog by semantic similarity (RAG) instead of exact
    destination/budget filters. Use this when the client's request doesn't match
    any package by exact destination name, or describes preferences in free text
    (e.g. "algo relajante en la playa" instead of a specific destination).

    Args:
        query: Free-text description of what the client wants (destination, vibe, preferences)
        top_k: Maximum number of packages to return (default 5)

    Returns:
        JSON string with a list of matching packages, or an empty list if the
        embeddings service (Ollama) is unavailable.
    """
    try:
        resp = httpx.get(
            f"{DB_API_URL}/api/v1/packages/semantic-search",
            params={"query": query, "top_k": top_k},
            timeout=30,
        )
        if resp.status_code == 200:
            return json.dumps(resp.json())
        return json.dumps({"packages": [], "error": f"HTTP {resp.status_code}"})
    except Exception as e:
        return json.dumps({"packages": [], "error": str(e)})


def _tool_select_package(packages_json: str, budget_max: float, destination: str) -> str:
    """Selects the best matching package from available options for the given destination and budget.

    Args:
        packages_json: JSON string of available packages list
        budget_max: Maximum budget in PEN per traveler
        destination: Desired travel destination

    Returns:
        JSON string with the selected package id and name, or null if none matches
    """
    try:
        packages = json.loads(packages_json)
        if not packages:
            return json.dumps({"selected": None, "reason": "No packages available"})

        # Filtrar por presupuesto y buscar mejor match de destino
        affordable = [p for p in packages if float(p.get("base_price", 0)) <= budget_max]
        if not affordable:
            affordable = packages  # usar todos si ninguno es asequible

        # Preferir el que más coincide con el destino
        destination_lower = destination.lower()
        scored = sorted(
            affordable,
            key=lambda p: (
                destination_lower in p.get("destination", "").lower(),
                -float(p.get("base_price", 0)),
            ),
            reverse=True,
        )
        best = scored[0]
        return json.dumps({"selected": best.get("id"), "name": best.get("name"), "price": best.get("base_price")})
    except Exception as e:
        return json.dumps({"selected": None, "error": str(e)})


def _tool_validate_dates(start_date: str, end_date: str) -> str:
    """Validates that travel dates are logical and at least 48 hours in the future.

    Args:
        start_date: Travel start date in ISO format (YYYY-MM-DD)
        end_date: Travel end date in ISO format (YYYY-MM-DD)

    Returns:
        JSON string with valid boolean and duration_days
    """
    try:
        start = datetime.fromisoformat(start_date)
        end = datetime.fromisoformat(end_date)
        now = datetime.now()
        days = (end - start).days
        min_advance = (start - now).days

        return json.dumps({
            "valid": days > 0 and min_advance >= 2,
            "duration_days": days,
            "advance_days": min_advance,
            "issues": [] if (days > 0 and min_advance >= 2) else (
                ["duration_must_be_positive"] if days <= 0 else ["needs_48h_advance"]
            ),
        })
    except Exception as e:
        return json.dumps({"valid": False, "error": str(e)})


def _tool_build_customizations(preferences_list: str, budget_min: float, budget_max: float) -> str:
    """Builds a customizations dict from client preferences and budget constraints.

    Args:
        preferences_list: JSON array of preference strings (e.g. ["hotel 4*", "vuelo incluido"])
        budget_min: Minimum budget in PEN
        budget_max: Maximum budget in PEN

    Returns:
        JSON string with structured customizations dict
    """
    try:
        prefs = json.loads(preferences_list) if isinstance(preferences_list, str) else preferences_list
        return json.dumps({
            "hotel_category": next((p for p in prefs if "hotel" in p.lower()), None),
            "includes_flight": any("vuelo" in p.lower() or "flight" in p.lower() for p in prefs),
            "includes_transfer": any("traslado" in p.lower() or "transfer" in p.lower() for p in prefs),
            "budget_range": {"min": budget_min, "max": budget_max},
            "raw_preferences": prefs,
        })
    except Exception as e:
        return json.dumps({"budget_range": {"min": budget_min, "max": budget_max}, "error": str(e)})


# ── Agent ─────────────────────────────────────────────────────────────────────

class SalesAgent(BaseAgent):
    agent_id = "sales-agent"
    queue_name = "sales-events"
    system_prompt_file = "agents/sales/prompts/system_prompt.txt"

    def __init__(self) -> None:
        super().__init__()
        self._swarm_agent: Agent | None = None  # se crea en initialize() tras cargar el prompt
        self._http = httpx.AsyncClient(base_url=DB_API_URL, timeout=30)

    async def initialize(self) -> None:
        """Extiende initialize() de BaseAgent para crear el Agent de Swarms."""
        await super().initialize()  # carga system_prompt, conecta Redis/RabbitMQ

        # FASE 1: Instanciar swarms.Agent con tools nativos
        self._swarm_agent = Agent(
            agent_name="sales-agent-et",
            system_prompt=self._system_prompt,
            model_name=LLM_MODEL,
            max_loops=1,                        # una pasada por mensaje
            tools=[                             # herramientas nativas de Swarms
                _tool_select_package,
                _tool_validate_dates,
                _tool_build_customizations,
                _tool_semantic_search_packages,  # RAG: búsqueda semántica sobre pgvector
            ],
            memory_chunk_size=2000,            # Swarms gestiona el historial de conversación
            output_type="str",
            verbose=False,
            temperature=0.1,                   # respuestas determinísticas para JSON
            response_schema=PackageRequest.model_json_schema(),  # fuerza JSON schema (Ollama constrained decoding)
        )
        logger.info("[Sales] Swarms Agent (Fase 1) inicializado con 4 tools")

    def _register_handlers(self) -> None:
        self._consumer.register_handler("PackageInquiry", self.handle_message)
        self._consumer.register_handler("QuotationResult", self._handle_quotation_result)

    async def handle_message(self, envelope: MCPEnvelope) -> None:
        inquiry_data = envelope.payload
        client_id = inquiry_data.get("client_id")

        logger.info(
            f"[Sales] Consulta recibida | cliente={client_id} "
            f"destino={inquiry_data.get('destination')}"
        )

        client_memory = await self._redis.get_client_memory(client_id)
        matching_packages = await self._search_catalog(inquiry_data)

        package_request = await self._build_package_request_swarms(
            inquiry_data, matching_packages, client_memory, saga_id=envelope.saga_id
        )

        await self._redis.set_client_memory(client_id, {
            **client_memory,
            "last_inquiry": inquiry_data,
            "last_destination": inquiry_data.get("destination"),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })

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
        packages = await self._search_catalog_structured(inquiry)
        if packages:
            return packages

        # RAG fallback: la búsqueda estructurada (filtro exacto de destino + presupuesto)
        # no encontró nada — puede ser un destino mal escrito, una variación de nombre
        # ("Cusco" vs "Cuzco, Perú") o preferencias descriptivas que un `ilike` no
        # captura. Recuperamos por similaridad semántica sobre el embedding del paquete.
        logger.info("[Sales] Búsqueda estructurada vacía; intentando RAG semantic-search")
        return await self._search_catalog_semantic(inquiry)

    async def _search_catalog_structured(self, inquiry: dict) -> list[dict]:
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

    async def _search_catalog_semantic(self, inquiry: dict) -> list[dict]:
        preferences = " ".join(inquiry.get("preferences", []))
        query = f"{inquiry.get('destination', '')} {preferences}".strip()
        if not query:
            return []
        try:
            resp = await self._http.get(
                "/api/v1/packages/semantic-search",
                params={"query": query, "top_k": 5},
            )
            if resp.status_code == 200:
                packages = resp.json().get("packages", [])
                budget_max = inquiry.get("budget_max")
                if budget_max:
                    packages = [p for p in packages if float(p.get("base_price", 0)) <= budget_max] or packages
                return packages
            if resp.status_code == 503:
                logger.info("[Sales] RAG semantic-search no disponible (Ollama caído); catálogo vacío")
        except Exception as e:
            logger.warning(f"[Sales] Error en semantic-search: {e}")
        return []

    async def _build_package_request_swarms(
        self, inquiry: dict, packages: list, memory: dict, saga_id: str | None = None
    ) -> dict:
        """
        FASE 1 — Usa swarms.Agent en lugar del SDK de Anthropic directamente.

        El Agent de Swarms:
        - Invoca _tool_select_package, _tool_validate_dates, _tool_build_customizations según necesite
        - Mantiene memoria conversacional automáticamente
        - Reintenta ante errores de red
        - asyncio.to_thread() evita bloquear el event loop
        """
        if packages:
            logger.info("[Sales] Paquete de catálogo encontrado; usando selección determinística")
            return self._fallback_package_request(inquiry, packages)

        prompt = (
            f"Client inquiry: {json.dumps(inquiry)}\n"
            f"Available packages: {json.dumps(packages[:5])}\n"
            f"Client memory (past interactions): {json.dumps(memory)}\n\n"
            "Use the available tools to:\n"
            "1. Validate the travel dates\n"
            "2. Select the best matching package\n"
            "3. Build customizations from preferences\n"
            "Then return ONLY a valid PackageRequest JSON object with keys: "
            "client_id, package_template_id, destination, start_date, end_date, "
            "traveler_count, customizations, budget_range (min/max), priority"
        )

        start = time.perf_counter()
        try:
            # asyncio.to_thread porque Agent.run() es síncrono
            raw_output = await asyncio.to_thread(self._swarm_agent.run, prompt)
            result = self._parse_json_output(raw_output, inquiry, packages)
            await self.report_llm_interaction(
                "build_package_request", input_data=inquiry, output_data=result,
                duration_ms=int((time.perf_counter() - start) * 1000),
                success=True, saga_id=saga_id,
            )
            return result
        except Exception as e:
            logger.warning(f"[Sales] Swarms Agent falló ({type(e).__name__}), usando fallback")
            await self.report_llm_interaction(
                "build_package_request", input_data=inquiry,
                duration_ms=int((time.perf_counter() - start) * 1000),
                success=False, error=str(e), saga_id=saga_id,
            )
            return self._fallback_package_request(inquiry, packages)

    def _parse_json_output(self, raw: str, inquiry: dict, packages: list) -> dict:
        """Valida la salida del LLM contra el schema PackageRequest (ver
        core/mcp/envelope.py). El schema ya se fuerza en generación (Ollama
        constrained decoding, ver response_schema en initialize()); esto es
        la segunda capa de defensa — valida de verdad, no solo extrae texto."""
        parsed = parse_structured_output(raw, PackageRequest)
        if parsed is None:
            logger.warning("[Sales] Salida del LLM no validó contra PackageRequest, usando fallback")
            return self._fallback_package_request(inquiry, packages)
        data = parsed.model_dump()
        data["inquiry_id"] = str(uuid.uuid4())
        return data

    def _fallback_package_request(self, inquiry: dict, packages: list) -> dict:
        selected_package = packages[0] if packages else None
        return {
            "inquiry_id": str(uuid.uuid4()),
            "client_id": inquiry.get("client_id"),
            "package_template_id": selected_package["id"] if selected_package else None,
            "destination": inquiry.get("destination"),
            "start_date": inquiry.get("start_date"),
            "end_date": inquiry.get("end_date"),
            "traveler_count": inquiry.get("traveler_count", 1),
            "customizations": {
                "preferences": inquiry.get("preferences", []),
                "selected_package_name": selected_package.get("name") if selected_package else None,
            },
            "budget_range": {"min": inquiry.get("budget_min", 0), "max": inquiry.get("budget_max", 9999)},
            "priority": "NORMAL",
        }

    async def _handle_quotation_result(self, envelope: MCPEnvelope) -> None:
        result = envelope.payload
        logger.info(f"[Sales] Cotización recibida: quote_id={result.get('quote_id')} status={result.get('status')}")
        await self._redis.publish_realtime(
            f"client:{result.get('client_id')}",
            {"event": "quotation_ready", "data": result},
        )
        await self._redis.publish_realtime(
            "system:alerts",
            {
                "type": "QuotationReady",
                "message": f"Cotización {result.get('quote_id')} lista ({result.get('status')})",
                "data": result,
            },
        )

    def _days_between(self, start: str | None, end: str | None) -> int:
        if not start or not end:
            return 0
        try:
            return max(0, (datetime.fromisoformat(end) - datetime.fromisoformat(start)).days)
        except Exception:
            return 0


if __name__ == "__main__":
    from core.logging_config import configure_logging
    configure_logging("sales-agent")
    agent = SalesAgent()
    asyncio.run(agent.run())
