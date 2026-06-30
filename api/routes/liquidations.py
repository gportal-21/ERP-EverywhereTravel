import uuid
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models import DocumentJob, Liquidation, Transaction, Reservation, Package

router = APIRouter()

COMMISSION_RATE = Decimal("0.08")


def _build_schedule(total: Decimal) -> list:
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    if total <= Decimal("1000"):
        return [{"due_date": now.isoformat(), "amount": float(total), "pct": 100, "paid": False}]
    elif total <= Decimal("5000"):
        return [
            {"due_date": now.isoformat(), "amount": float(total * Decimal("0.5")), "pct": 50, "paid": False},
            {"due_date": (now + timedelta(days=30)).isoformat(), "amount": float(total * Decimal("0.5")), "pct": 50, "paid": False},
        ]
    else:
        return [
            {"due_date": now.isoformat(), "amount": float(total * Decimal("0.3")), "pct": 30, "paid": False},
            {"due_date": (now + timedelta(days=30)).isoformat(), "amount": float(total * Decimal("0.4")), "pct": 40, "paid": False},
            {"due_date": (now + timedelta(days=60)).isoformat(), "amount": float(total * Decimal("0.3")), "pct": 30, "paid": False},
        ]


async def _get_or_create_liquidation(reservation: Reservation, db: AsyncSession) -> Liquidation:
    """Obtiene la liquidación existente o crea una nueva si no existe."""
    liq_res = await db.execute(
        select(Liquidation).where(Liquidation.reservation_id == str(reservation.id))
    )
    liq = liq_res.scalar_one_or_none()
    if liq:
        return liq

    # Auto-calcular total desde el paquete
    total = Decimal("0")
    if reservation.package_id:
        pkg_res = await db.execute(select(Package).where(Package.id == str(reservation.package_id)))
        pkg = pkg_res.scalar_one_or_none()
        if pkg:
            total = Decimal(str(pkg.base_price)) * reservation.traveler_count

    commission = (total * COMMISSION_RATE).quantize(Decimal("0.01"))
    schedule = _build_schedule(total)

    liq = Liquidation(
        id=str(uuid.uuid4()),
        liquidation_code=f"LIQ-{uuid.uuid4().hex[:8].upper()}",
        reservation_id=str(reservation.id),
        total_charged=float(total),
        total_paid=0,
        commission_amount=float(commission),
        status="PARTIAL",
        payment_schedule=schedule,
    )
    db.add(liq)
    await db.flush()  # Obtiene el ID sin commit
    return liq


