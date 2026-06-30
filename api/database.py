from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from api.config import settings

engine = create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


async def ensure_schema_compatibility() -> None:
    """Aplica ajustes idempotentes para instalaciones ya inicializadas."""
    statements = [
        "ALTER TYPE document_type ADD VALUE IF NOT EXISTS 'ITINERARY'",
        "ALTER TYPE document_type ADD VALUE IF NOT EXISTS 'RECEIPT'",
        "ALTER TABLE liquidations ADD COLUMN IF NOT EXISTS payment_schedule JSONB DEFAULT '[]'",
    ]
    async with engine.begin() as conn:
        for statement in statements:
            await conn.execute(text(statement))
