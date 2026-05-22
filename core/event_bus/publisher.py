"""
Event Bus Publisher — Publica mensajes MCP al exchange de RabbitMQ.
Soporta prioridades, persistencia y routing dinámico por topic.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import aio_pika
from aio_pika import DeliveryMode, Message

from core.mcp.envelope import MCPEnvelope

logger = logging.getLogger(__name__)

EXCHANGE_NAME = "everywheretravel.events"


class EventPublisher:
    def __init__(self, connection: aio_pika.RobustConnection) -> None:
        self._connection = connection
        self._channel: aio_pika.abc.AbstractChannel | None = None
        self._exchange: aio_pika.abc.AbstractExchange | None = None

    async def connect(self) -> None:
        self._channel = await self._connection.channel()
        self._exchange = await self._channel.declare_exchange(
            EXCHANGE_NAME,
            aio_pika.ExchangeType.TOPIC,
            durable=True,
        )
        logger.info(f"Publisher conectado al exchange: {EXCHANGE_NAME}")

    async def publish(
        self,
        envelope: MCPEnvelope,
        routing_key: str,
    ) -> None:
        if not self._exchange:
            raise RuntimeError("Publisher no conectado. Llama connect() primero.")

        body = envelope.model_dump_json().encode()
        message = Message(
            body=body,
            delivery_mode=DeliveryMode.PERSISTENT,
            message_id=envelope.message_id,
            correlation_id=envelope.correlation_id,
            content_type="application/json",
            priority=envelope.priority,
            headers={
                "saga_id": envelope.saga_id,
                "sender_agent": envelope.sender_agent,
                "payload_type": envelope.payload_type,
            },
        )
        await self._exchange.publish(message, routing_key=routing_key)
        logger.debug(
            f"Publicado [{routing_key}] "
            f"msg={envelope.message_id} saga={envelope.saga_id}"
        )

    async def publish_raw(
        self,
        routing_key: str,
        payload: dict[str, Any],
        message_id: str | None = None,
    ) -> None:
        if not self._exchange:
            raise RuntimeError("Publisher no conectado.")

        body = json.dumps(payload).encode()
        message = Message(
            body=body,
            delivery_mode=DeliveryMode.PERSISTENT,
            content_type="application/json",
            message_id=message_id,
        )
        await self._exchange.publish(message, routing_key=routing_key)

    async def close(self) -> None:
        if self._channel:
            await self._channel.close()


_publisher_instance: EventPublisher | None = None


async def get_publisher(rabbitmq_url: str) -> EventPublisher:
    global _publisher_instance
    if _publisher_instance is None:
        connection = await aio_pika.connect_robust(rabbitmq_url)
        _publisher_instance = EventPublisher(connection)
        await _publisher_instance.connect()
    return _publisher_instance
