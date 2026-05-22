from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models import Package

router = APIRouter()


@router.get("/search")
async def search_packages(
    destination: str = "",
    budget_max: float = 999999,
    duration_days_min: int = 0,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Package).where(
        and_(
            Package.is_active == True,
            Package.base_price <= budget_max,
        )
    )
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
    }


@router.get("")
@router.get("/")
async def list_packages(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Package).where(Package.is_active == True))
    packages = result.scalars().all()
    return {"packages": [{"id": str(p.id), "name": p.name, "destination": p.destination, "base_price": float(p.base_price)} for p in packages]}
