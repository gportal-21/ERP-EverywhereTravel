import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models import Quotation

router = APIRouter()


@router.post("/")
async def create_quotation(data: dict, db: AsyncSession = Depends(get_db)):
    valid_until = data.get("valid_until")
    if isinstance(valid_until, str):
        try:
            valid_until = datetime.fromisoformat(valid_until)
        except ValueError:
            valid_until = datetime.now(timezone.utc)

    q = Quotation(
        id=str(uuid.uuid4()),
        quote_id=data.get("quote_id", str(uuid.uuid4())),
        version=data.get("version", 1),
        client_id=data.get("client_id"),
        package_id=data.get("package_id"),
        line_items=data.get("line_items", []),
        total_cost=data.get("total_cost", 0),
        margin_pct=data.get("margin_pct", 0),
        currency=data.get("currency", "PEN"),
        valid_until=valid_until,
        status=data.get("status", "DRAFT"),
        customizations=data.get("customizations", {}),
        created_by_agent=data.get("created_by_agent", "quotation-agent"),
    )
    db.add(q)
    await db.commit()
    return {"id": str(q.id), "quote_id": q.quote_id, "status": q.status}


@router.get("/{quote_id}")
async def get_quotation(quote_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Quotation)
        .where(Quotation.quote_id == quote_id)
        .order_by(Quotation.version.desc())
    )
    q = result.scalars().first()
    if not q:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")
    return {
        "quote_id": q.quote_id, "version": q.version,
        "total_cost": float(q.total_cost), "status": q.status,
        "line_items": q.line_items, "margin_pct": float(q.margin_pct),
        "valid_until": q.valid_until.isoformat() if q.valid_until else None,
    }
