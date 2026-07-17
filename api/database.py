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
        # RAG (pgvector) — instalaciones creadas antes de que se agregara el subsistema RAG
        'CREATE EXTENSION IF NOT EXISTS "vector"',
        "ALTER TABLE packages ADD COLUMN IF NOT EXISTS embedding vector(768)",
        """
        CREATE TABLE IF NOT EXISTS destination_knowledge (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            destination VARCHAR(255) NOT NULL,
            title VARCHAR(255) NOT NULL,
            content TEXT NOT NULL,
            embedding vector(768),
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        # Trazas locales de interacción LLM (golden set / evaluación sin LangSmith)
        """
        CREATE TABLE IF NOT EXISTS agent_interaction_logs (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            saga_id UUID,
            agent_id VARCHAR(100) NOT NULL,
            action VARCHAR(255) NOT NULL,
            input_schema JSONB,
            output_schema JSONB,
            duration_ms INTEGER,
            tokens_used INTEGER,
            success BOOLEAN DEFAULT TRUE,
            error_message TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
    ]
    async with engine.begin() as conn:
        for statement in statements:
            await conn.execute(text(statement))

    # Índices ivfflat: requieren ejecutarse fuera del bloque anterior si la tabla
    # ya tiene filas de una instalación previa sin pgvector; CREATE INDEX IF NOT
    # EXISTS es idempotente y seguro de reintentar en cada arranque.
    index_statements = [
        "CREATE INDEX IF NOT EXISTS idx_packages_embedding "
        "ON packages USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)",
        "CREATE INDEX IF NOT EXISTS idx_destination_knowledge_embedding "
        "ON destination_knowledge USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50)",
        "CREATE INDEX IF NOT EXISTS idx_destination_knowledge_destination "
        "ON destination_knowledge(destination)",
    ]
    async with engine.begin() as conn:
        for statement in index_statements:
            await conn.execute(text(statement))
