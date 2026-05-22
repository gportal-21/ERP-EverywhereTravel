import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, desc, text
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models import Reservation, Quotation

router = APIRouter()


@router.post("/from-quotation")
async def create_from_quotation(data: dict, db: AsyncSession = Depends(get_db)):
    """Crea una reserva directamente desde una cotización VALIDATED."""
    quote_id = data.get("quote_id")
    if not quote_id:
        raise HTTPException(400, "quote_id es requerido")

    # Buscar la cotización más reciente con ese quote_id
    q_res = await db.execute(
        select(Quotation)
        .where(Quotation.quote_id == quote_id)
        .order_by(Quotation.version.desc())
    )
    quotation = q_res.scalars().first()

    if not quotation:
        raise HTTPException(404, "Cotización no encontrada")
    if quotation.status != "VALIDATED":
        raise HTTPException(400, f"Solo se pueden reservar cotizaciones VALIDATED. Estado actual: {quotation.status}")

    # Obtener fechas de las customizaciones de la cotización
    custom = quotation.customizations or {}
    start_date = data.get("start_date") or custom.get("start_date")
    end_date   = data.get("end_date")   or custom.get("end_date")
    traveler_count = data.get("traveler_count") or custom.get("traveler_count", 1)

    def parse_dt(val: str | None) -> datetime:
        if not val:
            return datetime.now(timezone.utc)
        try:
            return datetime.fromisoformat(val)
        except Exception:
            return datetime.now(timezone.utc)

    code = f"ET-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:5].upper()}"
    r = Reservation(
        id=str(uuid.uuid4()),
        reservation_code=code,
        quote_id=quote_id,
        client_id=str(quotation.client_id) if quotation.client_id else None,
        package_id=str(quotation.package_id) if quotation.package_id else None,
        travel_start=parse_dt(start_date),
        travel_end=parse_dt(end_date),
        traveler_count=int(traveler_count),
        status="PENDING_PAYMENT",
        version=1,
        notes=data.get("notes"),
        created_by_agent="api-gateway-direct",
    )
    db.add(r)

    # Marcar la cotización como usada (opcional, no bloquea)
    await db.commit()

    return {
        "reservation_code": code,
        "quote_id": quote_id,
        "status": "PENDING_PAYMENT",
        "travel_start": parse_dt(start_date).isoformat(),
        "travel_end": parse_dt(end_date).isoformat(),
        "traveler_count": int(traveler_count),
        "total_cost": float(quotation.total_cost),
    }

VALID_STATUSES = ("PENDING_PAYMENT", "CONFIRMED", "CANCELLED", "REFUNDED")


@router.get("")
@router.get("/")
async def list_reservations(
    status: str | None = Query(None),
    client_id: str | None = Query(None),
    limit: int = Query(100, le=500),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Reservation).order_by(desc(Reservation.created_at)).limit(limit)
    if status:
        stmt = stmt.where(text("reservations.status::text = :s").bindparams(s=status))
    if client_id:
        stmt = stmt.where(Reservation.client_id == client_id)
    result = await db.execute(stmt)
    reservations = result.scalars().all()
    return {"reservations": [
        {
            "reservation_code": r.reservation_code,
            "quote_id": str(r.quote_id) if r.quote_id else None,
            "client_id": str(r.client_id) if r.client_id else None,
            "package_id": str(r.package_id) if r.package_id else None,
            "travel_start": r.travel_start.isoformat(),
            "travel_end": r.travel_end.isoformat(),
            "traveler_count": r.traveler_count,
            "status": r.status,
            "version": r.version,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "notes": r.notes,
        }
        for r in reservations
    ]}


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
        notes=data.get("notes"),
        created_by_agent=data.get("created_by_agent", "api-gateway"),
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
        "reservation_code": r.reservation_code,
        "client_id": str(r.client_id) if r.client_id else None,
        "package_id": str(r.package_id) if r.package_id else None,
        "quote_id": str(r.quote_id) if r.quote_id else None,
        "travel_start": r.travel_start.isoformat(),
        "travel_end": r.travel_end.isoformat(),
        "traveler_count": r.traveler_count,
        "status": r.status,
        "version": r.version,
        "notes": r.notes,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


@router.patch("/{reservation_code}")
async def update_reservation(reservation_code: str, data: dict, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Reservation).where(Reservation.reservation_code == reservation_code)
    )
    r = result.scalar_one_or_none()
    if not r:
        raise HTTPException(404, "Reserva no encontrada")

    new_status = data.get("status")
    if new_status and new_status not in VALID_STATUSES:
        raise HTTPException(400, f"Estado inválido. Válidos: {VALID_STATUSES}")

    for field in ("status", "notes", "traveler_count"):
        if field in data and data[field] is not None:
            setattr(r, field, data[field])

    r.version = (r.version or 1) + 1
    await db.commit()
    return {"reservation_code": r.reservation_code, "status": r.status, "version": r.version}


@router.delete("/{reservation_code}")
async def cancel_reservation(reservation_code: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Reservation).where(Reservation.reservation_code == reservation_code)
    )
    r = result.scalar_one_or_none()
    if not r:
        raise HTTPException(404, "Reserva no encontrada")
    if r.status == "CONFIRMED":
        raise HTTPException(400, "No se puede cancelar una reserva CONFIRMADA. Usa PATCH para cambiar el estado.")
    r.status = "CANCELLED"
    r.version = (r.version or 1) + 1
    await db.commit()
    return {"reservation_code": reservation_code, "status": "CANCELLED"}
