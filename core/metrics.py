"""
Metrics — Recolección de métricas de rendimiento del sistema multiagente.

Expone:
- Latencia por agente y operación (histograma)
- Token usage LLM por agente (counter)
- Throughput de mensajes procesados (counter)
- Estado de circuit breakers (gauge)
- Sagas activas (gauge)
- Tamaño de dead-letter queue (gauge)

Integración: prometheus_fastapi_instrumentator + métricas custom via prometheus_client.
"""
from __future__ import annotations

import time
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Awaitable, Callable, TypeVar

from prometheus_client import (
    Counter, Gauge, Histogram, Summary, CollectorRegistry, REGISTRY
)

logger = logging.getLogger(__name__)

T = TypeVar("T")

# ─── Definición de métricas Prometheus ───────────────────────────────────────

# Latencia de procesamiento de mensajes por agente
AGENT_MESSAGE_DURATION = Histogram(
    "et_agent_message_duration_seconds",
    "Duración del procesamiento de mensajes por agente",
    ["agent_id", "payload_type"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
)

# Total de mensajes procesados
AGENT_MESSAGES_TOTAL = Counter(
    "et_agent_messages_total",
    "Total de mensajes procesados por agente",
    ["agent_id", "payload_type", "status"],
)

# Errores por agente
AGENT_ERRORS_TOTAL = Counter(
    "et_agent_errors_total",
    "Total de errores por agente",
    ["agent_id", "error_type"],
)

# Token usage LLM
LLM_TOKENS_TOTAL = Counter(
    "et_llm_tokens_total",
    "Total de tokens LLM consumidos por agente",
    ["agent_id", "model", "token_type"],
)

# Latencia de llamadas LLM
LLM_CALL_DURATION = Histogram(
    "et_llm_call_duration_seconds",
    "Duración de llamadas al LLM por agente",
    ["agent_id", "model"],
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0],
)

# Estado de circuit breakers (0=CLOSED, 1=HALF_OPEN, 2=OPEN)
CIRCUIT_BREAKER_STATE = Gauge(
    "et_circuit_breaker_state",
    "Estado del circuit breaker por servicio (0=CLOSED, 1=HALF_OPEN, 2=OPEN)",
    ["service"],
)

# Sagas activas
SAGAS_ACTIVE = Gauge(
    "et_sagas_active_total",
    "Número de sagas en estado RUNNING",
)

SAGAS_COMPLETED = Counter(
    "et_sagas_completed_total",
    "Total de sagas completadas",
    ["saga_type", "outcome"],
)

# Dead-letter queue
DEAD_LETTER_QUEUE_SIZE = Gauge(
    "et_dead_letter_queue_size",
    "Número de mensajes en la dead-letter queue",
)

# Requeue de dead-letter
DEAD_LETTER_REQUEUED = Counter(
    "et_dead_letter_requeued_total",
    "Total de mensajes reencolados desde dead-letter",
    ["result"],
)

# Latencia de operaciones Redis
REDIS_OPERATION_DURATION = Histogram(
    "et_redis_operation_duration_seconds",
    "Latencia de operaciones Redis",
    ["operation"],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5],
)

# Deduplicación
DEDUP_TOTAL = Counter(
    "et_message_dedup_total",
    "Total de mensajes deduplicados (duplicados ignorados)",
    ["agent_id"],
)

# Documentos generados
DOCUMENTS_GENERATED = Counter(
    "et_documents_generated_total",
    "Total de documentos generados",
    ["document_type", "status"],
)

