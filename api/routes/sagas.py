from fastapi import APIRouter, Depends
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models import Saga

router = APIRouter()


@router.patch("/{saga_id}")
async def update_saga(saga_id: str, data: dict, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Saga).where(Saga.id == saga_id))
    saga = result.scalar_one_or_none()
    if not saga:
        return {"ok": False, "detail": "not found"}
    if "status" in data:
        saga.status = data["status"]
    if "steps" in data:
        saga.steps = data["steps"]
    if "error_message" in data and data["error_message"]:
        saga.error_message = data["error_message"]
    await db.commit()
    return {"ok": True, "saga_id": saga_id}


@router.get("")
@router.get("/")
async def list_sagas(status: str | None = None, db: AsyncSession = Depends(get_db)):
    stmt = select(Saga).order_by(Saga.created_at.desc()).limit(100)
    if status:
        # Cast explícito porque status es enum en PostgreSQL
        stmt = stmt.where(text("sagas.status::text = :s").bindparams(s=status))
    result = await db.execute(stmt)
    sagas = result.scalars().all()
    return {"sagas": [
        {
            "saga_id": str(s.id), "saga_type": s.saga_type,
            "status": s.status, "initiated_by": s.initiated_by,
            "steps": s.steps, "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in sagas
    ]}


@router.get("/{saga_id}")
async def get_saga(saga_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Saga).where(Saga.id == saga_id))
    s = result.scalar_one_or_none()
    if not s:
        return {"error": "Saga no encontrada"}
    return {
        "saga_id": str(s.id), "saga_type": s.saga_type,
        "status": s.status, "steps": s.steps,
        "context": s.context, "error_message": s.error_message,
    }
