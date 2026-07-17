# ADR-006 — `Decimal` en cálculos financieros

**Estado:** Aceptado

## Contexto
`QuotationAgent`, `FinanceAgent` y `ValidationAgent` calculan márgenes, IGV y totales que
terminan en registros contables inmutables (`quotations`, `liquidations`, `transactions`).

## Decisión
Usar `decimal.Decimal` (con `ROUND_HALF_UP` explícito) en toda la aritmética financiera,
nunca `float`.

## Alternativas consideradas
| Alternativa | Por qué no |
|---|---|
| `float` | Acumula errores de representación binaria (`0.1 + 0.2 != 0.3`) que son inaceptables en registros contables inmutables — un error de redondeo no se puede "corregir" retroactivamente sin violar la inmutabilidad del ledger. |

## Consecuencias
- Los totales son exactos y reproducibles bit a bit entre corridas.
- Costo: `Decimal` no es serializable nativamente a JSON — todos los payloads MCP convierten explícitamente a `float` solo en el borde de serialización (`float(total_cost)`), manteniendo `Decimal` internamente durante el cálculo.
