# ADR-011 — Evaluación local (golden set) en vez de LangSmith

**Estado:** Aceptado

## Contexto
El plan de evaluación necesita un golden set con casos representativos y un procedimiento
repetible para medir la calidad de las salidas del LLM. LangSmith es la herramienta de
referencia para tracing/datasets/evaluadores sobre LangChain/LangGraph, pero requiere una
cuenta externa y el sistema no usa LangChain/LangGraph como framework de orquestación
(ver [ADR-001](ADR-001-saga-vs-langgraph.md)).

## Decisión
- **Golden set local** (`tests/evaluation/golden_set.py`): casos que ejercitan la capa de
  salida estructurada (`core/structured_output.py`) con salidas de LLM representativas
  (válidas, válidas-envueltas-en-prosa, inválidas), ejecutables en CI sin depender de
  Ollama corriendo.
- **Trazas de interacción LLM en PostgreSQL** (`agent_interaction_logs`, poblada vía
  `agents/base_agent.py::report_llm_interaction()` → `POST /api/v1/agent-interactions`):
  cada llamada real a un agente con LLM queda registrada con input, output, duración,
  éxito/error — consultable para una evaluación end-to-end manual con el sistema en vivo.
- **Reporte imprimible** (`scripts/run_evaluation.py`), como sustituto del dashboard de
  LangSmith.

## Alternativas consideradas
| Alternativa | Por qué no |
|---|---|
| LangSmith | Requiere cuenta y `LANGCHAIN_API_KEY` externos que el proyecto no tiene, y su tracing está diseñado para instrumentar llamadas de LangChain/LangGraph — el sistema no pasa por ninguno de los dos en su camino principal, así que el tracing solo cubriría una fracción del flujo real. |

## Consecuencias
- El golden set es determinístico y corre en CI (`.github/workflows/ci.yml`) sin infraestructura externa.
- La evaluación de calidad *end-to-end* contra el LLM real sigue siendo manual (`scripts/demo_flow.py` + consulta a `agent_interaction_logs`) — no hay un dashboard automático de comparación de experimentos como el de LangSmith. Queda documentado como mejora futura si el proyecto migrara a un proveedor de LLM de pago con presupuesto de observabilidad.
