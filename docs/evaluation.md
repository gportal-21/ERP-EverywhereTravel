# Plan de Evaluación — Everywhere Travel

## 5.1 Conjunto de evaluación (golden set)

`tests/evaluation/golden_set.py` — 12 casos sobre los 4 agentes que invocan LLM
(Sales, Quotation, Itinerary, Orchestrator/Fase 3), cada uno con:
- una salida de LLM representativa (`raw_output`),
- el modelo Pydantic contra el que debe validar,
- si se espera que sea válida o no,
- campos específicos a verificar cuando es válida.

Cubre tres categorías por agente: JSON limpio, JSON válido envuelto en prosa/bloques
```` ```json ````, y salidas inválidas (campos faltantes, tipos incorrectos, texto sin
JSON) — replicando los patrones reales observados en `_parse_*` de cada agente antes de
esta iteración.

## 5.2 Métricas

| Métrica | Fuente | Qué mide |
|---|---|---|
| % casos golden set que pasan | `scripts/run_evaluation.py` | Robustez de la capa de validación estructurada |
| `et_llm_call_duration_seconds` (p50/p95) | Prometheus | Latencia de llamadas LLM por agente |
| `et_llm_tokens_total` | Prometheus | Consumo de tokens por agente/modelo |
| `agent_interaction_logs.success` | PostgreSQL | Tasa de éxito real de interacciones LLM en producción/demo |
| `et_agent_errors_total` | Prometheus | Tasa de error por agente |

## 5.3 LangSmith — decisión: no se usa

Ver [ADR-011](adr/ADR-011-evaluacion-local-sin-langsmith.md). El proyecto no tiene cuenta
de LangSmith y el sistema no usa LangChain/LangGraph en su camino principal (ver
[ADR-001](adr/ADR-001-saga-vs-langgraph.md)), así que el tracing de LangSmith solo
cubriría una fracción del flujo real. En su lugar:

### 5.3.1 Tracing local (sustituto de LangSmith tracing)
Cada llamada LLM se reporta a `agent_interaction_logs` vía
`agents/base_agent.py::report_llm_interaction()` → `POST /api/v1/agent-interactions`,
con input, output, duración y éxito/error — consultable con SQL directo o vía un futuro
endpoint de listado.

### 5.3.2 Datasets y evaluadores (sustituto de LangSmith datasets)
El golden set (`tests/evaluation/golden_set.py`) cumple el rol de dataset versionado;
`parse_structured_output()` + los asserts de `tests/evaluation/test_golden_set.py` cumplen
el rol de evaluador.

### 5.3.3 Comparación de experimentos (sustituto de LangSmith experiments)
No automatizada — comparar corridas del golden set requiere correr
`python scripts/run_evaluation.py --json` en cada punto del tiempo y diffear manualmente
(o versionar el output). Queda como mejora futura si el proyecto escala.

### 5.3.4 Evaluación en línea (online evals)
No implementada — requeriría un evaluador LLM-as-judge corriendo sobre tráfico real, que
implica costo adicional de tokens. Con Ollama local el costo marginal es bajo, así que es
la extensión más natural si se necesita evaluación continua de calidad (no solo de
validez estructural).

## 5.4 Procedimiento

```bash
# Evaluación estructural (determinística, sin Ollama, corre en CI)
python scripts/run_evaluation.py

# Evaluación end-to-end contra el sistema real (requiere Ollama + docker compose up)
python scripts/demo_flow.py --scenario ALL

# Consultar trazas de interacciones LLM reales tras la demo
docker compose exec postgres psql -U etuser -d everywheretravel \
  -c "SELECT agent_id, action, success, duration_ms, tokens_used FROM agent_interaction_logs ORDER BY created_at DESC LIMIT 20;"
```

## 5.5 Reporte de resultados

`scripts/run_evaluation.py` imprime un reporte tabular (PASS/FAIL por caso + agregado por
agente) y admite `--json` para integrarlo en un pipeline de CI o un dashboard externo.
Ejemplo de salida (12/12 casos, ver `.github/workflows/ci.yml` job `backend-tests`):

```
ID                 Agente               Resultado Descripción
------------------------------------------------------------------------------------------
sales-01           sales-agent          PASS   JSON limpio válido
sales-02           sales-agent          PASS   JSON válido envuelto en bloque ```json``` + prosa
...
Total: 12/12 casos pasaron (100.0%)
```
