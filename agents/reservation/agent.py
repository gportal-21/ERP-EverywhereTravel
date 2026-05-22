"""
Reservation Agent — Convierte cotizaciones aprobadas en reservas atómicas.

Responsabilidades exclusivas:
- Verificación y lock de disponibilidad (Redis SETNX atómico)
- Creación de ReservationRecord con código único
- Publicación del evento ReservationCreated
- Trigger a Finance Agent para cronograma de pagos
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone, timedelta

import httpx

from agents.base_agent import BaseAgent
from core.mcp.envelope import MCPEnvelope

logger = logging.getLogger(__name__)
DB_API_URL = os.environ.get("DB_API_URL", "http://api:8000")


class ReservationAgent(BaseAgent):
    agent_id = "reservation-agent"
    queue_name = "reservation-events"
    system_prompt_file = "agents/reservation/prompts/system_prompt.txt"

    def __init__(self) -> None:
        super().__init__()
        self._http = httpx.AsyncClient(base_url=DB_API_URL, timeout=30)

    def _register_handlers(self) -> None:
        self._consumer.register_handler("ReservationCreate", self.handle_message)
        self._consumer.register_handler("QuotationResult", self._handle_approved_quote)

    async def handle_message(self, envelope: MCPEnvelope) -> None:
        await self._create_reservation(envelope)

    async def _handle_approved_quote(self, envelope: MCPEnvelope) -> None:
        """Recibe una cotización validada y la convierte en reserva."""
        quote = envelope.payload
        if quote.get("status") != "VALIDATED":
            logger.warning(
                f"[Reservation] Rechazada cotización no validada: "
                f"quote_id={quote.get('quote_id')} status={quote.get('status')}"
            )
            return
        await self._create_reservation(envelope)

    async def _create_reservation(self, envelope: MCPEnvelope) -> None:
        payload = envelope.payload
        quote_id = payload.get("quote_id")
        client_id = payload.get("client_id")
        package_id = payload.get("package_id")

        # 1. Validar que la cotización está VALIDATED
        if payload.get("status") not in ("VALIDATED", None):
            await self._emit_failed(envelope, "Cotización no está VALIDATED")
            return

        # 2. Verificar fechas mínimas (48h adelante)
        travel_start = payload.get("travel_start") or payload.get("start_date")
        if travel_start:
            try:
                start_dt = datetime.fromisoformat(travel_start)
                if start_dt < datetime.now(timezone.utc) + timedelta(hours=48):
                    await self._emit_failed(envelope, "Fechas insuficientes (< 48h)")
                    return
            except ValueError:
                pass

        # 3. Lock atómico de disponibilidad (SETNX)
        lock_key = f"availability:{package_id}:{travel_start}"
        lock_acquired = await self._redis.acquire_lock(
            "availability", f"{package_id}:{travel_start}", self.agent_id
        )
        if not lock_acquired:
            await self._emit_conflict(envelope, package_id)
            return

        try:
            # 4. Generar código único de reserva
            reservation_code = self._generate_code()

            reservation = {
                "reservation_code": reservation_code,
                "quote_id": quote_id,
                "client_id": client_id,
                "package_id": package_id,
                "travel_start": travel_start,
                "travel_end": payload.get("travel_end") or payload.get("end_date"),
                "traveler_count": payload.get("traveler_count", 1),
                "status": "PENDING_PAYMENT",
                "version": 1,
                "created_by_agent": self.agent_id,
            }

            # 5. Persistir reserva
            await self._save_reservation(reservation, payload.get("total_cost", 0))

            # 6. Publicar ReservationCreated
            await self.publish(
                payload_type="ReservationRecord",
                payload=reservation,
                receiver_agent="orchestrator-agent",
                routing_key="finance.reservation_created",
                saga_id=envelope.saga_id,
            )

            await self._saga.record_step(
                envelope.saga_id, "reservation_created",
                self.agent_id, "COMPLETED",
                output_ref=f"reservation:{reservation_code}",
            )
            self._messages_processed += 1
            logger.info(f"[Reservation] Reserva creada: {reservation_code}")

        finally:
            await self._redis.release_lock(
                "availability", f"{package_id}:{travel_start}", self.agent_id
            )

    async def _emit_failed(self, envelope: MCPEnvelope, reason: str) -> None:
        logger.warning(f"[Reservation] Fallida: {reason}")
        await self.publish(
            payload_type="ReservationFailed",
            payload={"reason": reason, "payload": envelope.payload},
            receiver_agent="orchestrator-agent",
            routing_key="orchestrator.route",
            saga_id=envelope.saga_id,
        )
        await self._saga.record_step(
            envelope.saga_id, "reservation_failed",
            self.agent_id, "FAILED", error=reason
        )

    async def _emit_conflict(self, envelope: MCPEnvelope, package_id: str) -> None:
        logger.warning(
            f"[Reservation] Conflicto de disponibilidad: package={package_id}"
        )
        await self.publish(
            payload_type="ConflictNotification",
            payload={
                "entity_type": "availability",
                "entity_id": package_id,
                "agents": [self.agent_id],
                "reason": "Disponibilidad bloqueada por otro proceso",
            },
            receiver_agent="orchestrator-agent",
            routing_key="orchestrator.conflict",
            saga_id=envelope.saga_id,
        )

    async def _save_reservation(self, reservation: dict, total_cost: float) -> None:
        try:
            await self._http.post(
                "/api/v1/reservations",
                json={**reservation, "total_cost": total_cost},
            )
        except Exception as e:
            logger.warning(f"[Reservation] Error persistiendo: {e}")

    def _generate_code(self) -> str:
        date_part = datetime.now().strftime("%Y%m%d")
        random_part = uuid.uuid4().hex[:5].upper()
        return f"ET-{date_part}-{random_part}"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    agent = ReservationAgent()
    asyncio.run(agent.run())
