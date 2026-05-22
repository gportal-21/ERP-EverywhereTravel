"""
Base Agent — Clase abstracta que todos los agentes especializados heredan.

Provee:
- Ciclo de vida (start/stop)
- Integración con Redis, RabbitMQ, PostgreSQL
- Heartbeat automático
- Métricas de latencia y tokens
- Logging estructurado
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone

import aio_pika

from core.circuit_breaker import CircuitBreaker
from core.event_bus.consumer import BaseConsumer
from core.event_bus.publisher import EventPublisher, get_publisher
from core.mcp.envelope import MCPEnvelope
from core.saga_coordinator import SagaCoordinator
from core.shared_state.redis_store import RedisStore, get_redis_store

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """
    Clase base para todos los agentes del sistema multiagente.
    Cada agente hereda de esta clase e implementa handle_message().
    """

    agent_id: str
    queue_name: str
    system_prompt_file: str

    def __init__(self) -> None:
        self._redis: RedisStore | None = None
        self._publisher: EventPublisher | None = None
        self._consumer: BaseConsumer | None = None
        self._saga: SagaCoordinator | None = None
        self._circuit_breaker: CircuitBreaker | None = None
        self._connection: aio_pika.RobustConnection | None = None
        self._system_prompt: str = ""
        self._running = False
        self._messages_processed = 0
        self._errors_last_minute = 0

    async def initialize(self) -> None:
        redis_url = os.environ["REDIS_URL"]
        rabbitmq_url = os.environ["RABBITMQ_URL"]

        self._redis = await get_redis_store(redis_url)
        self._publisher = await get_publisher(rabbitmq_url)
        self._saga = SagaCoordinator(self._redis)
        self._circuit_breaker = CircuitBreaker(self.agent_id, self._redis)

        # Conectar consumidor
        self._connection = await aio_pika.connect_robust(rabbitmq_url)
        self._consumer = BaseConsumer(
            self._connection, self.queue_name, self.agent_id, self._redis
        )
        self._register_handlers()
        await self._consumer.start()

        # Cargar system prompt
        self._load_system_prompt()

        logger.info(f"[{self.agent_id}] Inicializado correctamente")

    def _load_system_prompt(self) -> None:
        prompt_path = (
            f"agents/{self.agent_id.replace('-agent', '')}"
            f"/prompts/system_prompt.txt"
        )
        try:
            with open(prompt_path) as f:
                self._system_prompt = f.read()
        except FileNotFoundError:
            logger.warning(f"[{self.agent_id}] System prompt no encontrado: {prompt_path}")
            self._system_prompt = f"You are the {self.agent_id} for Everywhere Travel."

    @abstractmethod
    def _register_handlers(self) -> None:
        """Registra los handlers de payload_type en el consumer."""
        pass

    @abstractmethod
    async def handle_message(self, envelope: MCPEnvelope) -> None:
        """Lógica principal del agente para procesar un mensaje."""
        pass

    async def publish(
        self,
        payload_type: str,
        payload: dict,
        receiver_agent: str,
        routing_key: str,
        saga_id: str,
    ) -> None:
        envelope = MCPEnvelope(
            saga_id=saga_id,
            sender_agent=self.agent_id,
            receiver_agent=receiver_agent,
            payload_type=payload_type,
            payload=payload,
        )
        await self._publisher.publish(envelope, routing_key)

    async def _send_heartbeat(self) -> None:
        while self._running:
            await self._redis.update_heartbeat(
                self.agent_id,
                {
                    "agent_id": self.agent_id,
                    "agent_type": self.agent_id,
                    "status": "HEALTHY",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "metrics": {
                        "messages_processed": self._messages_processed,
                        "errors_last_minute": self._errors_last_minute,
                        "avg_latency_ms": 0,
                    },
                },
            )
            await asyncio.sleep(30)

    async def run(self) -> None:
        await self.initialize()
        self._running = True
        logger.info(f"[{self.agent_id}] Ejecutándose. Esperando mensajes...")
        asyncio.create_task(self._send_heartbeat())
        try:
            await asyncio.Future()  # Mantiene el loop activo
        except (KeyboardInterrupt, asyncio.CancelledError):
            await self.stop()

    async def stop(self) -> None:
        self._running = False
        if self._consumer:
            await self._consumer.stop()
        logger.info(f"[{self.agent_id}] Detenido")
