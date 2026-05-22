"""
Itinerary Route — Genera itinerario PDF de un viaje bajo demanda.

POST /api/v1/itinerary/{quote_id}  → Publica GenerateItinerary al ItineraryAgent
GET  /api/v1/itinerary/{quote_id}  → Retorna URL del itinerario si ya fue generado
"""
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models import DocumentJob, Quotation

router = APIRouter()


@router.post("/{quote_id}")
async def generate_itinerary(quote_id: str, db: AsyncSession = Depends(get_db)):
    """Dispara la generación del itinerario PDF para una cotización validada."""
    from api.main import app
    from core.mcp.envelope import MCPEnvelope

    # Verificar que la cotización existe y está validada
    q_res = await db.execute(
        select(Quotation)
        .where(Quotation.quote_id == quote_id)
        .order_by(desc(Quotation.version))
    )
    quotation = q_res.scalars().first()
    if not quotation:
        raise HTTPException(404, "Cotización no encontrada")
    if quotation.status not in ("VALIDATED", "DRAFT"):
        raise HTTPException(400, f"Solo se pueden generar itinerarios de cotizaciones válidas. Estado: {quotation.status}")

    saga_id = str(uuid.uuid4())
    payload = {
        "quote_id": quote_id,
        "client_id": str(quotation.client_id) if quotation.client_id else None,
        "package_id": str(quotation.package_id) if quotation.package_id else None,
        "line_items": quotation.line_items or [],
        "total_cost": float(quotation.total_cost),
        "status": quotation.status,
        "customizations": quotation.customizations or {},
        "destination": (quotation.customizations or {}).get("destination", "Destino turístico"),
        "start_date": (quotation.customizations or {}).get("start_date", ""),
        "end_date": (quotation.customizations or {}).get("end_date", ""),
        "traveler_count": (quotation.customizations or {}).get("traveler_count", 1),
    }

    envelope = MCPEnvelope(
        saga_id=saga_id,
        sender_agent="api-gateway",
        receiver_agent="itinerary-agent",
        payload_type="GenerateItinerary",
        payload=payload,
    )

    try:
        publisher = app.state.publisher
        await publisher.publish(envelope, "itinerary.generate")
        return {
            "status": "processing",
            "saga_id": saga_id,
            "quote_id": quote_id,
            "message": "El itinerario se está generando. Recibirás una notificación cuando esté listo.",
        }
    except Exception as e:
        raise HTTPException(500, f"Error publicando tarea de itinerario: {e}")


@router.get("/{quote_id}")
async def get_itinerary(quote_id: str, db: AsyncSession = Depends(get_db)):
    """Retorna el URL del itinerario generado para una cotización."""
    result = await db.execute(
        select(DocumentJob)
        .where(
            DocumentJob.reference_id == quote_id,
            DocumentJob.document_type == "ITINERARY",
            DocumentJob.status == "COMPLETE",
        )
        .order_by(desc(DocumentJob.created_at))
    )
    job = result.scalars().first()
    if not job:
        return {"status": "not_generated", "url": None}
    return {
        "status": "ready",
        "url": job.document_url,
        "generated_at": job.created_at.isoformat() if job.created_at else None,
    }
