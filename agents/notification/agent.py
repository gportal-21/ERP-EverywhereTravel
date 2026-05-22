"""
Notification Agent — Centraliza y entrega notificaciones internas.

Responsabilidades exclusivas:
- Consumir eventos del bus y transformarlos en notificaciones
- Deduplicación de notificaciones (ventana 60s por evento)
- Routing: WebSocket dashboard / email
- Log de entregas
"""
from __future__ import annotations

import asyncio
import logging
import os

import httpx

from agents.base_agent import BaseAgent
from core.mcp.envelope import MCPEnvelope

logger = logging.getLogger(__name__)
DB_API_URL = os.environ.get("DB_API_URL", "http://api:8000")

EVENT_TEMPLATES = {
    "DocumentReady":      "Documento disponible: {document_type}. Descarga: {document_url}",
    "ReservationConfirmed": "Reserva {reservation_code} confirmada. Viaje: {travel_start}",
    "PaymentOverdue":     "ALERTA: Pago vencido — Reserva {reservation_code}",
    "AgentDegraded":      "ALERTA SISTEMA: Agente {agent_id} degradado",
    "ValidationFailed":   "Validación fallida para cotización {quote_id}",
    "ItineraryReady":     "Itinerario listo para {destination}. Descarga: {itinerary_url}",
}


class NotificationAgent(BaseAgent):
    agent_id = "notification-agent"
    queue_name = "notification-events"
    system_prompt_file = "agents/notification/prompts/system_prompt.txt"

    def __init__(self) -> None:
        super().__init__()
        self._http = httpx.AsyncClient(base_url=DB_API_URL, timeout=30)

    def _register_handlers(self) -> None:
        for event_type in EVENT_TEMPLATES:
            self._consumer.register_handler(event_type, self.handle_message)
        self._consumer.register_handler("DocumentReady", self.handle_message)

    async def handle_message(self, envelope: MCPEnvelope) -> None:
        event_type = envelope.payload_type
        payload = envelope.payload

        # Deduplicación: clave por tipo + reference_id con TTL 60s
        ref_id = (
            payload.get("reference_id") or
            payload.get("reservation_code") or
            payload.get("quote_id") or
            envelope.saga_id
        )
        dedup_key = f"notif:{event_type}:{ref_id}"
        is_new = await self._redis._r.set(dedup_key, "1", ex=60, nx=True)
        if not is_new:
            logger.debug(f"[Notification] Notificación duplicada ignorada: {dedup_key}")
            return

        # Construir mensaje
        template = EVENT_TEMPLATES.get(event_type, "Evento: {event_type}")
        try:
            message = template.format(event_type=event_type, **payload)
        except KeyError:
            message = f"[{event_type}] {payload}"

        # Determinar canal de entrega
        channel = self._resolve_channel(event_type, payload)

        # Entregar vía Redis pub/sub al WebSocket
        await self._redis.publish_realtime(
            channel,
            {
                "type": event_type,
                "message": message,
                "data": payload,
                "saga_id": envelope.saga_id,
            },
        )

        # Eventos de alta prioridad también van a email
        if event_type in ("PaymentOverdue", "AgentDegraded"):
            await self._send_email_alert(event_type, message, payload)

        self._messages_processed += 1
        logger.info(f"[Notification] Entregado [{event_type}] → {channel}")

    def _resolve_channel(self, event_type: str, payload: dict) -> str:
        if event_type in ("AgentDegraded",):
            return "system:alerts"
        client_id = payload.get("client_id")
        if client_id:
            return f"client:{client_id}"
        return "system:alerts"

    async def _send_email_alert(
        self, event_type: str, message: str, payload: dict
    ) -> None:
        try:
            await self._http.post(
                "/api/v1/notifications/email",
                json={
                    "subject": f"Everywhere Travel — {event_type}",
                    "body": message,
                    "recipient": "admin@everywheretravel.com",
                    "payload": payload,
                },
            )
        except Exception as e:
            logger.warning(f"[Notification] Error enviando email: {e}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    agent = NotificationAgent()
    asyncio.run(agent.run())
