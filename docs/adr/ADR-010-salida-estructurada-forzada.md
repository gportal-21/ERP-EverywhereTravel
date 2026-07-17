# ADR-010 — Salida estructurada forzada (constrained decoding) sobre prompt-only

**Estado:** Aceptado

## Contexto
Cada agente con LLM pedía "Return ONLY valid JSON" en el prompt y luego parseaba el texto
con regex/split de bloques ```` ```json ```` — sin ninguna garantía de que el modelo
respetara el formato. Con un modelo local de 8B (ver [ADR-002](ADR-002-ollama-vs-anthropic.md))
esto fallaba con más frecuencia que con un modelo frontier.

## Decisión
Definir el contrato de salida de cada agente como modelo Pydantic (`PackageRequest`,
`LineItemsOutput`, `ItineraryOutput`, `ConflictValidationOutput`, `ConflictMonitoringOutput`)
y pasar su `.model_json_schema()` como `response_schema` al `Agent` de
`agents/swarms_compat.py`, que lo reenvía como `format` a `/api/generate` de Ollama —
Ollama restringe el *decoding* token a token para que la salida cumpla el schema
(constrained decoding, disponible desde Ollama ≥ 0.5). `core/structured_output.py::parse_structured_output()`
valida el resultado contra el mismo modelo Pydantic como segunda capa de defensa, con
extracción manual como red de seguridad final.

## Alternativas consideradas
| Alternativa | Por qué no |
|---|---|
| Solo prompt engineering ("Return ONLY JSON") | Sin garantía real — el modelo puede envolver la respuesta en prosa, usar comillas simples, u olvidar un campo. Era el estado anterior del proyecto y fallaba de forma silenciosa hacia el fallback determinístico más seguido de lo necesario. |
| Librería `instructor` u otro wrapper de terceros | Añade una dependencia más sobre un proveedor (Ollama) que ya expone `format` nativamente vía su propia API; no aporta valor adicional para este caso de uso acotado. |

## Consecuencias
- Los agentes usan menos su fallback determinístico cuando Ollama está disponible — el LLM aporta valor real en vez de fallar silenciosamente la mayoría de las veces.
- `QuotationAgent._estimate_with_swarms()` estaba definido pero nunca invocado (código muerto) — al reforzar esta capa se corrigió también ese bug, conectándolo al flujo de paquetes personalizados.
- El mismo mecanismo destapó una promesa sin implementar en `agents/orchestrator/prompts/system_prompt.txt` ("Escalate to human review when confidence < 0.7") — ahora `ConflictValidationOutput.confidence` es un campo real forzado por schema, y `_handle_conflict()` lo usa para decidir escalación (ver `HUMAN_ESCALATION_CONFIDENCE_THRESHOLD` en `agents/orchestrator/agent.py`).
