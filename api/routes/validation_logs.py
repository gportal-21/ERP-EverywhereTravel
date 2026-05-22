import uuid
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models import ValidationLog

router = APIRouter()


@router.post("/")
async def create_validation_log(data: dict, db: AsyncSession = Depends(get_db)):
    log = ValidationLog(
        id=str(uuid.uuid4()),
        entity_type=data.get("entity_type", ""),
        entity_id=data.get("entity_id", str(uuid.uuid4())),
        rules_checked=data.get("rules_checked", []),
        overall_status=data.get("overall_status", "PASS"),
        compliance_flags=data.get("compliance_flags", []),
        audited_by_agent=data.get("audited_by_agent", "validation-agent"),
    )
    db.add(log)
    await db.commit()
    return {"id": str(log.id), "overall_status": log.overall_status}
