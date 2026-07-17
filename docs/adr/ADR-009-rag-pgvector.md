# ADR-009 — RAG con pgvector + embeddings Ollama, sin LangChain retrievers

**Estado:** Aceptado

## Contexto
`SalesAgent` necesitaba recuperar paquetes por similaridad semántica cuando la búsqueda
estructurada (`destination ILIKE`) no encuentra resultados, e `ItineraryAgent` usaba un
diccionario Python hardcodeado como "base de conocimiento" de destinos — sin recuperación
semántica real. El sistema ya usa PostgreSQL como almacén persistente único.

## Decisión
Implementar RAG con **pgvector** (extensión de PostgreSQL) para almacenar embeddings de
paquetes (`packages.embedding`) y de una base de conocimiento curada de destinos
(`destination_knowledge`, ver `core/rag/content.py`), generados con el modelo de
embeddings local de Ollama (`nomic-embed-text`, 768 dim). La recuperación (similaridad de
coseno) se expone vía endpoints propios (`/api/v1/packages/semantic-search`,
`/api/v1/knowledge/destinations/search`) que los agentes consultan por HTTP — mismo patrón
que el resto del acceso a datos del sistema (agentes → API → PostgreSQL).

## Alternativas consideradas
| Alternativa | Por qué no |
|---|---|
| Vector store dedicado (Pinecone, Chroma, Weaviate) | Introduce un almacén de datos adicional cuando PostgreSQL con pgvector ya cubre el volumen del proyecto (catálogo de paquetes + guías de destino, no un corpus masivo); menos piezas operativas para desplegar y respaldar. |
| Retrievers de LangChain | El sistema no usa LangChain como framework de orquestación (ver [ADR-001](ADR-001-saga-vs-langgraph.md)) y de hecho neutraliza activamente `langchain_community` en `agents/swarms_compat.py` para evitar sus dependencias pesadas (PyTorch/transformers) — introducir sus retrievers solo para RAG rompería esa decisión sin necesidad, cuando una consulta SQL con el operador `<=>` de pgvector logra lo mismo. |

## Consecuencias
- RAG genuino: los paquetes/destinos se recuperan por similaridad semántica real, no por coincidencia exacta de string.
- El catálogo pequeño (decenas de paquetes) no justifica un índice ANN sofisticado — el índice `ivfflat` se crea igualmente por completitud, pero con este volumen un scan secuencial sería igual de rápido.
- Si Ollama no está disponible, `embed_text()` retorna `None` y los endpoints de búsqueda semántica responden `503` — los agentes degradan a su fallback determinístico existente (mismo patrón que el resto del sistema ante fallos de LLM).
