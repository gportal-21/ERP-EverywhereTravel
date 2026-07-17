#!/usr/bin/env python3
"""
Build RAG Index — Everywhere Travel Sistema Multiagente

(Re)genera los embeddings del subsistema RAG:
1. Paquetes turísticos sin embedding (packages.embedding IS NULL)
2. Base de conocimiento de destinos (core/rag/content.py → destination_knowledge)

Requisitos:
    Sistema corriendo: docker compose up -d
    Ollama corriendo en el host con el modelo de embeddings descargado:
        ollama pull nomic-embed-text

Uso:
    python scripts/build_rag_index.py
    python scripts/build_rag_index.py --api-url http://localhost:8000
"""
from __future__ import annotations

import argparse
import sys

import httpx


def main() -> int:
    parser = argparse.ArgumentParser(description="Indexa el subsistema RAG (paquetes + conocimiento de destinos)")
    parser.add_argument("--api-url", default="http://localhost:8000", help="URL base de la API (default: %(default)s)")
    args = parser.parse_args()

    print(f"[RAG] Indexando contra {args.api_url} ...")

    with httpx.Client(base_url=args.api_url, timeout=120) as client:
        print("\n[1/2] Reindexando paquetes turísticos...")
        resp = client.post("/api/v1/packages/reindex")
        resp.raise_for_status()
        data = resp.json()
        print(f"      indexados={data['indexed']} omitidos={data['skipped']} pendientes_totales={data['total_pending']}")
        if data["skipped"] > 0:
            print("      ADVERTENCIA: hay paquetes sin embedding — ¿Ollama está corriendo y accesible?")

        print("\n[2/2] Reindexando base de conocimiento de destinos...")
        resp = client.post("/api/v1/knowledge/destinations/reindex")
        resp.raise_for_status()
        data = resp.json()
        print(f"      insertados={data['inserted']} omitidos={data['skipped']}")
        if data["skipped"] > 0:
            print("      ADVERTENCIA: hay chunks sin embedding — ¿Ollama está corriendo y accesible?")

    print("\n[RAG] Indexación completa.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