@router.get("")
@router.get("/")
async def list_liquidations(
    status: str | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import text
    stmt = select(Liquidation).order_by(desc(Liquidation.created_at)).limit(limit)
    if status:
        stmt = stmt.where(text("liquidations.status::text = :s").bindparams(s=status))
    result = await db.execute(stmt)
    liqs = result.scalars().all()
    return {"liquidations": [
        {
            "id": str(l.id),
            "liquidation_code": l.liquidation_code,
            "reservation_id": str(l.reservation_id) if l.reservation_id else None,
            "total_charged": float(l.total_charged),
            "total_paid": float(l.total_paid),
            "balance": float(l.total_charged) - float(l.total_paid),
            "commission_amount": float(l.commission_amount),
            "status": l.status,
            "payment_schedule": l.payment_schedule or [],
            "created_at": l.created_at.isoformat() if l.created_at else None,
        }
        for l in liqs
    ]}


@router.get("/{reservation_code}")
async def get_liquidation_by_reservation(reservation_code: str, db: AsyncSession = Depends(get_db)):
    """Retorna la liquidación de una reserva, creándola si no existe."""
    res = await db.execute(
        select(Reservation).where(Reservation.reservation_code == reservation_code)
    )
    reservation = res.scalar_one_or_none()
    if not reservation:
        raise HTTPException(404, "Reserva no encontrada")

    liq = await _get_or_create_liquidation(reservation, db)
    await db.commit()

    # Obtener transacciones
    txs = await db.execute(
        select(Transaction)
        .where(Transaction.liquidation_id == str(liq.id))
        .order_by(desc(Transaction.created_at))
    )
    transactions = txs.scalars().all()

    return {
        "reservation_code": reservation_code,
        "reservation_status": reservation.status,
        "travel_start": reservation.travel_start.isoformat(),
        "travel_end": reservation.travel_end.isoformat(),
        "traveler_count": reservation.traveler_count,
        "liquidation_code": liq.liquidation_code,
        "total_charged": float(liq.total_charged),
        "total_paid": float(liq.total_paid),
        "balance": float(liq.total_charged) - float(liq.total_paid),
        "commission_amount": float(liq.commission_amount),
        "status": liq.status,
        "payment_schedule": liq.payment_schedule or [],
        "transactions": [
            {
                "id": str(t.id),
                "amount": float(t.amount),
                "method": t.payment_method,
                "reference": t.reference,
                "date": t.created_at.isoformat() if t.created_at else None,
            }
            for t in transactions
        ],
    }


@router.post("/")
async def create_liquidation(data: dict, db: AsyncSession = Depends(get_db)):
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

    # Auto-crear liquidación si no existe
    liq = await _get_or_create_liquidation(reservation, db)

    amount = float(data.get("amount", 0))
    if amount <= 0:
        raise HTTPException(400, "El monto debe ser mayor a 0")

    total_charged = float(liq.total_charged)
    total_paid    = float(liq.total_paid)
    balance       = total_charged - total_paid

    # Validar que no se haya saldado ya
    if total_charged > 0 and balance <= 0:
        raise HTTPException(400, "Esta reserva ya está completamente pagada")

    # Validar que el pago no exceda el saldo pendiente
    if total_charged > 0 and amount > round(balance, 2):
        raise HTTPException(
            400,
            f"El monto S/. {amount:.2f} supera el saldo pendiente de S/. {balance:.2f}. "
            f"Para adelantar cuotas paga exactamente el saldo completo o un monto menor."
        )

    tx = Transaction(
        id=str(uuid.uuid4()),
        liquidation_id=str(liq.id),
        amount=amount,
        payment_method=data.get("method", "TRANSFER"),
        reference=data.get("reference", f"REF-{uuid.uuid4().hex[:8].upper()}"),
        recorded_by_agent=data.get("recorded_by_agent", "api-gateway"),
    )
    db.add(tx)
    liq.total_paid = float(liq.total_paid) + amount

    if float(liq.total_paid) >= float(liq.total_charged) and float(liq.total_charged) > 0:
        liq.status = "COMPLETE"
        reservation.status = "CONFIRMED"
    elif float(liq.total_paid) > 0:
        liq.status = "PARTIAL"

    await db.commit()

    new_balance = float(liq.total_charged) - float(liq.total_paid)
    previous    = float(liq.total_paid) - amount

    # Generar recibo PDF de forma asíncrona
    receipt_url = await _generate_receipt_pdf(
        tx_id=str(tx.id),
        reservation=reservation,
        liq=liq,
        amount=amount,
        method=data.get("method", "TRANSFER"),
        reference=tx.reference,
        new_balance=new_balance,
        previous_payments=previous,
    )

    if receipt_url:
        receipt_job = DocumentJob(
            id=str(uuid.uuid4()),
            document_type="RECEIPT",
            reference_id=str(reservation.id),
            reference_type="reservation",
            template_data={
                "transaction_id": str(tx.id),
                "reservation_code": reservation.reservation_code,
                "liquidation_code": liq.liquidation_code,
                "amount": amount,
                "method": data.get("method", "TRANSFER"),
                "reference": tx.reference,
                "balance": new_balance,
            },
            status="COMPLETE",
            requested_by_agent=data.get("recorded_by_agent", "api-gateway"),
            document_url=receipt_url,
        )
        db.add(receipt_job)
        await db.commit()

    return {
        "transaction_id": str(tx.id),
        "liquidation_code": liq.liquidation_code,
        "total_charged": float(liq.total_charged),
        "total_paid": float(liq.total_paid),
        "balance": new_balance,
        "status": liq.status,
        "reservation_status": reservation.status,
        "receipt_url": receipt_url,
    }


async def _generate_receipt_pdf(
    tx_id: str, reservation, liq, amount: float,
    method: str, reference: str, new_balance: float, previous_payments: float
) -> str | None:
    """Genera el PDF del recibo de pago y lo sube a MinIO."""
    import io, asyncio
    from pathlib import Path
    from datetime import datetime
    from jinja2 import Environment, FileSystemLoader, select_autoescape
    import boto3, os

    TEMPLATES_DIR = Path(__file__).parent.parent.parent / "agents" / "document" / "templates"
    BUCKET = "everywheretravel-docs"

    try:
        # Render HTML
        env = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            autoescape=select_autoescape(["html"]),
        )
        template = env.get_template("receipt.html")
        total_charged = float(liq.total_charged)
        pct = int((float(liq.total_paid) / total_charged * 100)) if total_charged > 0 else 100

        html = template.render(
            receipt_number=f"REC-{datetime.now().strftime('%Y%m%d')}-{tx_id[:6].upper()}",
            issue_date=datetime.now().strftime("%d/%m/%Y %H:%M"),
            reservation_code=reservation.reservation_code,
            reservation_status=reservation.status,
            client_name="Cliente Everywhere Travel",
            client_doc=None,
            destination=None,
            travel_dates=f"{reservation.travel_start.strftime('%d/%m/%Y')} → {reservation.travel_end.strftime('%d/%m/%Y')}",
            payment_method=method,
            payment_reference=reference,
            amount_paid=amount,
            total_charged=total_charged,
            total_paid=float(liq.total_paid),
            previous_payments=previous_payments,
            balance=max(0, new_balance),
            payment_pct=pct,
        )

        # HTML → PDF
        from xhtml2pdf import pisa
        buf = io.BytesIO()
        pisa.CreatePDF(html.encode("utf-8"), dest=buf, encoding="utf-8")
        pdf_bytes = buf.getvalue()

        # Upload
        s3 = boto3.client(
            "s3",
            endpoint_url=f"http://{os.environ.get('MINIO_ENDPOINT','minio:9000')}",
            aws_access_key_id=os.environ.get("MINIO_ACCESS_KEY", "etminio"),
            aws_secret_access_key=os.environ.get("MINIO_SECRET_KEY", "etminiopass"),
        )
        try:
            s3.head_bucket(Bucket=BUCKET)
        except Exception:
            s3.create_bucket(Bucket=BUCKET)

        key = f"receipt/{datetime.now().strftime('%Y/%m')}/{tx_id}.pdf"
        content_type = "application/pdf" if pdf_bytes[:4] == b"%PDF" else "text/html"
        s3.put_object(Bucket=BUCKET, Key=key, Body=pdf_bytes, ContentType=content_type)
        url = s3.generate_presigned_url("get_object", Params={"Bucket": BUCKET, "Key": key}, ExpiresIn=604800)
        internal_url = f"http://{os.environ.get('MINIO_ENDPOINT','minio:9000')}"
        public_url = os.environ.get("MINIO_PUBLIC_URL", "http://localhost:9000")
        return url.replace(internal_url, public_url)

    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"[Receipt] Error generando recibo PDF: {e}")
        return None


