import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models import Liquidation, Transaction, Reservation

router = APIRouter()


@router.post("/")
async def create_liquidation(data: dict, db: AsyncSession = Depends(get_db)):
    # Buscar reservation_id por código
    res_result = await db.execute(
        select(Reservation).where(Reservation.reservation_code == data.get("reservation_code"))
    )
    reservation = res_result.scalar_one_or_none()

    liq = Liquidation(
        id=str(uuid.uuid4()),
        liquidation_code=data.get("liquidation_code", f"LIQ-{uuid.uuid4().hex[:8].upper()}"),
        reservation_id=str(reservation.id) if reservation else None,
        total_charged=data.get("total_charged", 0),
        total_paid=data.get("total_paid", 0),
        commission_amount=data.get("commission_amount", 0),
        status=data.get("status", "PARTIAL"),
        payment_schedule=data.get("payment_schedule", []),
    )
    db.add(liq)
    await db.commit()
    return {"liquidation_code": liq.liquidation_code, "status": liq.status}


@router.post("/{reservation_code}/transactions")
async def add_transaction(reservation_code: str, data: dict, db: AsyncSession = Depends(get_db)):
    res = await db.execute(
        select(Reservation).where(Reservation.reservation_code == reservation_code)
    )
    reservation = res.scalar_one_or_none()
    if not reservation:
        raise HTTPException(404, "Reserva no encontrada")

    liq_res = await db.execute(
        select(Liquidation).where(Liquidation.reservation_id == str(reservation.id))
    )
    liq = liq_res.scalar_one_or_none()
    if not liq:
        raise HTTPException(404, "Liquidación no encontrada")

    tx = Transaction(
        id=str(uuid.uuid4()),
        liquidation_id=str(liq.id),
        amount=data.get("amount", 0),
        payment_method=data.get("method", "TRANSFER"),
        reference=data.get("reference", ""),
        recorded_by_agent=data.get("recorded_by_agent", "finance-agent"),
    )
    db.add(tx)
    liq.total_paid = float(liq.total_paid) + float(data.get("amount", 0))
    if float(liq.total_paid) >= float(liq.total_charged):
        liq.status = "COMPLETE"
    await db.commit()

    return {
        "transaction_id": str(tx.id),
        "liquidation_code": liq.liquidation_code,
        "total_paid": float(liq.total_paid),
        "status": liq.status,
    }
