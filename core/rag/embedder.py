"""Embedder — genera vectores de embedding vía la API local de Ollama.

Usa el endpoint estable `/api/embeddings` (no el más nuevo `/api/embed`) porque
es el que existe en todas las versiones de Ollama desplegadas para este proyecto.
"""
from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

EMBEDDING_DIMENSIONS = int(os.environ.get("EMBEDDING_DIMENSIONS", "768"))


def _embedding_model() -> str:
    return os.environ.get("EMBEDDING_MODEL", "nomic-embed-text")


def _base_url() -> str:
    base_url = os.environ.get("OLLAMA_BASE_URL") or os.environ.get("OLLAMA_HOST") or "http://localhost:11434"
    if not base_url.startswith(("http://", "https://")):
        base_url = f"http://{base_url}"
    return base_url.rstrip("/")


async def embed_text(text: str, *, timeout: float = 30.0) -> list[float] | None:
    """Genera el embedding de un texto. Retorna None si Ollama no está disponible
    (el llamador debe degradar con gracia: guardar sin embedding y reintentar luego
    vía scripts/build_rag_index.py, o caer a búsqueda estructurada/estática)."""
    text = (text or "").strip()
    if not text:
        return None

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{_base_url()}/api/embeddings",
                json={"model": _embedding_model(), "prompt": text},
            )
            response.raise_for_status()
            data = response.json()
            embedding = data.get("embedding")
            if not embedding or len(embedding) != EMBEDDING_DIMENSIONS:
                logger.warning(
                    "[RAG] Embedding con dimensión inesperada (%s): esperado %s",
                    len(embedding) if embedding else 0,
                    EMBEDDING_DIMENSIONS,
                )
                return None
            return embedding
    except Exception as exc:
        logger.warning("[RAG] embed_text falló (%s): %s", type(exc).__name__, exc)
        return None


def embed_text_sync(text: str, *, timeout: float = 30.0) -> list[float] | None:
    """Variante síncrona para uso dentro de Swarms tools (deben ser funciones síncronas)."""
    text = (text or "").strip()
    if not text:
        return None

    try:
        response = httpx.post(
            f"{_base_url()}/api/embeddings",
            json={"model": _embedding_model(), "prompt": text},
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()
        embedding = data.get("embedding")
        if not embedding or len(embedding) != EMBEDDING_DIMENSIONS:
            return None
        return embedding
    except Exception as exc:
        logger.warning("[RAG] embed_text_sync falló (%s): %s", type(exc).__name__, exc)
        return None
