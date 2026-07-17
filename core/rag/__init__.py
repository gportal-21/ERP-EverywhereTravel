"""RAG — Retrieval-Augmented Generation sobre PostgreSQL + pgvector.

Componentes:
- embedder.py: genera embeddings vía Ollama (nomic-embed-text, 768 dim)
- content.py: fuentes de conocimiento curadas (paquetes turísticos, guías de destino)

La recuperación en sí (similaridad de coseno) vive en la capa API
(api/routes/packages.py::semantic_search_packages, api/routes/knowledge.py)
porque es la única capa con sesión directa a PostgreSQL — los agentes
consultan estos endpoints por HTTP, igual que el resto del acceso a datos
en este sistema (ver DB_API_URL en agents/base_agent.py y agentes individuales).
"""
