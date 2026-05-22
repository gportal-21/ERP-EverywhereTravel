"""
Redis Store — Shared state, optimistic locking y deduplicación de mensajes.

Tres responsabilidades:
1. Working memory (sagas activas, locks, heartbeats)
2. Deduplicación de mensajes MCP (processed_ids)
3. Estado de circuit breakers
"""
from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import Any

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

# TTLs por tipo de clave
TTL_SAGA = int(timedelta(hours=1).total_seconds())
TTL_LOCK = 30
TTL_DEDUP = int(timedelta(hours=24).total_seconds())
TTL_HEARTBEAT = 90
TTL_CIRCUIT = int(timedelta(minutes=5).total_seconds())


class RedisStore:
    """Acceso centralizado al Redis compartido del sistema multiagente."""

    def __init__(self, client: aioredis.Redis) -> None:
        self._r = client

    # ─── Saga State ──────────────────────────────────────────────────────────

    async def save_saga(self, saga_id: str, state: dict[str, Any]) -> None:
        await self._r.setex(
            f"saga:{saga_id}", TTL_SAGA, json.dumps(state)
        )

    async def get_saga(self, saga_id: str) -> dict[str, Any] | None:
        raw = await self._r.get(f"saga:{saga_id}")
        return json.loads(raw) if raw else None

    async def update_saga_step(
        self, saga_id: str, step_name: str, step_data: dict
    ) -> None:
        saga = await self.get_saga(saga_id) or {"steps": []}
        saga.setdefault("steps", []).append({"step": step_name, **step_data})
        await self.save_saga(saga_id, saga)

    # ─── Optimistic Locking ──────────────────────────────────────────────────

    async def acquire_lock(
        self, entity_type: str, entity_id: str, agent_id: str
    ) -> bool:
        """SETNX atómico — retorna True si el lock fue adquirido."""
        key = f"lock:{entity_type}:{entity_id}"
        acquired = await self._r.set(
            key, agent_id, ex=TTL_LOCK, nx=True
        )
        if acquired:
            logger.debug(f"Lock adquirido: {key} por {agent_id}")
        return bool(acquired)

    async def release_lock(
        self, entity_type: str, entity_id: str, agent_id: str
    ) -> bool:
        """Libera el lock solo si el agente actual es el propietario."""
        key = f"lock:{entity_type}:{entity_id}"
        current = await self._r.get(key)
        if current and current.decode() == agent_id:
            await self._r.delete(key)
            logger.debug(f"Lock liberado: {key}")
            return True
        logger.warning(f"Intento de liberar lock ajeno: {key} (propietario={current})")
        return False

    async def get_lock_owner(self, entity_type: str, entity_id: str) -> str | None:
        val = await self._r.get(f"lock:{entity_type}:{entity_id}")
        return val.decode() if val else None

    # ─── Deduplicación de mensajes ───────────────────────────────────────────

    async def mark_processed(self, message_id: str) -> bool:
        """Marca el mensaje como procesado. Retorna True si es nuevo (no duplicado)."""
        key = f"processed:{message_id}"
        result = await self._r.set(key, "1", ex=TTL_DEDUP, nx=True)
        return bool(result)

    async def is_processed(self, message_id: str) -> bool:
        exists = await self._r.exists(f"processed:{message_id}")
        return bool(exists)

    # ─── Heartbeats de agentes ───────────────────────────────────────────────

    async def update_heartbeat(self, agent_id: str, data: dict) -> None:
        await self._r.setex(
            f"heartbeat:{agent_id}", TTL_HEARTBEAT, json.dumps(data)
        )

    async def get_heartbeat(self, agent_id: str) -> dict | None:
        raw = await self._r.get(f"heartbeat:{agent_id}")
        return json.loads(raw) if raw else None

    async def get_all_heartbeats(self) -> dict[str, dict | None]:
        agents = [
            "orchestrator-agent", "sales-agent", "quotation-agent",
            "reservation-agent", "finance-agent", "document-agent",
            "validation-agent", "monitoring-agent", "notification-agent",
        ]
        result = {}
        for agent in agents:
            result[agent] = await self.get_heartbeat(agent)
        return result

    # ─── Circuit Breaker state ───────────────────────────────────────────────

    async def get_circuit_state(self, service: str) -> dict:
        raw = await self._r.get(f"circuit:{service}")
        if raw:
            return json.loads(raw)
        return {"state": "CLOSED", "failure_count": 0, "last_failure": None}

    async def set_circuit_state(self, service: str, state: dict) -> None:
        await self._r.setex(f"circuit:{service}", TTL_CIRCUIT, json.dumps(state))

    async def increment_circuit_failures(self, service: str) -> int:
        key = f"circuit:failures:{service}"
        count = await self._r.incr(key)
        await self._r.expire(key, 60)
        return count

    async def reset_circuit_failures(self, service: str) -> None:
        await self._r.delete(f"circuit:failures:{service}")

    # ─── Memoria semántica (preferencias de clientes, patrones) ─────────────

    async def set_client_memory(self, client_id: str, data: dict) -> None:
        await self._r.set(f"memory:client:{client_id}", json.dumps(data))

    async def get_client_memory(self, client_id: str) -> dict:
        raw = await self._r.get(f"memory:client:{client_id}")
        return json.loads(raw) if raw else {}

    # ─── Pub/Sub para WebSocket (notificaciones en tiempo real) ─────────────

    async def publish_realtime(self, channel: str, data: dict) -> None:
        await self._r.publish(channel, json.dumps(data))


_store_instance: RedisStore | None = None


async def get_redis_store(redis_url: str) -> RedisStore:
    global _store_instance
    if _store_instance is None:
        client = aioredis.from_url(redis_url, decode_responses=False)
        _store_instance = RedisStore(client)
    return _store_instance
