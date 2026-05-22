"""
MCP Envelope — Contrato base de comunicación entre agentes.
Todo mensaje inter-agente DEBE empaquetarse con esta estructura.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, model_validator


class MCPEnvelope(BaseModel):
    """Envelope estándar para todos los mensajes MCP del sistema."""

    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    saga_id: str
    sender_agent: str
    receiver_agent: str
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    correlation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    payload_type: str
    payload: dict[str, Any]
    retry_count: int = Field(default=0, ge=0, le=10)
    ttl_seconds: int = Field(default=300, gt=0)
    priority: int = Field(default=5, ge=1, le=10)

    class Config:
        json_schema_extra = {
            "$schema": "https://everywheretravel.internal/schemas/mcp-envelope/v1"
        }

    @model_validator(mode="after")
    def validate_agents(self) -> "MCPEnvelope":
        valid_agents = {
            "orchestrator-agent", "sales-agent", "quotation-agent",
            "reservation-agent", "finance-agent", "document-agent",
            "validation-agent", "monitoring-agent", "notification-agent",
            "itinerary-agent", "api-gateway",
        }
        if self.sender_agent not in valid_agents:
            raise ValueError(f"sender_agent inválido: {self.sender_agent}")
        if self.receiver_agent not in valid_agents:
            raise ValueError(f"receiver_agent inválido: {self.receiver_agent}")
        return self

    def is_expired(self) -> bool:
        sent_at = datetime.fromisoformat(self.timestamp)
        elapsed = (datetime.now(timezone.utc) - sent_at).total_seconds()
        return elapsed > self.ttl_seconds

    def make_reply(
        self,
        payload_type: str,
        payload: dict[str, Any],
        receiver_agent: str | None = None,
    ) -> "MCPEnvelope":
        return MCPEnvelope(
            saga_id=self.saga_id,
            sender_agent=self.receiver_agent,
            receiver_agent=receiver_agent or self.sender_agent,
            correlation_id=self.correlation_id,
            payload_type=payload_type,
            payload=payload,
        )


# ─── Payloads tipados ─────────────────────────────────────────────────────────

class PackageInquiry(BaseModel):
    client_id: str
    destination: str
    start_date: str
    end_date: str
    budget_min: float
    budget_max: float
    traveler_count: int = Field(ge=1, le=50)
    preferences: list[str] = []
    inquiry_source: str = "dashboard"


class PackageRequest(BaseModel):
    inquiry_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_id: str
    package_template_id: str | None = None
    destination: str
    start_date: str
    end_date: str
    traveler_count: int
    customizations: dict[str, Any] = {}
    budget_range: dict[str, float]
    priority: str = "NORMAL"


class LineItem(BaseModel):
    concept: str
    unit_price: float
    quantity: int
    subtotal: float


class QuotationResult(BaseModel):
    quote_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    version: int = 1
    package_id: str | None
    client_id: str
    line_items: list[LineItem]
    total_cost: float
    margin_pct: float
    currency: str = "PEN"
    valid_until: str
    status: str = "DRAFT"
    anomaly_flags: list[str] = []


class ReservationRecord(BaseModel):
    reservation_code: str
    quote_id: str
    client_id: str
    package_id: str | None
    travel_start: str
    travel_end: str
    traveler_count: int
    status: str = "PENDING_PAYMENT"
    version: int = 1
    created_by_agent: str = "reservation-agent"


class LiquidationRecord(BaseModel):
    liquidation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    reservation_code: str
    total_charged: float
    total_paid: float
    commission_amount: float
    status: str = "PARTIAL"
    transactions: list[dict[str, Any]] = []


class DocumentJob(BaseModel):
    job_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    document_type: str
    reference_id: str
    reference_type: str
    template_data: dict[str, Any]
    priority: str = "NORMAL"
    requested_by: str


class ValidationResult(BaseModel):
    validation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    entity_type: str
    entity_id: str
    rules_checked: list[dict[str, Any]]
    overall_status: str
    compliance_flags: list[str] = []
    audited_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class SagaStep(BaseModel):
    step_name: str
    agent: str
    status: str
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    output_ref: str | None = None
    error: str | None = None
