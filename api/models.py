"""SQLAlchemy models — mapeo directo del schema PostgreSQL."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, ForeignKey,
    Integer, JSON, Numeric, String, Text
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from api.database import Base


def gen_uuid():
    return str(uuid.uuid4())


class Client(Base):
    __tablename__ = "clients"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    full_name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    phone = Column(String(50))
    document_type = Column(String(20))
    document_number = Column(String(50), unique=True)
    preferences = Column(JSON, default={})
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Package(Base):
    __tablename__ = "packages"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    name = Column(String(255), nullable=False)
    package_type = Column(String(20), default="PREDEFINED")
    destination = Column(String(255), nullable=False)
    description = Column(Text)
    base_price = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(3), default="PEN")
    duration_days = Column(Integer, nullable=False)
    includes = Column(JSON, default=[])
    excludes = Column(JSON, default=[])
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Quotation(Base):
    __tablename__ = "quotations"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    quote_id = Column(UUID(as_uuid=False), nullable=False)
    version = Column(Integer, default=1)
    client_id = Column(UUID(as_uuid=False), ForeignKey("clients.id"))
    package_id = Column(UUID(as_uuid=False), ForeignKey("packages.id"), nullable=True)
    line_items = Column(JSON, default=[])
    total_cost = Column(Numeric(12, 2), nullable=False)
    margin_pct = Column(Numeric(5, 2), nullable=False)
    currency = Column(String(3), default="PEN")
    valid_until = Column(DateTime(timezone=True), nullable=False)
    status = Column(String(20), default="DRAFT")
    customizations = Column(JSON, default={})
    created_by_agent = Column(String(100))
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Reservation(Base):
    __tablename__ = "reservations"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    reservation_code = Column(String(20), unique=True, nullable=False)
    quote_id = Column(UUID(as_uuid=False), nullable=False)
    client_id = Column(UUID(as_uuid=False), ForeignKey("clients.id"))
    package_id = Column(UUID(as_uuid=False), ForeignKey("packages.id"), nullable=True)
    travel_start = Column(DateTime(timezone=True), nullable=False)
    travel_end = Column(DateTime(timezone=True), nullable=False)
    traveler_count = Column(Integer, default=1)
    status = Column(String(20), default="PENDING_PAYMENT")
    version = Column(Integer, default=1)
    notes = Column(Text)
    created_by_agent = Column(String(100))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Liquidation(Base):
    __tablename__ = "liquidations"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    liquidation_code = Column(String(20), unique=True, nullable=False)
    reservation_id = Column(UUID(as_uuid=False), ForeignKey("reservations.id"))
    total_charged = Column(Numeric(12, 2), nullable=False)
    total_paid = Column(Numeric(12, 2), default=0)
    commission_amount = Column(Numeric(12, 2), default=0)
    commission_agent_id = Column(String(100))
    status = Column(String(20), default="PARTIAL")
    payment_schedule = Column(JSON, default=[])
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    liquidation_id = Column(UUID(as_uuid=False), ForeignKey("liquidations.id"))
    amount = Column(Numeric(12, 2), nullable=False)
    payment_method = Column(String(50), nullable=False)
    reference = Column(String(255))
    recorded_by_agent = Column(String(100))
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DocumentJob(Base):
    __tablename__ = "document_jobs"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    document_type = Column(String(20), nullable=False)
    reference_id = Column(UUID(as_uuid=False))
    reference_type = Column(String(100))
    template_data = Column(JSON, nullable=False)
    priority = Column(String(20), default="NORMAL")
    status = Column(String(20), default="QUEUED")
    retry_count = Column(Integer, default=0)
    error_message = Column(Text)
    requested_by_agent = Column(String(100))
    document_url = Column(Text)
    expires_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True))


class Saga(Base):
    __tablename__ = "sagas"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    saga_type = Column(String(100), nullable=False)
    status = Column(String(30), default="RUNNING")
    initiated_by = Column(String(100))
    context = Column(JSON, default={})
    steps = Column(JSON, default=[])
    error_message = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True))


class ValidationLog(Base):
    __tablename__ = "validation_logs"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    entity_type = Column(String(100), nullable=False)
    entity_id = Column(UUID(as_uuid=False), nullable=False)
    rules_checked = Column(JSON, nullable=False)
    overall_status = Column(String(10), nullable=False)
    compliance_flags = Column(JSON, default=[])
    audited_by_agent = Column(String(100))
    audited_at = Column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    username = Column(String(100), unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(50), default="sales_agent")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
