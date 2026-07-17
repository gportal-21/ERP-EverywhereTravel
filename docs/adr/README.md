# Registro de Decisiones de Arquitectura (ADR) — Everywhere Travel

Formato: [MADR](https://adr.github.io/madr/) simplificado (Contexto / Decisión / Consecuencias).
Cada ADR es inmutable una vez aceptado — si una decisión cambia, se crea un ADR nuevo que
supersede al anterior (no se edita el original).

| ADR | Título | Estado |
|---|---|---|
| [001](ADR-001-saga-vs-langgraph.md) | Orquestación Saga + Event Bus en vez de LangGraph | Aceptado |
| [002](ADR-002-ollama-vs-anthropic.md) | Ollama local como proveedor LLM por defecto | Aceptado |
| [003](ADR-003-topologia-hibrida.md) | Topología híbrida jerárquica-estrella | Aceptado |
| [004](ADR-004-optimistic-locking-redis.md) | Optimistic locking con Redis SETNX | Aceptado |
| [005](ADR-005-rabbitmq-vs-kafka.md) | RabbitMQ topic exchange en vez de Kafka | Aceptado |
| [006](ADR-006-decimal-en-finanzas.md) | `Decimal` en cálculos financieros | Aceptado |
| [007](ADR-007-audit-log-inmutable.md) | Audit log inmutable en vez de soft delete | Aceptado |
| [008](ADR-008-doble-validacion-schema.md) | JSON Schema Draft-07 + Pydantic (doble validación) | Aceptado |
| [009](ADR-009-rag-pgvector.md) | RAG con pgvector + embeddings Ollama, sin LangChain retrievers | Aceptado |
| [010](ADR-010-salida-estructurada-forzada.md) | Salida estructurada forzada (constrained decoding) sobre prompt-only | Aceptado |
| [011](ADR-011-evaluacion-local-sin-langsmith.md) | Evaluación local (golden set) en vez de LangSmith | Aceptado |
| [012](ADR-012-deep-agents-vs-multiagente-especializado.md) | Agentes especializados de flujo fijo en vez de patrón Deep Agent | Aceptado |
