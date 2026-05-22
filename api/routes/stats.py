from fastapi import APIRouter, Depends
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models import Client, Reservation, Liquidation, Transaction, Saga, Package

router = APIRouter()


@router.get("")
@router.get("/")
async def get_stats(db: AsyncSession = Depends(get_db)):
    # Clientes
    total_clients = (await db.execute(select(func.count()).select_from(Client))).scalar()

    # Reservas por estado
    res_by_status = await db.execute(
        select(text("status::text"), func.count())
        .select_from(Reservation)
        .group_by(text("status::text"))
    )
    reservations = {row[0]: row[1] for row in res_by_status}

    # Revenue total
    revenue_row = await db.execute(
        select(func.coalesce(func.sum(Transaction.amount), 0))
    )
    total_revenue = float(revenue_row.scalar() or 0)

    # Balance pendiente
    pending_row = await db.execute(
        select(func.coalesce(func.sum(Liquidation.total_charged - Liquidation.total_paid), 0))
        .where(text("liquidations.status::text != 'COMPLETE'"))
    )
    pending_balance = float(pending_row.scalar() or 0)

    # Paquetes activos
    active_packages = (await db.execute(
        select(func.count()).select_from(Package).where(Package.is_active == True)
    )).scalar()

    # Sagas por estado
    sagas_row = await db.execute(
        select(text("status::text"), func.count())
        .select_from(Saga)
        .group_by(text("status::text"))
    )
    sagas = {row[0]: row[1] for row in sagas_row}

    # Últimas 5 reservas
    last_res = await db.execute(
        select(Reservation).order_by(Reservation.created_at.desc()).limit(5)
    )
    recent_reservations = [
        {
            "code": r.reservation_code,
            "status": r.status,
            "traveler_count": r.traveler_count,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in last_res.scalars().all()
    ]

    return {
        "clients": {"total": total_clients},
        "reservations": {
            "total": sum(reservations.values()),
            "by_status": reservations,
            "confirmed": reservations.get("CONFIRMED", 0),
            "pending": reservations.get("PENDING_PAYMENT", 0),
            "cancelled": reservations.get("CANCELLED", 0),
        },
        "finance": {
            "total_revenue": total_revenue,
            "pending_balance": pending_balance,
        },
        "packages": {"active": active_packages},
        "sagas": {
            "total": sum(sagas.values()),
            "running": sagas.get("RUNNING", 0),
            "completed": sagas.get("COMPLETED", 0),
            "failed": sagas.get("FAILED", 0),
        },
        "recent_reservations": recent_reservations,
    }
