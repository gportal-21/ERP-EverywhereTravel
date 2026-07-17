"""
Saga Coordinator — Gestiona transacciones distribuidas entre agentes.

Implementa el patrón Saga con:
- Log de pasos persistido en Redis (hot) y PostgreSQL (cold)
- Compensaciones automáticas ante fallos
- Detección de sagas estancadas (sin progreso > 5 min)
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx

from core.shared_state.redis_store import RedisStore

logger = logging.getLogger(__name__)

STALE_THRESHOLD_SECONDS = 300
_DB_API_URL = os.environ.get("DB_API_URL", "http://api:8000")
TERMINAL_STEPS = {
    "pipeline_quotation_complete",
    "validation_complete",
    "validation_blocking",
    "reservation_created",
    "reservation_failed",
    "finance_liquidation_created",
    "document_generated",
    "itinerary_generated",
}


class SagaCoordinator:
    def __init__(self, redis_store: RedisStore) -> None:
        self._redis = redis_store

    async def _sync_to_db(self, saga_id: str, saga: dict) -> None:
        """Sincroniza el estado de la saga hacia PostgreSQL (best-effort)."""
        try:
            async with httpx.AsyncClient(base_url=_DB_API_URL, timeout=5) as client:
                await client.patch(
                    f"/api/v1/sagas/{saga_id}",
                    json={
                        "status": saga.get("status", "RUNNING"),
                        "steps": saga.get("steps", []),
                        "error_message": saga.get("error_message"),
                    },
                )
        except Exception as e:
            logger.debug(f"[Saga] Sync a DB fallida (no crítico): {e}")

    async def start_saga(
        self,
        saga_type: str,
        initiated_by: str,
        context: dict[str, Any],
    ) -> str:
        saga_id = str(uuid.uuid4())
        saga_state = {
            "saga_id": saga_id,
            "saga_type": saga_type,
            "status": "RUNNING",
            "initiated_by": initiated_by,
            "context": context,
            "steps": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        await self._redis.save_saga(saga_id, saga_state)
        logger.info(f"[Saga] Iniciada: {saga_id} tipo={saga_type}")
        return saga_id

    async def record_step(
        self,
        saga_id: str,
        step_name: str,
        agent: str,
        status: str,
        output_ref: str | None = None,
        error: str | None = None,
    ) -> None:
        saga = await self._redis.get_saga(saga_id)
        if not saga:
            logger.warning(f"[Saga] No encontrada: {saga_id}")
            return

        step = {
            "step": step_name,
            "agent": agent,
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "output_ref": output_ref,
            "error": error,
        }
        saga["steps"].append(step)
        saga["updated_at"] = datetime.now(timezone.utc).isoformat()

        if status == "FAILED":
            saga["status"] = "COMPENSATING"
        elif status == "COMPLETED" and step_name in TERMINAL_STEPS:
            saga["status"] = "COMPLETED"
            saga["completed_at"] = datetime.now(timezone.utc).isoformat()

        await self._redis.save_saga(saga_id, saga)
        await self._sync_to_db(saga_id, saga)
        logger.debug(f"[Saga:{saga_id}] Paso '{step_name}' → {status}")

    async def fail_saga(self, saga_id: str, reason: str) -> None:
        saga = await self._redis.get_saga(saga_id)
        if saga:
            saga["status"] = "FAILED"
            saga["error_message"] = reason
            saga["updated_at"] = datetime.now(timezone.utc).isoformat()
            await self._redis.save_saga(saga_id, saga)
            await self._sync_to_db(saga_id, saga)
        logger.error(f"[Saga:{saga_id}] Fallida: {reason}")

    async def complete_saga(self, saga_id: str) -> None:
        saga = await self._redis.get_saga(saga_id)
        if saga:
            saga["status"] = "COMPLETED"
            saga["completed_at"] = datetime.now(timezone.utc).isoformat()
            await self._redis.save_saga(saga_id, saga)
            await self._sync_to_db(saga_id, saga)
        logger.info(f"[Saga:{saga_id}] Completada exitosamente")

    async def get_saga_status(self, saga_id: str) -> dict | None:
        return await self._redis.get_saga(saga_id)

    async def is_stale(self, saga_id: str) -> bool:
        saga = await self._redis.get_saga(saga_id)
        if not saga or saga["status"] != "RUNNING":
            return False
        updated = datetime.fromisoformat(saga["updated_at"])
        elapsed = (datetime.now(timezone.utc) - updated).total_seconds()
        return elapsed > STALE_THRESHOLD_SECONDS

    def _all_steps_done(self, saga: dict) -> bool:
        return all(s["status"] in ("COMPLETED", "SKIPPED") for s in saga["steps"])
