# ADR-002 — Ollama local como proveedor LLM por defecto

**Estado:** Aceptado
**Reemplaza:** documentación previa (README/deployment.md) que afirmaba incorrectamente
que el sistema usaba "Anthropic Claude API (claude-sonnet-4-6)" — el código nunca invocó
el SDK de Anthropic; esta ADR formaliza la decisión real ya presente en `.env.example`.

## Contexto

Los 9 agentes necesitan un LLM para tareas acotadas: clasificar/extraer datos de una
consulta de cliente, estimar componentes de un paquete personalizado, redactar un
itinerario, y evaluar conflictos operativos. El proyecto es una evaluación académica que
corre cientos de sagas de prueba/demo repetidamente durante el desarrollo.

## Decisión

Usar **Ollama local** (`qwen3:8b`) como proveedor LLM por defecto (`LLM_PROVIDER=ollama`),
invocado directamente por HTTP desde `agents/swarms_compat.py::_OllamaAgent` (sin pasar
por `swarms`/`litellm` en este camino).

## Alternativas consideradas

| Alternativa | Por qué no (como default) |
|---|---|
| Anthropic Claude API | Costo por token variable en un proyecto que ejecuta cientos de llamadas de prueba/demo; depende de conectividad y rate limits externos durante la evaluación en vivo. |
| OpenAI / otros proveedores de pago | Mismas razones que Anthropic. |

## Consecuencias

**Positivas:**
- Costo marginal cero por ejecución — se puede correr `scripts/demo_flow.py` y los tests
  de integración tantas veces como haga falta sin factura variable.
- Sin dependencia de conectividad externa ni rate limits durante la demo en vivo.

**Negativas / trade-offs aceptados y mitigados:**
- Un modelo local de 8B es menos confiable que un modelo frontier "razonando en libre
  forma" — mitigado forzando JSON Schema en cada llamada (ver
  [ADR-010](ADR-010-salida-estructurada-forzada.md)) y manteniendo un fallback
  determinístico sin LLM en cada agente (`_fallback_*` en `agents/*/agent.py`).
- El "tool calling" de Ollama vía este wrapper no es function-calling nativo estructurado
  (se inyecta como texto en el prompt, ver `_OllamaAgent._tool_context()`) — una limitación
  conocida del proveedor local, documentada aquí en vez de ocultarla.

## Punto de extensión

`LLM_PROVIDER=anthropic` + `ANTHROPIC_API_KEY` activa el camino real hacia Claude vía
`swarms`/`litellm` (`agents/swarms_compat.py::Agent` delega a `swarms.Agent` cuando el
modelo no es `ollama/*`) — sin cambios de código, solo de configuración, para un despliegue
de producción real donde el costo por token ya no sea la restricción dominante.
