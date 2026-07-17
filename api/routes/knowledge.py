"""Knowledge Route — Búsqueda semántica sobre la base de conocimiento de destinos (RAG).

GET  /api/v1/knowledge/destinations/search?query=...  → chunks más relevantes (coseno)
POST /api/v1/knowledge/destinations/reindex           → (re)embebe core/rag/content.py

Consumido por ItineraryAgent (agents/itinerary/agent.py::_tool_get_destination_info)
como fuente RAG primaria, con el diccionario estático original como fallback si
este endpoint no está disponible.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models import DestinationKnowledge
from core.rag.content import DESTINATION_KNOWLEDGE
from core.rag.embedder import embed_text

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/destinations/search")
async def search_destination_knowledge(
    query: str,
    top_k: int = Query(3, ge=1, le=10),
    db: AsyncSession = Depends(get_db),
):
    embedding = await embed_text(query)
    if embedding is None:
        raise HTTPException(503, "Servicio de embeddings (Ollama) no disponible")

    stmt = (
        select(DestinationKnowledge)
        .where(DestinationKnowledge.embedding.isnot(None))
        .order_by(DestinationKnowledge.embedding.cosine_distance(embedding))
        .limit(top_k)
    )
    result = await db.execute(stmt)
    chunks = result.scalars().all()
    return {
        "query": query,
        "chunks": [
            {"destination": c.destination, "title": c.title, "content": c.content}
            for c in chunks
        ],
    }


@router.post("/destinations/reindex")
async def reindex_destination_knowledge(db: AsyncSession = Depends(get_db)):
    """(Re)genera la tabla destination_knowledge desde core/rag/content.py.
    Idempotente: borra y vuelve a insertar todo el contenido curado embebido."""
    await db.execute(delete(DestinationKnowledge))

    inserted, skipped = 0, 0
    for entry in DESTINATION_KNOWLEDGE:
        embedding = await embed_text(f"{entry['title']}. {entry['content']}")
        if embedding is None:
            skipped += 1
            continue
        db.add(DestinationKnowledge(
            destination=entry["destination"],
            title=entry["title"],
            content=entry["content"],
            embedding=embedding,
        ))
        inserted += 1

    await db.commit()
    logger.info("[RAG] Reindex destination_knowledge: %d insertados, %d omitidos (sin Ollama)", inserted, skipped)
    return {"inserted": inserted, "skipped": skipped}
