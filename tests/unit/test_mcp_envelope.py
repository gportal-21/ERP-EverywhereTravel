"""
Tests unitarios para el MCP Envelope.
Verifica serialización, validación de agentes y detección de expiración.
"""
import pytest
import time
from datetime import datetime, timezone, timedelta

from core.mcp.envelope import MCPEnvelope, PackageInquiry, QuotationResult


class TestMCPEnvelope:
    def test_valid_envelope_creation(self):
        env = MCPEnvelope(
            saga_id="saga-123",
            sender_agent="sales-agent",
            receiver_agent="quotation-agent",
            payload_type="PackageRequest",
            payload={"client_id": "c1", "destination": "Lima"},
        )
        assert env.message_id is not None
        assert env.correlation_id is not None
        assert env.retry_count == 0

    def test_invalid_sender_agent_raises(self):
        with pytest.raises(ValueError, match="sender_agent inválido"):
            MCPEnvelope(
                saga_id="saga-123",
                sender_agent="unknown-agent",  # inválido
                receiver_agent="quotation-agent",
                payload_type="PackageRequest",
                payload={},
            )

    def test_invalid_receiver_agent_raises(self):
        with pytest.raises(ValueError, match="receiver_agent inválido"):
            MCPEnvelope(
                saga_id="saga-123",
                sender_agent="sales-agent",
                receiver_agent="hacker-agent",  # inválido
                payload_type="PackageRequest",
                payload={},
            )

    def test_envelope_not_expired(self):
        env = MCPEnvelope(
            saga_id="saga-123",
            sender_agent="sales-agent",
            receiver_agent="quotation-agent",
            payload_type="PackageRequest",
            payload={},
            ttl_seconds=300,
        )
        assert not env.is_expired()

    def test_envelope_expired(self):
        past_time = (datetime.now(timezone.utc) - timedelta(seconds=400)).isoformat()
        env = MCPEnvelope(
            saga_id="saga-123",
            sender_agent="sales-agent",
            receiver_agent="quotation-agent",
            payload_type="PackageRequest",
            payload={},
            ttl_seconds=300,
        )
        env.timestamp = past_time
        assert env.is_expired()

    def test_make_reply(self):
        env = MCPEnvelope(
            saga_id="saga-abc",
            sender_agent="sales-agent",
            receiver_agent="quotation-agent",
            payload_type="PackageRequest",
            payload={"key": "value"},
        )
        reply = env.make_reply(
            payload_type="QuotationResult",
            payload={"quote_id": "q1"},
        )
        assert reply.sender_agent == "quotation-agent"
        assert reply.receiver_agent == "sales-agent"
        assert reply.saga_id == "saga-abc"
        assert reply.correlation_id == env.correlation_id
        assert reply.payload_type == "QuotationResult"

    def test_json_serialization(self):
        env = MCPEnvelope(
            saga_id="saga-xyz",
            sender_agent="finance-agent",
            receiver_agent="document-agent",
            payload_type="DocumentJob",
            payload={"job_id": "j1", "document_type": "INVOICE"},
        )
        json_str = env.model_dump_json()
        restored = MCPEnvelope.model_validate_json(json_str)
        assert restored.message_id == env.message_id
        assert restored.saga_id == env.saga_id


class TestPayloadModels:
    def test_package_inquiry_valid(self):
        inquiry = PackageInquiry(
            client_id="client-001",
            destination="Cusco",
            start_date="2026-07-01",
            end_date="2026-07-06",
            budget_min=1500,
            budget_max=2500,
            traveler_count=2,
        )
        assert inquiry.traveler_count == 2

    def test_package_inquiry_max_travelers(self):
        with pytest.raises(Exception):
            PackageInquiry(
                client_id="c1",
                destination="Lima",
                start_date="2026-07-01",
                end_date="2026-07-05",
                budget_min=100,
                budget_max=500,
                traveler_count=51,  # > 50: inválido
            )
