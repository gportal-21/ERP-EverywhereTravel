import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models import Quotation, Package, Saga, ValidationLog

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
            "package_id": str(q.package_id) if q.package_id else None,
            "line_items": q.line_items or [],
            "total_cost": float(q.total_cost),
            "margin_pct": float(q.margin_pct),
            "currency": q.currency,
            "status": q.status,
            "valid_until": q.valid_until.isoformat() if q.valid_until else None,
            "created_at": q.created_at.isoformat() if q.created_at else None,
            "customizations": q.customizations or {},
            "created_by_agent": q.created_by_agent,
        }
        for q in quotations
    ]}


@router.post("")
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


@router.patch("/{quote_id}/status")
async def update_quotation_status(
    quote_id: str,
    data: dict,
    db: AsyncSession = Depends(get_db),
):
    status = data.get("status")
    if status not in {"DRAFT", "VALIDATED", "REJECTED", "EXPIRED"}:
        raise HTTPException(400, "status inválido")

    result = await db.execute(
        select(Quotation)
        .where(Quotation.quote_id == quote_id)
        .order_by(Quotation.version.desc())
    )
    q = result.scalars().first()
    if not q:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")

    q.status = status
    await db.commit()
    return {"quote_id": q.quote_id, "status": q.status}


def _step_narrative(step: dict, quotation: Quotation | None = None) -> dict:
    name = step.get("step", "")
    agent = step.get("agent", "unknown")
    labels = {
        "route_to_sales_rabbitmq": (
            "El orquestador envio la solicitud al agente de ventas",
            "Identifico que la consulta debia pasar por el flujo comercial y publico el evento para ventas.",
        ),
        "sales_package_request": (
            "Ventas selecciono o preparo el paquete base",
            "Reviso destino, presupuesto, fechas y catalogo disponible para construir la solicitud de paquete.",
        ),
        "route_to_quotation-agent": (
            "El orquestador envio el paquete al agente de cotizacion",
            "Conecto la decision comercial con el calculo financiero de la cotizacion.",
        ),
        "route_to_quotation_agent": (
            "El orquestador envio el paquete al agente de cotizacion",
            "Conecto la decision comercial con el calculo financiero de la cotizacion.",
        ),
        "quotation_calculated": (
            "Cotizacion calculo el precio final",
            "Aplico precio base, cantidad de viajeros, margen comercial e impuestos antes de guardar la cotizacion.",
        ),
        "route_to_validation-agent": (
            "El orquestador envio la cotizacion a validacion",
            "Pidio una revision de reglas de negocio antes de marcar la cotizacion como usable.",
        ),
        "route_to_validation_agent": (
            "El orquestador envio la cotizacion a validacion",
            "Pidio una revision de reglas de negocio antes de marcar la cotizacion como usable.",
        ),
        "validation_complete": (
            "Validacion aprobo las reglas de negocio",
            "Verifico margen minimo, costo positivo, vigencia y desglose antes de aprobar el resultado.",
        ),
        "pipeline_quotation_complete": (
            "Pipeline multiagente completo",
            "El flujo secuencial genero, calculo y valido la cotizacion.",
        ),
    }
    title, summary = labels.get(
        name,
        (name.replace("_", " ").strip().capitalize(), "Paso registrado por el flujo multiagente."),
    )
    if name == "quotation_calculated" and quotation:
        summary = (
            f"Calculo un total de {quotation.currency} {float(quotation.total_cost):.2f} "
            f"con margen de {float(quotation.margin_pct):.2f}%."
        )
    return {
        "step": name,
        "agent": agent,
        "status": step.get("status"),
        "timestamp": step.get("timestamp"),
        "output_ref": step.get("output_ref"),
        "error": step.get("error"),
        "title": title,
        "summary": summary,
    }


@router.get("/{quote_id}/agent-history")
async def get_quotation_agent_history(quote_id: str, db: AsyncSession = Depends(get_db)):
    q_result = await db.execute(
        select(Quotation)
        .where(Quotation.quote_id == quote_id)
        .order_by(Quotation.version.desc())
    )
    quotation = q_result.scalars().first()
    if not quotation:
        raise HTTPException(status_code=404, detail="Cotización no encontrada")

    sagas_result = await db.execute(select(Saga).order_by(desc(Saga.created_at)).limit(200))
    matching_saga = None
    for saga in sagas_result.scalars().all():
        steps = saga.steps or []
        if any(quote_id in str(step.get("output_ref", "")) for step in steps):
            matching_saga = saga
            break

    validation_result = await db.execute(
        select(ValidationLog)
        .where(ValidationLog.entity_id == quote_id)
        .order_by(desc(ValidationLog.audited_at))
    )
    validation_logs = validation_result.scalars().all()

    if matching_saga:
        timeline = [
            _step_narrative(step, quotation)
            for step in (matching_saga.steps or [])
        ]
        saga_payload = {
            "saga_id": str(matching_saga.id),
            "saga_type": matching_saga.saga_type,
            "status": matching_saga.status,
            "initiated_by": matching_saga.initiated_by,
            "context": matching_saga.context,
            "created_at": matching_saga.created_at.isoformat() if matching_saga.created_at else None,
            "completed_at": matching_saga.completed_at.isoformat() if matching_saga.completed_at else None,
        }
    else:
        timeline = [{
            "step": "direct_quotation",
            "agent": quotation.created_by_agent or "api-gateway",
            "status": quotation.status,
            "timestamp": quotation.created_at.isoformat() if quotation.created_at else None,
            "output_ref": f"quote:{quote_id}:v{quotation.version}",
            "error": None,
            "title": "Cotizacion directa",
            "summary": "Esta cotizacion se genero por el flujo directo, sin saga multiagente asociada.",
        }]
        saga_payload = None

    return {
        "quote_id": quote_id,
        "saga": saga_payload,
        "timeline": timeline,
        "validation_logs": [
            {
                "id": str(log.id),
                "overall_status": log.overall_status,
                "rules_checked": log.rules_checked,
                "compliance_flags": log.compliance_flags,
                "audited_by_agent": log.audited_by_agent,
                "audited_at": log.audited_at.isoformat() if log.audited_at else None,
            }
            for log in validation_logs
        ],
    }


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
        "line_items": q.line_items or [], "margin_pct": float(q.margin_pct),
        "valid_until": q.valid_until.isoformat() if q.valid_until else None,
        "customizations": q.customizations or {},
        "created_at": q.created_at.isoformat() if q.created_at else None,
        "created_by_agent": q.created_by_agent,
    }
