import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models import Client

router = APIRouter()


@router.post("/")
async def create_client(data: dict, db: AsyncSession = Depends(get_db)):
    c = Client(
        id=str(uuid.uuid4()),
        full_name=data["full_name"],
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
    return {"id": str(c.id), "full_name": c.full_name, "email": c.email, "preferences": c.preferences}


@router.get("")
@router.get("/")
async def list_clients(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Client).limit(50))
    clients = result.scalars().all()
    return {"clients": [{"id": str(c.id), "full_name": c.full_name, "email": c.email} for c in clients]}
