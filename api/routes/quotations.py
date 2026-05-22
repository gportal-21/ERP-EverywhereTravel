import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models import Quotation, Package

router = APIRouter()

IGV = Decimal("0.18")
MARGIN = Decimal("0.20")


@router.post("/direct")
async def create_direct_quotation(data: dict, db: AsyncSession = Depends(get_db)):
    """Crea una cotización directamente sin pasar por el flujo multiagente.
    Útil cuando la API de LLM no está disponible o para cotizaciones simples."""
    client_id   = data.get("client_id")
    package_id  = data.get("package_id")
    traveler_count = int(data.get("traveler_count", 1))
    start_date  = data.get("start_date")
    end_date    = data.get("end_date")

    if not client_id or not package_id:
        raise HTTPException(400, "client_id y package_id son requeridos")

    # Obtener paquete
    pkg_res = await db.execute(select(Package).where(Package.id == package_id))
    pkg = pkg_res.scalar_one_or_none()
    if not pkg:
        raise HTTPException(404, "Paquete no encontrado")

    # Calcular precio
    base_price = Decimal(str(pkg.base_price))
    base_cost  = base_price * traveler_count
    margin     = (base_cost * MARGIN).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    taxes      = (base_cost * IGV).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    total_cost = base_cost + margin + taxes

    line_items = [
        {"concept": pkg.name, "unit_price": float(base_price), "quantity": traveler_count, "subtotal": float(base_cost)},
        {"concept": "Margen de servicio (20%)", "unit_price": float(margin), "quantity": 1, "subtotal": float(margin)},
        {"concept": "IGV (18%)", "unit_price": float(taxes), "quantity": 1, "subtotal": float(taxes)},
    ]

    valid_until = datetime.now(timezone.utc) + timedelta(hours=48)
    quote_id = str(uuid.uuid4())

    q = Quotation(
        id=str(uuid.uuid4()),
        quote_id=quote_id,
        version=1,
        client_id=client_id,
        package_id=package_id,
        line_items=line_items,
        total_cost=float(total_cost),
        margin_pct=float(MARGIN * 100),
        currency="PEN",
        valid_until=valid_until,
        status="VALIDATED",
        customizations={"start_date": start_date, "end_date": end_date, "traveler_count": traveler_count},
        created_by_agent="api-gateway-direct",
    )
    db.add(q)
    await db.commit()

    return {
        "quote_id": quote_id,
        "package_name": pkg.name,
        "destination": pkg.destination,
        "traveler_count": traveler_count,
        "line_items": line_items,
        "total_cost": float(total_cost),
        "margin_pct": float(MARGIN * 100),
        "currency": "PEN",
        "valid_until": valid_until.isoformat(),
        "status": "VALIDATED",
        "start_date": start_date,
        "end_date": end_date,
    }


@router.get("")
@router.get("/")
async def list_quotations(
    status: str | None = Query(None),
    client_id: str | None = Query(None),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Quotation).order_by(desc(Quotation.created_at)).limit(limit)
    if status:
        from sqlalchemy import text
        stmt = stmt.where(text("quotations.status::text = :s").bindparams(s=status))
    if client_id:
        stmt = stmt.where(Quotation.client_id == client_id)
    result = await db.execute(stmt)
    quotations = result.scalars().all()
    return {"quotations": [
        {
            "id": str(q.id),
            "quote_id": q.quote_id,
            "version": q.version,
            "client_id": str(q.client_id) if q.client_id else None,
            "total_cost": float(q.total_cost),
            "margin_pct": float(q.margin_pct),
            "currency": q.currency,
            "status": q.status,
            "valid_until": q.valid_until.isoformat() if q.valid_until else None,
            "created_at": q.created_at.isoformat() if q.created_at else None,
        }
        for q in quotations
    ]}


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
