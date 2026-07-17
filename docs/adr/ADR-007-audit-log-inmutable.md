# ADR-007 — Audit log inmutable en vez de soft delete

**Estado:** Aceptado

## Contexto
`validation_logs` registra cada verificación de reglas de negocio (R001-R012) sobre
cotizaciones y reservas — es el rastro de compliance ante una auditoría.

## Decisión
`validation_logs` es una tabla append-only: sin `UPDATE` ni `DELETE` permitidos en
producción (documentado en `infrastructure/postgres/init.sql`). Cada nueva validación
inserta un registro nuevo, nunca modifica uno existente.

## Alternativas consideradas
| Alternativa | Por qué no |
|---|---|
| Soft delete (`is_active`/`deleted_at`) | Permite que un registro de auditoría "desaparezca" lógicamente o sea reinterpretado — inaceptable para compliance regulatorio (IGV Perú) donde el historial completo debe ser verificable. |

## Consecuencias
- Cualquier controversia sobre una cotización se resuelve consultando la secuencia completa de validaciones, sin riesgo de que un registro haya sido alterado.
- Costo: la tabla crece sin límite — se acepta porque el volumen (una fila por validación) es bajo comparado con, p. ej., logs de request HTTP; una estrategia de archivado (particionado por fecha) queda como trabajo futuro si el volumen creciera significativamente.
