import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models import Package

router = APIRouter()


@router.get("")
@router.get("/")
async def list_packages(
    include_inactive: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Package)
    if not include_inactive:
        stmt = stmt.where(Package.is_active == True)
    result = await db.execute(stmt)
    packages = result.scalars().all()
    return {"packages": [
        {
            "id": str(p.id), "name": p.name, "destination": p.destination,
            "base_price": float(p.base_price), "duration_days": p.duration_days,
            "includes": p.includes, "excludes": p.excludes,
            "package_type": p.package_type, "is_active": p.is_active,
            "description": p.description, "currency": p.currency,
        }
        for p in packages
    ]}


@router.get("/search")
async def search_packages(
    destination: str = "",
    budget_max: float = 999999,
    duration_days_min: int = 0,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Package).where(and_(Package.is_active == True, Package.base_price <= budget_max))
    if destination:
        stmt = stmt.where(Package.destination.ilike(f"%{destination}%"))
    if duration_days_min:
        stmt = stmt.where(Package.duration_days >= duration_days_min)
    result = await db.execute(stmt)
    packages = result.scalars().all()
    return {"packages": [
        {
            "id": str(p.id), "name": p.name, "destination": p.destination,
            "base_price": float(p.base_price), "duration_days": p.duration_days,
            "includes": p.includes, "package_type": p.package_type,
        }
        for p in packages
    ]}


@router.post("/")
async def create_package(data: dict, db: AsyncSession = Depends(get_db)):
    p = Package(
        id=str(uuid.uuid4()),
        name=data["name"],
        package_type=data.get("package_type", "PREDEFINED"),
        destination=data["destination"],
        description=data.get("description"),
        base_price=data.get("base_price", 0),
        currency=data.get("currency", "PEN"),
        duration_days=data.get("duration_days", 0),
        includes=data.get("includes", []),
        excludes=data.get("excludes", []),
        is_active=True,
    )
    db.add(p)
    await db.commit()
    return {"id": str(p.id), "name": p.name, "destination": p.destination}


@router.get("/{package_id}")
async def get_package(package_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Package).where(Package.id == package_id))
    pkg = result.scalar_one_or_none()
    if not pkg:
        raise HTTPException(status_code=404, detail="Paquete no encontrado")
    return {
        "id": str(pkg.id), "name": pkg.name, "destination": pkg.destination,
        "base_price": float(pkg.base_price), "duration_days": pkg.duration_days,
        "includes": pkg.includes, "excludes": pkg.excludes,
        "package_type": pkg.package_type, "is_active": pkg.is_active,
        "description": pkg.description, "currency": pkg.currency,
    }


@router.patch("/{package_id}")
async def update_package(package_id: str, data: dict, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Package).where(Package.id == package_id))
    pkg = result.scalar_one_or_none()
    if not pkg:
        raise HTTPException(404, "Paquete no encontrado")
    for field in ("name", "destination", "description", "base_price", "duration_days", "includes", "excludes", "is_active"):
        if field in data and data[field] is not None:
            setattr(pkg, field, data[field])
    await db.commit()
    return {"id": str(pkg.id), "name": pkg.name, "base_price": float(pkg.base_price), "is_active": pkg.is_active}


@router.delete("/{package_id}")
async def deactivate_package(package_id: str, db: AsyncSession = Depends(get_db)):
    """Soft delete — desactiva el paquete sin eliminarlo."""
    result = await db.execute(select(Package).where(Package.id == package_id))
    pkg = result.scalar_one_or_none()
    if not pkg:
        raise HTTPException(404, "Paquete no encontrado")
    pkg.is_active = False
    await db.commit()
    return {"id": package_id, "is_active": False}
