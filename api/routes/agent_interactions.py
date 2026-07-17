"""Agent Interactions Route — recolector central de trazas LLM.

Los agentes corren en contenedores separados (sales_worker, quotation_worker,
...) sin servidor HTTP propio, así que sus contadores de prometheus_client en
memoria nunca serían scrapeados (Prometheus solo scrapea `api:8000/metrics`,
ver infrastructure/prometheus/prometheus.yml). Por eso los agentes reportan
cada interacción LLM aquí (agents/base_agent.py::report_llm_interaction):

1. Se persiste en `agent_interaction_logs` (Postgres) — alimenta el golden set
   de evaluación local (scripts/run_evaluation.py) como sustituto de LangSmith.
2. Se incrementan las métricas Prometheus de core/metrics.py en el proceso de
   la API, que sí es scrapeado — así et_llm_tokens_total, et_agent_messages_total
   y et_llm_call_duration_seconds reflejan actividad real de los agentes.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models import AgentInteractionLog
from core.metrics import (
    AGENT_MESSAGE_DURATION,
    AGENT_MESSAGES_TOTAL,
    LLM_CALL_DURATION,
    LLM_TOKENS_TOTAL,
)

router = APIRouter()


class AgentInteractionIn(BaseModel):
    saga_id: str | None = None
    agent_id: str
    action: str
    input_schema: dict | None = None
    output_schema: dict | None = None
    duration_ms: int | None = None
    tokens_used: int | None = None
    success: bool = True
    error_message: str | None = None
    model: str = "ollama/qwen3:8b"


@router.post("")
@router.post("/")
async def record_agent_interaction(data: AgentInteractionIn, db: AsyncSession = Depends(get_db)):
    log = AgentInteractionLog(
        saga_id=data.saga_id,
        agent_id=data.agent_id,
        action=data.action,
        input_schema=data.input_schema,
        output_schema=data.output_schema,
        duration_ms=data.duration_ms,
        tokens_used=data.tokens_used,
        success=data.success,
        error_message=data.error_message,
    )
    db.add(log)
    await db.commit()

    status = "success" if data.success else "error"
    AGENT_MESSAGES_TOTAL.labels(agent_id=data.agent_id, payload_type=data.action, status=status).inc()
    if data.duration_ms is not None:
        AGENT_MESSAGE_DURATION.labels(agent_id=data.agent_id, payload_type=data.action).observe(data.duration_ms / 1000)
        LLM_CALL_DURATION.labels(agent_id=data.agent_id, model=data.model).observe(data.duration_ms / 1000)
    if data.tokens_used:
        LLM_TOKENS_TOTAL.labels(agent_id=data.agent_id, model=data.model, token_type="total").inc(data.tokens_used)

    return {"id": str(log.id)}
