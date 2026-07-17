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

import redis.asyncio as aioredis
from fastapi import Depends, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging_config import configure_logging

configure_logging("api")

from api.config import settings
from api.database import ensure_schema_compatibility, get_db
from api.routes import auth, clients, packages, quotations, reservations, liquidations, sagas, documents, monitoring, stats, itinerary, validation_logs, knowledge, agent_interactions
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
    await ensure_schema_compatibility()
    app.state.redis = await get_redis_store(settings.redis_url)
    app.state.publisher = await get_publisher(settings.rabbitmq_url)

    # Task: escuchar Redis pub/sub para forwarding a WebSocket
    task = asyncio.create_task(_redis_pubsub_listener(app.state.redis))

    yield

    # Shutdown
    task.cancel()
    logger.info("API detenida")


async def _redis_pubsub_listener(_redis_store) -> None:
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
    redirect_slashes=False,
)

_cors_raw = os.environ.get("CORS_ORIGINS", "http://localhost:3000,http://frontend:3000")
_cors_origins = [o.strip() for o in _cors_raw.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# Métricas Prometheus
Instrumentator().instrument(app).expose(app)

# Routers
#
# Nota de seguridad: antes NINGÚN endpoint verificaba el JWT (oauth2_scheme se
# definía pero no se usaba como dependencia en ninguna ruta) — la API entera
# era efectivamente anónima pese a tener /auth/token. Ahora auth.get_current_user
# protege los routers que sirven exclusivamente al dashboard autenticado.
#
# packages, quotations, reservations, liquidations, sagas, documents,
# validation-logs, knowledge y agent-interactions NO se protegen aquí porque
# también reciben tráfico interno agente→API sin JWT de usuario (ver
# agents/*/agent.py, llamadas httpx a estas rutas). Protegerlos requiere antes
# una estrategia de auth servicio-a-servicio (API key interna o red de
# confianza) para no romper la comunicación entre agentes — ver
# docs/architecture.md, sección de seguridad, para el plan de seguimiento.
#
# monitoring tampoco se protege: /api/v1/monitoring/health y
# /circuit-breakers se documentan y usan como chequeo de diagnóstico PRE-auth
# (README "Paso 3 — Verificar servicios", y scripts/demo_flow.py::scenario_system_check
# que corre antes de client.authenticate()) — protegerlo rompería ambos.
from api.routes.auth import get_current_user

app.include_router(auth.router,         prefix="/api/v1/auth",          tags=["auth"])
app.include_router(clients.router,      prefix="/api/v1/clients",        tags=["clients"], dependencies=[Depends(get_current_user)])
app.include_router(packages.router,     prefix="/api/v1/packages",       tags=["packages"])
app.include_router(quotations.router,   prefix="/api/v1/quotations",     tags=["quotations"])
app.include_router(reservations.router, prefix="/api/v1/reservations",   tags=["reservations"])
app.include_router(liquidations.router, prefix="/api/v1/liquidations",   tags=["liquidations"])
app.include_router(sagas.router,        prefix="/api/v1/sagas",          tags=["sagas"])
app.include_router(documents.router,    prefix="/api/v1/document-jobs",  tags=["documents"])
app.include_router(monitoring.router,   prefix="/api/v1/monitoring",     tags=["monitoring"])
app.include_router(stats.router,        prefix="/api/v1/stats",           tags=["stats"], dependencies=[Depends(get_current_user)])
app.include_router(itinerary.router,    prefix="/api/v1/itinerary",       tags=["itinerary"], dependencies=[Depends(get_current_user)])
app.include_router(validation_logs.router, prefix="/api/v1/validation-logs", tags=["validation"])
app.include_router(knowledge.router,    prefix="/api/v1/knowledge",       tags=["rag", "knowledge"])
app.include_router(agent_interactions.router, prefix="/api/v1/agent-interactions", tags=["observability"])


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
async def submit_inquiry(inquiry: dict, db: AsyncSession = Depends(get_db)):
    """
    Punto de entrada principal: recibe una consulta de paquete turístico
    y la inyecta al sistema multiagente via RabbitMQ.
    """
    from core.mcp.envelope import MCPEnvelope
    from core.saga_coordinator import SagaCoordinator
    from api.models import Saga
    import uuid

    redis_store = app.state.redis
    publisher = app.state.publisher
    saga_coord = SagaCoordinator(redis_store)

    # Crear saga en Redis (working memory)
    saga_id = await saga_coord.start_saga(
        saga_type="PackageInquiry",
        initiated_by="api-gateway",
        context=inquiry,
    )

    # Persistir saga en PostgreSQL (audit trail permanente)
    db_saga = Saga(
        id=saga_id,
        saga_type="PackageInquiry",
        status="RUNNING",
        initiated_by="api-gateway",
        context=inquiry,
        steps=[],
    )
    db.add(db_saga)
    await db.commit()

    envelope = MCPEnvelope(
        saga_id=saga_id,
        sender_agent="api-gateway",
        receiver_agent="orchestrator-agent",
        payload_type="PackageInquiry",
        payload=inquiry,
    )
    await publisher.publish(envelope, "orchestrator.route")

    return {"saga_id": saga_id, "status": "processing", "message_id": envelope.message_id}
