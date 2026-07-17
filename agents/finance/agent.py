"""
Finance Agent — Liquidaciones, cronogramas de pago y comisiones.

Responsabilidades exclusivas:
- Generación de cronogramas de pago por política
- Ledger de transacciones con audit trail completo
- Cálculo de comisiones por agente de ventas
- Detección de pagos vencidos (evento PaymentOverdue)
- Emisión de LiquidationRecord al completarse el pago
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

import httpx

from agents.base_agent import BaseAgent
from core.mcp.envelope import MCPEnvelope

logger = logging.getLogger(__name__)

COMMISSION_RATE = Decimal("0.08")
DB_API_URL = os.environ.get("DB_API_URL", "http://api:8000")


class FinanceAgent(BaseAgent):
    agent_id = "finance-agent"
    queue_name = "finance-events"
    system_prompt_file = "agents/finance/prompts/system_prompt.txt"

    def __init__(self) -> None:
        super().__init__()
        self._http = httpx.AsyncClient(base_url=DB_API_URL, timeout=30)

    def _register_handlers(self) -> None:
        self._consumer.register_handler("ReservationRecord", self.handle_message)
        self._consumer.register_handler("PaymentEvent", self._handle_payment)

    async def handle_message(self, envelope: MCPEnvelope) -> None:
        """Recibe ReservationRecord y genera cronograma + liquidación inicial."""
        reservation = envelope.payload
        reservation_code = reservation.get("reservation_code")
        total_cost = Decimal(str(reservation.get("total_cost", 0)))

        logger.info(
            f"[Finance] Procesando reserva: {reservation_code} "
            f"total={total_cost}"
        )

        # 1. Calcular cronograma de pagos
        schedule = self._build_payment_schedule(
            total_cost,
            reservation.get("travel_start"),
        )

        # 2. Calcular comisión
        commission = (total_cost * COMMISSION_RATE).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        # 3. Crear liquidación inicial
        liquidation_code = f"LIQ-{uuid.uuid4().hex[:8].upper()}"
        liquidation = {
            "liquidation_id": str(uuid.uuid4()),
            "liquidation_code": liquidation_code,
            "reservation_code": reservation_code,
            "total_charged": float(total_cost),
            "total_paid": 0.0,
            "commission_amount": float(commission),
            "status": "PARTIAL",
            "transactions": [],
            "payment_schedule": schedule,
        }

        # 4. Persistir
        await self._save_liquidation(liquidation)

        # 5. Publicar cronograma vía Redis para el dashboard
        await self._redis.publish_realtime(
            f"client:{reservation.get('client_id')}",
            {"event": "payment_schedule_ready", "data": schedule},
        )

        # 6. Generar documento INVOICE
        await self.publish(
            payload_type="DocumentJob",
            payload={
                "job_id": str(uuid.uuid4()),
                "document_type": "INVOICE",
                "reference_id": reservation_code,
                "reference_type": "reservation",
                "template_data": {
                    **reservation,
                    "liquidation": liquidation,
                    "payment_schedule": schedule,
                },
                "priority": "NORMAL",
                "requested_by": self.agent_id,
            },
            receiver_agent="document-agent",
            routing_key="document.generate",
            saga_id=envelope.saga_id,
        )

        await self._saga.record_step(
            envelope.saga_id, "finance_liquidation_created",
            self.agent_id, "COMPLETED",
            output_ref=f"liquidation:{liquidation_code}",
        )
        self._messages_processed += 1

    async def _handle_payment(self, envelope: MCPEnvelope) -> None:
        """Registra un pago recibido y verifica si la liquidación está completa."""
        payment = envelope.payload
        reservation_code = payment.get("reservation_code")
        amount = Decimal(str(payment.get("amount", 0)))

        logger.info(
            f"[Finance] Pago recibido: {amount} PEN para {reservation_code}"
        )

        # 1. Registrar transacción
        transaction = {
            "id": str(uuid.uuid4()),
            "liquidation_reservation": reservation_code,
            "amount": float(amount),
            "payment_method": payment.get("method", "TRANSFER"),
            "reference": payment.get("reference", ""),
            "recorded_by_agent": self.agent_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        updated_liquidation = await self._record_transaction(
            reservation_code, transaction
        )

        if not updated_liquidation:
            logger.warning(f"[Finance] Liquidación no encontrada: {reservation_code}")
            return

        total_paid = Decimal(str(updated_liquidation.get("total_paid", 0)))
        total_charged = Decimal(str(updated_liquidation.get("total_charged", 1)))

        # 2. Si balance == 0, completar liquidación
        if total_paid >= total_charged:
            await self._complete_liquidation(
                updated_liquidation, envelope.saga_id
            )

    async def _complete_liquidation(
        self, liquidation: dict, saga_id: str
    ) -> None:
        liquidation_id = liquidation.get("liquidation_id")
        reservation_code = liquidation.get("reservation_code")

        logger.info(f"[Finance] Liquidación completa: {reservation_code}")

        updated = {
            **liquidation,
            "status": "COMPLETE",
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }

        # Publicar LiquidationComplete
        await self.publish(
            payload_type="LiquidationRecord",
            payload={
                "liquidation_id": liquidation_id,
                "reservation_code": reservation_code,
                "total_charged": liquidation.get("total_charged"),
                "total_paid": liquidation.get("total_paid"),
                "commission_amount": liquidation.get("commission_amount"),
                "status": "COMPLETE",
                "transactions": liquidation.get("transactions", []),
            },
            receiver_agent="document-agent",
            routing_key="document.generate",
            saga_id=saga_id,
        )

        # Documento de liquidación
        await self.publish(
            payload_type="DocumentJob",
            payload={
                "job_id": str(uuid.uuid4()),
                "document_type": "LIQUIDATION",
                "reference_id": reservation_code,
                "reference_type": "liquidation",
                "template_data": updated,
                "priority": "HIGH",
                "requested_by": self.agent_id,
            },
            receiver_agent="document-agent",
            routing_key="document.generate",
            saga_id=saga_id,
        )

        await self._saga.complete_saga(saga_id)

    def _build_payment_schedule(
        self, total: Decimal, travel_start: str | None
    ) -> list[dict]:
        now = datetime.now(timezone.utc)
        travel_dt = datetime.fromisoformat(travel_start) if travel_start else now + timedelta(days=90)

        if total <= Decimal("1000"):
            return [{"due_date": now.isoformat(), "amount": float(total), "pct": 100}]
        elif total <= Decimal("5000"):
            return [
                {"due_date": now.isoformat(), "amount": float(total * Decimal("0.5")), "pct": 50},
                {"due_date": (travel_dt - timedelta(days=30)).isoformat(), "amount": float(total * Decimal("0.5")), "pct": 50},
            ]
        else:
            return [
                {"due_date": now.isoformat(), "amount": float(total * Decimal("0.3")), "pct": 30},
                {"due_date": (travel_dt - timedelta(days=30)).isoformat(), "amount": float(total * Decimal("0.4")), "pct": 40},
                {"due_date": (travel_dt - timedelta(days=7)).isoformat(), "amount": float(total * Decimal("0.3")), "pct": 30},
            ]

    async def _save_liquidation(self, liquidation: dict) -> None:
        try:
            await self._http.post("/api/v1/liquidations", json=liquidation)
        except Exception as e:
            logger.warning(f"[Finance] Error guardando liquidación: {e}")

    async def _record_transaction(
        self, reservation_code: str, transaction: dict
    ) -> dict | None:
        try:
            resp = await self._http.post(
                f"/api/v1/liquidations/{reservation_code}/transactions",
                json=transaction,
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            logger.warning(f"[Finance] Error registrando transacción: {e}")
        return None


if __name__ == "__main__":
    from core.logging_config import configure_logging
    configure_logging("finance-agent")
    agent = FinanceAgent()
    asyncio.run(agent.run())