@router.get("/{reservation_code}/receipt")
async def get_receipt(reservation_code: str, db: AsyncSession = Depends(get_db)):
    """Retorna el URL del último recibo generado para una reserva."""
    res = await db.execute(
        select(Reservation).where(Reservation.reservation_code == reservation_code)
    )
    reservation = res.scalar_one_or_none()
    if not reservation:
        raise HTTPException(404, "Reserva no encontrada")

    result = await db.execute(
        select(DocumentJob)
        .where(
            DocumentJob.reference_id == str(reservation.id),
            DocumentJob.document_type == "RECEIPT",
            DocumentJob.status == "COMPLETE",
        )
        .order_by(DocumentJob.created_at.desc())
    )
    job = result.scalars().first()
    if not job:
        return {"status": "not_generated", "url": None}
    return {"status": "ready", "url": job.document_url}


@router.patch("/{reservation_code}/adjust")
async def adjust_total(reservation_code: str, data: dict, db: AsyncSession = Depends(get_db)):
    """Ajustar el monto total de una liquidación manualmente."""
    res = await db.execute(
        select(Reservation).where(Reservation.reservation_code == reservation_code)
    )
    reservation = res.scalar_one_or_none()
    if not reservation:
        raise HTTPException(404, "Reserva no encontrada")

    liq = await _get_or_create_liquidation(reservation, db)
    new_total = float(data.get("total_charged", liq.total_charged))
    liq.total_charged = new_total
    liq.payment_schedule = _build_schedule(Decimal(str(new_total)))
    await db.commit()
    return {"liquidation_code": liq.liquidation_code, "total_charged": new_total}
