"""
Event Bus Consumer — Consumidor base con deduplicación, reintentos y dead-letter.
Cada agente instancia un BaseConsumer y registra su handler.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Awaitable, Callable

import aio_pika
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from core.mcp.envelope import MCPEnvelope
from core.shared_state.redis_store import RedisStore

logger = logging.getLogger(__name__)

MessageHandler = Callable[[MCPEnvelope], Awaitable[None]]

EXCHANGE_NAME = "everywheretravel.events"
DL_EXCHANGE_NAME = "everywheretravel.dead_letter"

# Routing key por cola
QUEUE_ROUTING_KEYS: dict[str, list[str]] = {
    "sales-events":          ["sales.#", "sales.quotation_validated"],
    "quotation-events":      ["quotation.#", "quotation.request"],
    "reservation-events":    ["reservation.#", "reservation.create"],
    "finance-events":        ["finance.#", "finance.payment", "finance.reservation_created"],
    "document-jobs":         ["document.#", "document.generate"],
    "monitoring-events":     ["monitoring.#"],
    "notification-events":   ["*.notification", "notification.#"],
    "orchestrator-commands": ["orchestrator.#", "orchestrator.route",
                              "orchestrator.conflict", "orchestrator.blocking"],
    "dead-letter-queue":     ["#"],
}


class BaseConsumer:
    """
    Consumer con:
    - Deduplicación via Redis (processed_ids)
    - Reintento con exponential backoff (max 3 intentos)
    - Nack automático a dead-letter tras 3 fallos
    - Prefetch = 1 para garantizar procesamiento ordenado por worker
    """

    def __init__(
        self,
        connection: aio_pika.RobustConnection,
        queue_name: str,
        agent_id: str,
        redis_store: RedisStore,
    ) -> None:
        self._connection = connection
        self._queue_name = queue_name
        self._agent_id = agent_id
        self._redis = redis_store
        self._handlers: dict[str, MessageHandler] = {}
        self._channel: aio_pika.abc.AbstractChannel | None = None

    def register_handler(self, payload_type: str, handler: MessageHandler) -> None:
        self._handlers[payload_type] = handler
        logger.info(f"[{self._agent_id}] Handler registrado: {payload_type}")

    async def start(self) -> None:
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=1)

        # Declarar dead-letter exchange
        dl_exchange = await self._channel.declare_exchange(
            DL_EXCHANGE_NAME, aio_pika.ExchangeType.DIRECT, durable=True
        )

        # Declarar exchange principal
        exchange = await self._channel.declare_exchange(
            EXCHANGE_NAME, aio_pika.ExchangeType.TOPIC, durable=True
        )

        # Declarar la cola con dead-letter
        dl_routing_key = f"dead.{self._queue_name}"
        queue = await self._channel.declare_queue(
            self._queue_name,
            durable=True,
            arguments={
                "x-dead-letter-exchange": DL_EXCHANGE_NAME,
                "x-dead-letter-routing-key": dl_routing_key,
            },
        )

        # Declarar dead-letter queue y bindear
        dl_queue = await self._channel.declare_queue("dead-letter-queue", durable=True)
        await dl_queue.bind(dl_exchange, routing_key="#")

        # Bindear la cola al exchange con todos sus routing keys
        routing_keys = QUEUE_ROUTING_KEYS.get(self._queue_name, ["#"])
        for rk in routing_keys:
            await queue.bind(exchange, routing_key=rk)

        await queue.consume(self._on_message)
        logger.info(f"[{self._agent_id}] Consumiendo cola: {self._queue_name} (bindings: {routing_keys})")

    async def _on_message(
        self, message: aio_pika.abc.AbstractIncomingMessage
    ) -> None:
        async with message.process(requeue=False):
            try:
                await self._process_message(message)
            except Exception as e:
                logger.error(
                    f"[{self._agent_id}] Error procesando mensaje "
                    f"{message.message_id}: {e}"
                )
                # Nack sin requeue → dead-letter exchange
                await message.nack(requeue=False)

    async def _process_message(
        self, message: aio_pika.abc.AbstractIncomingMessage
    ) -> None:
        body = json.loads(message.body)

        # Deserializar como MCPEnvelope
        try:
            envelope = MCPEnvelope(**body)
        except Exception as e:
            logger.error(f"[{self._agent_id}] Envelope inválido: {e} | body={body}")
            return

        # Deduplicación
        is_new = await self._redis.mark_processed(envelope.message_id)
        if not is_new:
            logger.warning(
                f"[{self._agent_id}] Mensaje duplicado ignorado: {envelope.message_id}"
            )
            return

        # TTL check
        if envelope.is_expired():
            logger.warning(
                f"[{self._agent_id}] Mensaje expirado: {envelope.message_id}"
            )
            return

        # Dispatch
        handler = self._handlers.get(envelope.payload_type)
        if not handler:
            logger.warning(
                f"[{self._agent_id}] Sin handler para: {envelope.payload_type}"
            )
            return

        await self._dispatch_with_retry(handler, envelope)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=32),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    async def _dispatch_with_retry(
        self, handler: MessageHandler, envelope: MCPEnvelope
    ) -> None:
        await handler(envelope)

    async def stop(self) -> None:
        if self._channel:
            await self._channel.close()
