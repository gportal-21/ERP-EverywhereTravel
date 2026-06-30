import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models import Client

router = APIRouter()


@router.get("")
@router.get("/")
async def list_clients(
    search: str | None = Query(None),
    limit: int = Query(100, le=500),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Client).order_by(Client.full_name).limit(limit)
    if search:
        like = f"%{search}%"
        stmt = stmt.where(or_(
            Client.full_name.ilike(like),
            Client.email.ilike(like),
            Client.document_number.ilike(like),
        ))
    result = await db.execute(stmt)
    clients = result.scalars().all()
    return {"clients": [
        {
            "id": str(c.id), "full_name": c.full_name, "email": c.email,
            "phone": c.phone, "document_type": c.document_type,
            "document_number": c.document_number,
        }
        for c in clients
    ]}


@router.post("/")
async def create_client(data: dict, db: AsyncSession = Depends(get_db)):
    full_name = data.get("full_name") or data.get("name")
    if not full_name:
        raise HTTPException(400, "El nombre del cliente es requerido")
    if not data.get("email"):
        raise HTTPException(400, "El email del cliente es requerido")

    c = Client(
        id=str(uuid.uuid4()),
        full_name=full_name,
        email=data["email"],
        phone=data.get("phone"),
        document_type=data.get("document_type"),
        document_number=data.get("document_number"),
        preferences=data.get("preferences", {}),
    )
    db.add(c)
    await db.commit()
    return {"id": str(c.id), "full_name": c.full_name, "email": c.email}


@router.get("/{client_id}")
async def get_client(client_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Client).where(Client.id == client_id))
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Cliente no encontrado")
    return {
        "id": str(c.id), "full_name": c.full_name, "email": c.email,
        "phone": c.phone, "document_type": c.document_type,
        "document_number": c.document_number, "preferences": c.preferences,
    }


@router.patch("/{client_id}")
async def update_client(client_id: str, data: dict, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Client).where(Client.id == client_id))
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Cliente no encontrado")
    for field in ("full_name", "email", "phone", "document_type", "document_number"):
        if field in data and data[field] is not None:
            setattr(c, field, data[field])
    await db.commit()
    return {"id": str(c.id), "full_name": c.full_name, "email": c.email, "phone": c.phone}


@router.delete("/{client_id}")
async def delete_client(client_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Client).where(Client.id == client_id))
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Cliente no encontrado")
    await db.delete(c)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="No se puede eliminar el cliente porque tiene cotizaciones o reservas asociadas",
        )
    return {"deleted": True, "id": client_id}
