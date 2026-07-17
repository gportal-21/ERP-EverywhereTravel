import logging
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models import Package
from core.rag.embedder import embed_text

router = APIRouter()
logger = logging.getLogger(__name__)


def _package_embedding_text(p: Package) -> str:
    includes = ", ".join(p.includes) if isinstance(p.includes, list) else ""
    return (
        f"{p.name}. Destino: {p.destination}. {p.description or ''}. "
        f"Incluye: {includes}. Duración: {p.duration_days} días."
    ).strip()


async def _try_embed_package(p: Package) -> None:
    """Genera y asigna el embedding del paquete; no falla la request si Ollama
    no está disponible (queda NULL y scripts/build_rag_index.py lo completa después)."""
    embedding = await embed_text(_package_embedding_text(p))
    if embedding is not None:
        p.embedding = embedding
    else:
        logger.warning("[RAG] No se pudo generar embedding para el paquete %s (Ollama no disponible)", p.id)


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


@router.get("/semantic-search")
async def semantic_search_packages(
    query: str,
    top_k: int = Query(5, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
):
    """Búsqueda RAG: recupera paquetes por similaridad semántica (coseno) sobre
    su embedding, en vez de filtros exactos de destino/presupuesto.
    Usado como fallback por SalesAgent cuando la búsqueda estructurada
    (`/packages/search`) no encuentra resultados (ej. preferencias descriptivas
    o variaciones de nombre de destino que un filtro `ilike` no captura)."""
    embedding = await embed_text(query)
    if embedding is None:
        raise HTTPException(503, "Servicio de embeddings (Ollama) no disponible")

    stmt = (
        select(Package)
        .where(Package.is_active == True, Package.embedding.isnot(None))
        .order_by(Package.embedding.cosine_distance(embedding))
        .limit(top_k)
    )
    result = await db.execute(stmt)
    packages = result.scalars().all()
    return {"packages": [
        {
            "id": str(p.id), "name": p.name, "destination": p.destination,
            "base_price": float(p.base_price), "duration_days": p.duration_days,
            "includes": p.includes, "package_type": p.package_type,
            "description": p.description,
        }
        for p in packages
    ]}


@router.post("/reindex")
async def reindex_packages(db: AsyncSession = Depends(get_db)):
    """Genera embeddings para paquetes activos que aún no tienen (embedding IS NULL).
    Usado por scripts/build_rag_index.py tras poblar el catálogo o si Ollama
    estuvo caído durante la creación de algún paquete."""
    result = await db.execute(select(Package).where(Package.is_active == True, Package.embedding.is_(None)))
    pending = result.scalars().all()

    indexed, skipped = 0, 0
    for p in pending:
        embedding = await embed_text(_package_embedding_text(p))
        if embedding is not None:
            p.embedding = embedding
            indexed += 1
        else:
            skipped += 1

    await db.commit()
    logger.info("[RAG] Reindex packages: %d indexados, %d omitidos (sin Ollama)", indexed, skipped)
    return {"indexed": indexed, "skipped": skipped, "total_pending": len(pending)}


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
    await _try_embed_package(p)
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


_EMBEDDING_RELEVANT_FIELDS = {"name", "destination", "description", "includes", "duration_days"}


@router.patch("/{package_id}")
async def update_package(package_id: str, data: dict, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Package).where(Package.id == package_id))
    pkg = result.scalar_one_or_none()
    if not pkg:
        raise HTTPException(404, "Paquete no encontrado")
    changed_fields = set()
    for field in ("name", "destination", "description", "base_price", "duration_days", "includes", "excludes", "is_active"):
        if field in data and data[field] is not None:
            setattr(pkg, field, data[field])
            changed_fields.add(field)
    if changed_fields & _EMBEDDING_RELEVANT_FIELDS:
        await _try_embed_package(pkg)
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
