"""
Circuit Breaker — Implementación del patrón para proteger servicios downstream.

Estados: CLOSED → OPEN → HALF_OPEN → CLOSED
- CLOSED: operación normal
- OPEN: fallas > threshold → rechaza llamadas sin ejecutarlas
- HALF_OPEN: prueba si el servicio se recuperó
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, TypeVar

from core.shared_state.redis_store import RedisStore

logger = logging.getLogger(__name__)

T = TypeVar("T")

FAILURE_THRESHOLD = 5
RESET_TIMEOUT_SECONDS = 30
WINDOW_SECONDS = 60


class CircuitBreakerOpenError(Exception):
    """Lanzada cuando el circuito está OPEN y se intenta una llamada."""
    pass


class CircuitBreaker:
    """
    Circuit breaker distribuido usando Redis como estado compartido.
    Permite coordinación entre múltiples instancias del mismo agente.
    """

    def __init__(self, service_name: str, redis_store: RedisStore) -> None:
        self.service_name = service_name
        self._redis = redis_store

    async def call(
        self,
        func: Callable[..., Awaitable[T]],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        state = await self._redis.get_circuit_state(self.service_name)

        if state["state"] == "OPEN":
            last_failure = state.get("last_failure")
            if last_failure:
                elapsed = (
                    datetime.now(timezone.utc)
                    - datetime.fromisoformat(last_failure)
                ).total_seconds()
                if elapsed >= RESET_TIMEOUT_SECONDS:
                    await self._transition_to("HALF_OPEN", state)
                    logger.info(f"[CB:{self.service_name}] OPEN → HALF_OPEN")
                else:
                    raise CircuitBreakerOpenError(
                        f"Circuito OPEN para {self.service_name}. "
                        f"Retry en {RESET_TIMEOUT_SECONDS - elapsed:.0f}s"
                    )

        try:
            result = await func(*args, **kwargs)
            await self._on_success(state)
            return result
        except Exception as e:
            await self._on_failure(state)
            raise

    async def _on_success(self, state: dict) -> None:
        if state["state"] in ("HALF_OPEN", "OPEN"):
            await self._transition_to("CLOSED", {"failure_count": 0})
            logger.info(f"[CB:{self.service_name}] → CLOSED (recuperado)")
        await self._redis.reset_circuit_failures(self.service_name)

    async def _on_failure(self, state: dict) -> None:
        failures = await self._redis.increment_circuit_failures(self.service_name)
        logger.warning(
            f"[CB:{self.service_name}] Fallo #{failures}/{FAILURE_THRESHOLD}"
        )
        if failures >= FAILURE_THRESHOLD or state["state"] == "HALF_OPEN":
            await self._transition_to(
                "OPEN",
                {
                    "failure_count": failures,
                    "last_failure": datetime.now(timezone.utc).isoformat(),
                },
            )
            logger.error(f"[CB:{self.service_name}] → OPEN (umbral alcanzado)")

    async def _transition_to(self, new_state: str, extra: dict) -> None:
        current = await self._redis.get_circuit_state(self.service_name)
        current.update({"state": new_state, **extra})
        await self._redis.set_circuit_state(self.service_name, current)

    async def get_state(self) -> str:
        state = await self._redis.get_circuit_state(self.service_name)
        return state.get("state", "CLOSED")
