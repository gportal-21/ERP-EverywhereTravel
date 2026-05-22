import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models import Reservation

router = APIRouter()


@router.post("/")
async def create_reservation(data: dict, db: AsyncSession = Depends(get_db)):
    def parse_dt(val):
        if not val:
            return datetime.now(timezone.utc)
        try:
            return datetime.fromisoformat(val)
        except Exception:
            return datetime.now(timezone.utc)

    r = Reservation(
        id=str(uuid.uuid4()),
        reservation_code=data["reservation_code"],
        quote_id=data["quote_id"],
        client_id=data.get("client_id"),
        package_id=data.get("package_id"),
        travel_start=parse_dt(data.get("travel_start")),
        travel_end=parse_dt(data.get("travel_end")),
        traveler_count=data.get("traveler_count", 1),
        status=data.get("status", "PENDING_PAYMENT"),
        version=data.get("version", 1),
        created_by_agent=data.get("created_by_agent", "reservation-agent"),
    )
    db.add(r)
    await db.commit()
    return {"reservation_code": r.reservation_code, "status": r.status}


@router.get("/{reservation_code}")
async def get_reservation(reservation_code: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Reservation).where(Reservation.reservation_code == reservation_code)
    )
    r = result.scalar_one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="Reserva no encontrada")
    return {
        "reservation_code": r.reservation_code, "status": r.status,
        "travel_start": r.travel_start.isoformat(), "travel_end": r.travel_end.isoformat(),
        "traveler_count": r.traveler_count, "version": r.version,
    }
