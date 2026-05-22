"""
MCP Validator — Validación de mensajes inter-agente con JSON Schema Draft-07.
Cada payload_type tiene su schema registrado. Mensajes inválidos son rechazados
antes de ser procesados por el agente receptor.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import jsonschema
from jsonschema import ValidationError

from core.mcp.envelope import MCPEnvelope

logger = logging.getLogger(__name__)

SCHEMAS_DIR = Path(__file__).parent.parent.parent / "schemas"

# Registro de schemas por payload_type
PAYLOAD_SCHEMA_MAP: dict[str, str] = {
    "PackageInquiry": "package_inquiry.json",
    "PackageRequest": "package_request.json",
    "QuotationResult": "quotation_result.json",
    "ReservationRecord": "reservation_record.json",
    "LiquidationRecord": "liquidation_record.json",
    "DocumentJob": "document_job.json",
    "ValidationResult": "validation_result.json",
    "SagaCommand": "saga_command.json",
    "AgentHeartbeat": "agent_heartbeat.json",
    "ConflictNotification": "conflict_notification.json",
}

_schema_cache: dict[str, dict] = {}


def _load_schema(schema_file: str) -> dict:
    if schema_file not in _schema_cache:
        path = SCHEMAS_DIR / schema_file
        if not path.exists():
            logger.warning(f"Schema no encontrado: {path}. Saltando validación.")
            return {}
        with open(path) as f:
            _schema_cache[schema_file] = json.load(f)
    return _schema_cache[schema_file]


def validate_envelope(envelope: MCPEnvelope) -> list[str]:
    """Valida el payload del envelope contra su JSON Schema registrado.
    Retorna lista de errores (vacía = válido)."""
    errors: list[str] = []

    if envelope.is_expired():
        errors.append(f"Mensaje expirado: TTL={envelope.ttl_seconds}s superado")
        return errors

    schema_file = PAYLOAD_SCHEMA_MAP.get(envelope.payload_type)
    if not schema_file:
        logger.warning(f"payload_type sin schema registrado: {envelope.payload_type}")
        return errors

    schema = _load_schema(schema_file)
    if not schema:
        return errors

    try:
        jsonschema.validate(instance=envelope.payload, schema=schema)
    except ValidationError as e:
        errors.append(f"Schema violation [{envelope.payload_type}]: {e.message}")

    return errors


def validate_or_raise(envelope: MCPEnvelope) -> None:
    errors = validate_envelope(envelope)
    if errors:
        raise MCPValidationError(
            f"Envelope inválido (message_id={envelope.message_id}): {errors}"
        )


class MCPValidationError(Exception):
    pass
