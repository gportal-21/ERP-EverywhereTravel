import uuid as _uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models import DocumentJob

router = APIRouter()


@router.post("")
@router.post("/")
async def create_job(data: dict, db: AsyncSession = Depends(get_db)):
    job = DocumentJob(
        id=data.get("id", str(_uuid.uuid4())),
        document_type=data.get("document_type", "UNKNOWN"),
        reference_id=data.get("reference_id"),
        reference_type=data.get("reference_type", "unknown"),
        template_data=data.get("template_data", {}),
        status=data.get("status", "PENDING"),
        document_url=data.get("document_url"),
        requested_by_agent=data.get("requested_by_agent", "unknown"),
    )
    db.add(job)
    await db.commit()
    return {"job_id": str(job.id), "status": job.status}


@router.patch("/{job_id}")
async def update_job(job_id: str, data: dict, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DocumentJob).where(DocumentJob.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(404, "Job no encontrado")
    if "status" in data:
        job.status = data["status"]
    if "document_url" in data and data["document_url"]:
        job.document_url = data["document_url"]
    if "error_message" in data:
        job.error_message = data["error_message"]
    await db.commit()
    return {"job_id": job_id, "status": job.status}


@router.get("/{job_id}")
async def get_job(job_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DocumentJob).where(DocumentJob.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(404, "Job no encontrado")
    return {
        "job_id": str(job.id), "document_type": job.document_type,
        "status": job.status, "document_url": job.document_url,
    }
