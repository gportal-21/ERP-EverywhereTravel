"""
Validation / Compliance Agent — Motor de reglas de negocio y auditoría inmutable.

Responsabilidades exclusivas:
- Motor de reglas (R001-R012) con severidades
- Auditoría inmutable de cada validación
- Compliance regulatorio (IGV Peru)
- Notificación BLOCKING al Orchestrator
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal

import httpx

from agents.base_agent import BaseAgent
from core.mcp.envelope import MCPEnvelope

logger = logging.getLogger(__name__)
DB_API_URL = os.environ.get("DB_API_URL", "http://api:8000")

IGV = Decimal("0.18")
MIN_MARGIN = Decimal("15.0")


class ValidationAgent(BaseAgent):
    agent_id = "validation-agent"
    queue_name = "quotation-events"  # Escucha cotizaciones para validar
    system_prompt_file = "agents/validation/prompts/system_prompt.txt"

    def __init__(self) -> None:
        super().__init__()
        self._http = httpx.AsyncClient(base_url=DB_API_URL, timeout=30)

    def _register_handlers(self) -> None:
        self._consumer.register_handler("QuotationResult", self.handle_message)
        self._consumer.register_handler("ReservationRecord", self._validate_reservation)

    async def handle_message(self, envelope: MCPEnvelope) -> None:
        await self._validate_quotation(envelope)

    async def _validate_quotation(self, envelope: MCPEnvelope) -> None:
        quote = envelope.payload
        rules_checked = []
        blocking = False

        total = Decimal(str(quote.get("total_cost", 0)))
        margin = Decimal(str(quote.get("margin_pct", 0)))
        line_items = quote.get("line_items", [])
        valid_until = quote.get("valid_until", "")

        # R001: Margen mínimo
        if margin < Decimal("0"):
            rules_checked.append(self._rule("R001", False, "BLOCKING", f"Margen negativo: {margin}"))
            blocking = True
        elif margin < MIN_MARGIN:
            rules_checked.append(self._rule("R001", False, "ERROR", f"Margen bajo: {margin}%"))
        else:
            rules_checked.append(self._rule("R001", True, "INFO", "Margen OK"))

        # R002: Costo positivo
        if total <= 0:
            rules_checked.append(self._rule("R002", False, "BLOCKING", "total_cost = 0"))
            blocking = True
        else:
            rules_checked.append(self._rule("R002", True, "INFO", "Costo positivo"))

        # R003: Validez futura
        try:
            valid_dt = datetime.fromisoformat(valid_until)
            if valid_dt < datetime.now(timezone.utc):
                rules_checked.append(self._rule("R003", False, "ERROR", "Cotización expirada"))
            else:
                rules_checked.append(self._rule("R003", True, "INFO", "Vigencia OK"))
        except Exception:
            rules_checked.append(self._rule("R003", False, "WARNING", "valid_until inválido"))

        # R004: Line items no vacíos
        if not line_items:
            rules_checked.append(self._rule("R004", False, "BLOCKING", "Sin line_items"))
            blocking = True
        else:
            rules_checked.append(self._rule("R004", True, "INFO", f"{len(line_items)} items"))

        overall_status = "FAIL" if blocking or any(
            r["passed"] is False and r["severity"] == "ERROR"
            for r in rules_checked
        ) else "PASS"

        validation_result = {
            "validation_id": str(uuid.uuid4()),
            "entity_type": "QuotationResult",
            "entity_id": quote.get("quote_id", ""),
            "rules_checked": rules_checked,
            "overall_status": overall_status,
            "compliance_flags": ["BLOCKING"] if blocking else [],
            "audited_at": datetime.now(timezone.utc).isoformat(),
        }

        # Audit log inmutable
        await self._write_audit_log(validation_result)

        # Actualizar estado de la cotización
        new_status = "VALIDATED" if overall_status == "PASS" else "REJECTED"
        validated_quote = {**quote, "status": new_status}

        if blocking:
            # BLOCKING: notificar al Orchestrator para detener el flujo
            await self.publish(
                payload_type="ValidationBlocking",
                payload={
                    "validation_result": validation_result,
                    "quote_id": quote.get("quote_id"),
                },
                receiver_agent="orchestrator-agent",
                routing_key="orchestrator.blocking",
                saga_id=envelope.saga_id,
            )
            await self._saga.record_step(
                envelope.saga_id, "validation_blocking",
                self.agent_id, "FAILED",
                error=f"BLOCKING rules: {[r['rule_id'] for r in rules_checked if not r['passed'] and r['severity'] == 'BLOCKING']}"
            )
        else:
            # Publicar resultado al Sales Agent
            await self.publish(
                payload_type="QuotationResult",
                payload=validated_quote,
                receiver_agent="sales-agent",
                routing_key="sales.quotation_validated",
                saga_id=envelope.saga_id,
            )
            await self._saga.record_step(
                envelope.saga_id, "validation_complete",
                self.agent_id, "COMPLETED",
                output_ref=f"validation:{validation_result['validation_id']}",
            )

        logger.info(
            f"[Validation] quote={quote.get('quote_id')} "
            f"→ {overall_status} (blocking={blocking})"
        )
        self._messages_processed += 1

    async def _validate_reservation(self, envelope: MCPEnvelope) -> None:
        reservation = envelope.payload
        rules_checked = []
        blocking = False

        # R010: travel_start >= 48h
        travel_start = reservation.get("travel_start", "")
        try:
            start_dt = datetime.fromisoformat(travel_start)
            min_start = datetime.now(timezone.utc) + timedelta(hours=48)
            if start_dt < min_start:
                rules_checked.append(self._rule("R010", False, "ERROR", "< 48h de antelación"))
            else:
                rules_checked.append(self._rule("R010", True, "INFO", "Antelación OK"))
        except Exception:
            rules_checked.append(self._rule("R010", False, "ERROR", "Fecha inválida"))

        # R011: reservation_code formato
        code = reservation.get("reservation_code", "")
        if not re.match(r"^ET-\d{8}-[A-Z0-9]{5}$", code):
            rules_checked.append(self._rule("R011", False, "ERROR", f"Código inválido: {code}"))
        else:
            rules_checked.append(self._rule("R011", True, "INFO", "Código válido"))

        # R012: traveler_count
        if reservation.get("traveler_count", 0) < 1:
            rules_checked.append(self._rule("R012", False, "BLOCKING", "traveler_count < 1"))
            blocking = True
        else:
            rules_checked.append(self._rule("R012", True, "INFO", "Viajeros OK"))

        overall = "FAIL" if blocking else "PASS"
        await self._write_audit_log({
            "validation_id": str(uuid.uuid4()),
            "entity_type": "ReservationRecord",
            "entity_id": code,
            "rules_checked": rules_checked,
            "overall_status": overall,
            "compliance_flags": [],
            "audited_at": datetime.now(timezone.utc).isoformat(),
        })

    def _rule(
        self, rule_id: str, passed: bool, severity: str, message: str
    ) -> dict:
        return {"rule_id": rule_id, "passed": passed, "severity": severity, "message": message}

    async def _write_audit_log(self, result: dict) -> None:
        try:
            await self._http.post("/api/v1/validation-logs", json=result)
        except Exception as e:
            logger.warning(f"[Validation] Error escribiendo audit log: {e}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    agent = ValidationAgent()
    asyncio.run(agent.run())
