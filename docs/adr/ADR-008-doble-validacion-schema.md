# ADR-008 — JSON Schema Draft-07 + Pydantic (doble validación)

**Estado:** Aceptado

## Contexto
Cada `MCPEnvelope` transporta un payload tipado (`PackageRequest`, `QuotationResult`, etc.)
que debe validarse tanto en el productor como en el consumidor del mensaje.

## Decisión
Mantener **dos** representaciones del mismo contrato: modelos Pydantic v2
(`core/mcp/envelope.py`) para validación en tiempo de ejecución en Python, y JSON Schema
Draft-07 (`schemas/*.json`) validado por `core/mcp/validator.py` en cada hop del bus.

## Alternativas consideradas
| Alternativa | Por qué no |
|---|---|
| Solo Pydantic | Pydantic valida en Python; JSON Schema es el estándar que puede validar el mismo contrato desde el frontend (TypeScript), tests de contrato en cualquier lenguaje, o herramientas externas — necesario porque el frontend Next.js también consume estos payloads. |

## Consecuencias
- El contrato está definido dos veces — riesgo real de que diverjan si se edita uno sin el otro. Mitigado documentando ambos en `docs/agent_contracts.md` como fuente de verdad narrativa.
- Cada mensaje se valida dos veces (Pydantic al construir el envelope, JSON Schema al recibirlo) — costo de CPU marginal, aceptable dado el volumen del sistema.
