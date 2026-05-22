from fastapi import APIRouter, Request
from api.config import settings
from core.shared_state.redis_store import get_redis_store

router = APIRouter()


@router.get("/health")
async def system_health(request: Request):
    redis = await get_redis_store(settings.redis_url)
    heartbeats = await redis.get_all_heartbeats()
    agents_status = {
        agent: ("HEALTHY" if hb else "UNKNOWN")
        for agent, hb in heartbeats.items()
    }
    return {
        "system": "everywheretravel",
        "agents": agents_status,
        "healthy_count": sum(1 for v in agents_status.values() if v == "HEALTHY"),
        "total_agents": len(agents_status),
    }


@router.get("/circuit-breakers")
async def circuit_breakers(request: Request):
    redis = await get_redis_store(settings.redis_url)
    from agents.base_agent import BaseAgent
    agents = [
        "orchestrator-agent", "sales-agent", "quotation-agent",
        "reservation-agent", "finance-agent", "document-agent",
        "validation-agent", "monitoring-agent", "notification-agent",
    ]
    result = {}
    for agent in agents:
        state = await redis.get_circuit_state(agent)
        result[agent] = state
    return result
