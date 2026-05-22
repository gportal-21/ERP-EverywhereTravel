"""
FastAPI Gateway — Punto de entrada HTTP/WebSocket del sistema.

Expone:
- REST API para operaciones CRUD y trigger de flujos multiagente
- WebSocket para notificaciones en tiempo real (Redis pub/sub)
- Métricas Prometheus en /metrics
- Health check en /health
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager

import aio_pika
import redis.asyncio as aioredis
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from api.config import settings
from api.routes import auth, clients, packages, quotations, reservations, liquidations, sagas, documents, monitoring
from core.event_bus.publisher import get_publisher
from core.shared_state.redis_store import get_redis_store

logger = logging.getLogger(__name__)

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active: dict[str, list[WebSocket]] = {}

    async def connect(self, channel: str, ws: WebSocket):
        await ws.accept()
        self.active.setdefault(channel, []).append(ws)

    def disconnect(self, channel: str, ws: WebSocket):
        if channel in self.active:
            self.active[channel].remove(ws)

    async def broadcast(self, channel: str, data: dict):
        for ws in self.active.get(channel, []):
            try:
                await ws.send_json(data)
            except Exception:
                pass


manager = ConnectionManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Iniciando Everywhere Travel API...")
    app.state.redis = await get_redis_store(settings.redis_url)
    app.state.publisher = await get_publisher(settings.rabbitmq_url)

    # Task: escuchar Redis pub/sub para forwarding a WebSocket
    task = asyncio.create_task(_redis_pubsub_listener(app.state.redis))

    yield

    # Shutdown
    task.cancel()
    logger.info("API detenida")


async def _redis_pubsub_listener(redis_store) -> None:
    """Escucha Redis pub/sub y forwardea mensajes a clientes WebSocket."""
    raw_client = aioredis.from_url(settings.redis_url)
    pubsub = raw_client.pubsub()
    await pubsub.psubscribe("client:*", "system:alerts")

    async for message in pubsub.listen():
        if message["type"] == "pmessage":
            try:
                channel = message["channel"].decode()
                data = json.loads(message["data"])
                await manager.broadcast(channel, data)
            except Exception:
                pass


app = FastAPI(
    title="Everywhere Travel — Sistema Multiagente",
    description="Plataforma interna de gestión para agencia de viajes",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://frontend:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Métricas Prometheus
Instrumentator().instrument(app).expose(app)

# Routers
app.include_router(auth.router,         prefix="/api/v1/auth",          tags=["auth"])
app.include_router(clients.router,      prefix="/api/v1/clients",        tags=["clients"])
app.include_router(packages.router,     prefix="/api/v1/packages",       tags=["packages"])
app.include_router(quotations.router,   prefix="/api/v1/quotations",     tags=["quotations"])
app.include_router(reservations.router, prefix="/api/v1/reservations",   tags=["reservations"])
app.include_router(liquidations.router, prefix="/api/v1/liquidations",   tags=["liquidations"])
app.include_router(sagas.router,        prefix="/api/v1/sagas",          tags=["sagas"])
app.include_router(documents.router,    prefix="/api/v1/document-jobs",  tags=["documents"])
app.include_router(monitoring.router,   prefix="/api/v1/monitoring",     tags=["monitoring"])


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "everywheretravel-api"}


@app.websocket("/ws/{channel}")
async def websocket_endpoint(websocket: WebSocket, channel: str):
    """
    WebSocket para notificaciones en tiempo real.
    channel: "client:{client_id}" | "system:alerts"
    """
    await manager.connect(channel, websocket)
    try:
        while True:
            await websocket.receive_text()  # keepalive
    except WebSocketDisconnect:
        manager.disconnect(channel, websocket)


@app.post("/api/v1/inquiries")
async def submit_inquiry(inquiry: dict, request=None):
    """
    Punto de entrada principal: recibe una consulta de paquete turístico
    y la inyecta al sistema multiagente via RabbitMQ.
    """
    from core.mcp.envelope import MCPEnvelope
    from core.saga_coordinator import SagaCoordinator
    import uuid

    redis_store = app.state.redis
    publisher = app.state.publisher
    saga = SagaCoordinator(redis_store)

    # Crear saga
    saga_id = await saga.start_saga(
        saga_type="PackageInquiry",
        initiated_by="api-gateway",
        context=inquiry,
    )

    envelope = MCPEnvelope(
        saga_id=saga_id,
        sender_agent="api-gateway",
        receiver_agent="orchestrator-agent",
        payload_type="PackageInquiry",
        payload=inquiry,
    )
    await publisher.publish(envelope, "orchestrator.route")

    return {"saga_id": saga_id, "status": "processing", "message_id": envelope.message_id}