DOCUMENT_GENERATION_DURATION = Histogram(
    "et_document_generation_duration_seconds",
    "Duración de generación de documentos",
    ["document_type"],
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

# Validaciones
VALIDATIONS_TOTAL = Counter(
    "et_validations_total",
    "Total de validaciones por resultado",
    ["entity_type", "result"],
)

# Notificaciones
NOTIFICATIONS_DELIVERED = Counter(
    "et_notifications_delivered_total",
    "Total de notificaciones entregadas",
    ["event_type", "channel"],
)


# ─── Decoradores de instrumentación ──────────────────────────────────────────

def track_agent_message(agent_id: str, payload_type: str):
    """Decorador para medir latencia y contabilizar mensajes procesados."""
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            start = time.perf_counter()
            status = "success"
            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                status = "error"
                AGENT_ERRORS_TOTAL.labels(
                    agent_id=agent_id,
                    error_type=type(e).__name__,
                ).inc()
                raise
            finally:
                duration = time.perf_counter() - start
                AGENT_MESSAGE_DURATION.labels(
                    agent_id=agent_id,
                    payload_type=payload_type,
                ).observe(duration)
                AGENT_MESSAGES_TOTAL.labels(
                    agent_id=agent_id,
                    payload_type=payload_type,
                    status=status,
                ).inc()
        return wrapper
    return decorator


def track_llm_call(agent_id: str, model: str = "claude-sonnet-4-6"):
    """Decorador para medir latencia y tokens de llamadas LLM."""
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            start = time.perf_counter()
            try:
                result = await func(*args, **kwargs)
                # Si el resultado tiene usage (anthropic response)
                if hasattr(result, "usage") and result.usage:
                    LLM_TOKENS_TOTAL.labels(
                        agent_id=agent_id,
                        model=model,
                        token_type="input",
                    ).inc(result.usage.input_tokens)
                    LLM_TOKENS_TOTAL.labels(
                        agent_id=agent_id,
                        model=model,
                        token_type="output",
                    ).inc(result.usage.output_tokens)
                return result
            finally:
                duration = time.perf_counter() - start
                LLM_CALL_DURATION.labels(agent_id=agent_id, model=model).observe(duration)
        return wrapper
    return decorator


@asynccontextmanager
async def measure_redis_op(operation: str):
    """Context manager para medir latencia de operaciones Redis."""
    start = time.perf_counter()
    try:
        yield
    finally:
        REDIS_OPERATION_DURATION.labels(operation=operation).observe(
            time.perf_counter() - start
        )


# ─── Funciones de reporte ─────────────────────────────────────────────────────

def record_circuit_state(service: str, state: str) -> None:
    state_map = {"CLOSED": 0, "HALF_OPEN": 1, "OPEN": 2}
    CIRCUIT_BREAKER_STATE.labels(service=service).set(state_map.get(state, -1))


def record_saga_started() -> None:
    SAGAS_ACTIVE.inc()


def record_saga_completed(saga_type: str, outcome: str) -> None:
    SAGAS_ACTIVE.dec()
    SAGAS_COMPLETED.labels(saga_type=saga_type, outcome=outcome).inc()


def record_validation(entity_type: str, result: str) -> None:
    VALIDATIONS_TOTAL.labels(entity_type=entity_type, result=result).inc()


def record_document_generated(doc_type: str, status: str, duration: float) -> None:
    DOCUMENTS_GENERATED.labels(document_type=doc_type, status=status).inc()
    DOCUMENT_GENERATION_DURATION.labels(document_type=doc_type).observe(duration)


def record_notification(event_type: str, channel: str) -> None:
    NOTIFICATIONS_DELIVERED.labels(event_type=event_type, channel=channel).inc()


def record_dedup(agent_id: str) -> None:
    DEDUP_TOTAL.labels(agent_id=agent_id).inc()


def record_dead_letter_requeue(result: str) -> None:
    DEAD_LETTER_REQUEUED.labels(result=result).inc()


# ─── Snapshot de métricas para el dashboard ──────────────────────────────────

class MetricsSnapshot:
    """Snapshot puntual de métricas para mostrar en el dashboard interno."""

    @staticmethod
    def get_agent_summary() -> dict:
        """Retorna métricas agrupadas por agente para el dashboard."""
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "note": "Ver /metrics para métricas Prometheus completas",
            "endpoints": {
                "prometheus": "/metrics",
                "health": "/api/v1/monitoring/health",
                "circuit_breakers": "/api/v1/monitoring/circuit-breakers",
            }
        }
