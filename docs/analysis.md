# Análisis — Everywhere Travel Sistema Multiagente

## 2.1 Justificación: ¿se necesita un LLM?

Sí, para un subconjunto acotado de tareas — el resto del sistema es deliberadamente
determinístico. Un LLM aporta valor real donde hay ambigüedad de lenguaje natural o
generación creativa que no se puede resolver con reglas fijas:

| Tarea | ¿Por qué LLM y no reglas? |
|---|---|
| Interpretar una consulta de cliente y armar `PackageRequest` (SalesAgent) | Las preferencias del cliente llegan en texto libre ("hotel 4*", "vuelo incluido") — mapear eso a una estructura requiere comprensión de lenguaje, no solo parsing. |
| Estimar componentes de un paquete personalizado (QuotationAgent) | Sin un paquete de catálogo que fije el precio, componer un desglose razonable (vuelo + hotel + traslados) para un destino arbitrario requiere razonamiento, no una tabla fija. |
| Redactar un itinerario día a día (ItineraryAgent) | Es generación de contenido creativo en español, con contexto cultural — exactamente el tipo de tarea donde un LLM aporta valor que una plantilla no puede. |
| Evaluar un conflicto operativo y decidir escalación (OrchestratorAgent, Fase 3) | Juzgar si un conflicto entre agentes es un problema de integridad de datos, con qué grado de confianza, no es una regla determinista — requiere sopesar contexto. |

Todo lo demás — cálculo de IGV, cronogramas de pago, motor de reglas de compliance
(R001-R012), circuit breaker, deduplicación, generación de PDF — es **intencionalmente
determinístico** (ver `docs/prompts_catalog.md`, sección "Prompts cargados pero no
usados"). Usar un LLM para compliance regulatorio o aritmética financiera introduciría
no-determinismo donde la rúbrica de negocio exige exactitud auditable.

## 2.2 Objetivos y alcance

**Objetivo general:** automatizar el ciclo de vida completo de una venta de paquete
turístico (consulta → cotización → validación → reserva → liquidación → documentos →
itinerario) mediante agentes especializados que colaboran vía un contrato de mensajería
explícito (MCP), sin que ningún agente concentre toda la lógica de negocio.

**Objetivos específicos:**
1. Eliminar la doble reserva y los errores de cálculo manual (Excel) mediante agentes deterministas para dinero y disponibilidad.
2. Reducir el tiempo de cotización de horas a segundos mediante LLM acotado + catálogo.
3. Dar trazabilidad completa de cada transacción distribuida (patrón Saga + audit log inmutable).
4. Sostener continuidad operativa ante fallos parciales (circuit breaker, dead-letter, escalación humana).

**Dentro del alcance:** cotización, validación, reserva, liquidación, documentos, itinerarios, RAG sobre catálogo/destinos, observabilidad (métricas + logs estructurados + golden set local).

**Fuera del alcance:** pagos reales (pasarela de pago), integración con GDS/aerolíneas reales, multi-tenant (multi-agencia), app móvil nativa, LangSmith/tracing en la nube (ver [ADR-011](adr/ADR-011-evaluacion-local-sin-langsmith.md)).

## 2.3 Requisitos funcionales

- RF-01: El sistema debe generar una cotización a partir de una consulta de cliente en < 30s (catálogo) o con estimación LLM (personalizado).
- RF-02: Toda cotización debe pasar por `ValidationAgent` antes de poder confirmarse.
- RF-03: Una reserva debe fallar de forma segura (sin doble-booking) ante solicitudes concurrentes sobre el mismo paquete/fecha.
- RF-04: Toda liquidación completa debe disparar generación automática de factura y comprobante.
- RF-05: El sistema debe poder generar un itinerario descargable en PDF por cotización validada.
- RF-06: Un conflicto entre agentes debe resolverse automáticamente o escalarse a un humano según el nivel de confianza de la evaluación (ver `HUMAN_ESCALATION_CONFIDENCE_THRESHOLD`).

## 2.4 Requisitos no funcionales (propios de IA)

- RNF-01 (Confiabilidad de salida): toda respuesta del LLM debe validar contra un JSON Schema forzado (constrained decoding) antes de usarse; si falla, el agente cae a un fallback determinístico — nunca debe propagarse una salida no válida al resto del sistema (ver [ADR-010](adr/ADR-010-salida-estructurada-forzada.md)).
- RNF-02 (Costo): el proveedor LLM por defecto debe tener costo marginal cero por ejecución (Ollama local, ver [ADR-002](adr/ADR-002-ollama-vs-anthropic.md)).
- RNF-03 (Latencia): p95 de llamadas LLM reportado en `et_llm_call_duration_seconds` (Prometheus), con alerta si supera 20s (`infrastructure/prometheus/rules/alerts.yml`).
- RNF-04 (Trazabilidad): toda llamada LLM debe quedar registrada en `agent_interaction_logs` (input, output, duración, éxito) para poder auditar y evaluar calidad después.
- RNF-05 (Degradación con gracia): si el LLM no está disponible, el flujo de negocio debe completarse igual con lógica determinística — nunca debe bloquear una venta.

## 2.5 Inventario de conocimiento y acciones

**Fuentes de conocimiento (para RAG):**
| Fuente | Contenido | Tabla |
|---|---|---|
| Catálogo de paquetes | Nombre, destino, precio, duración, incluye/excluye | `packages` (embedding vector(768)) |
| Guías de destino curadas | Clima, altitud, cultura, tips prácticos por destino (`core/rag/content.py`) | `destination_knowledge` |

**Acciones externas (tools):**
| Tool | Agente | Efecto |
|---|---|---|
| `_tool_select_package` / `_tool_validate_dates` / `_tool_build_customizations` | Sales | Puro cómputo local, sin I/O externo |
| `_tool_semantic_search_packages` | Sales | Llama a `GET /packages/semantic-search` (RAG) |
| `_tool_calculate_igv` / `_tool_check_margin_policy` / `_tool_estimate_component_price` / `_tool_detect_budget_anomaly` | Quotation | Puro cómputo local |
| `_tool_get_destination_info` (vía `_rag_destination_info`) | Itinerary | Llama a `GET /knowledge/destinations/search` (RAG), con fallback estático |
| `_tool_calculate_days` / `_tool_get_included_services` | Itinerary | Puro cómputo local |

Ficha completa de cada tool (Args, Returns, I/O externo, manejo de errores) en
[docs/tools_catalog.md](tools_catalog.md).

## 2.6 Criterios de éxito y conjunto de evaluación (golden set)

Ver `tests/evaluation/golden_set.py` — 12 casos que verifican que la capa de salida
estructurada (a) acepta JSON válido (limpio o envuelto en prosa/bloques de código) y
(b) rechaza salidas incompletas o mal tipadas, forzando el fallback determinístico.
Criterio de éxito: 100% de los casos deben pasar en cada PR (ver `.github/workflows/ci.yml`).
Procedimiento y reporte completos en `docs/evaluation.md`.

## 2.7 Análisis de riesgos

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| El LLM local (8B) alucina o produce JSON inválido | Media | Medio | Salida forzada por schema + fallback determinístico en cada agente (ver [ADR-010](adr/ADR-010-salida-estructurada-forzada.md)) |
| Doble reserva por condición de carrera | Baja (mitigado) | Alto | Optimistic locking Redis SETNX ([ADR-004](adr/ADR-004-optimistic-locking-redis.md)) |
| Un agente cae y bloquea la Saga completa | Media | Alto | Dead-letter queue + reintentos exponenciales + escalación humana tras 3 fallos |
| Ollama no disponible (host sin GPU/memoria) | Media | Bajo | Cada agente LLM tiene fallback determinístico; el sistema sigue vendiendo sin LLM |
| Routers de la API sin autenticación real | Alta antes de esta iteración, mitigada parcialmente | Alto | `get_current_user` ahora verifica JWT en `clients`, `itinerary`, `stats`; routers con tráfico de agentes quedan pendientes de una estrategia de auth servicio-a-servicio (ver nota en `api/main.py`) |
| JWT accesible desde JS (XSS) en el frontend actual | Media | Medio | Cookie httpOnly añadida como defensa adicional en el login; migración completa del frontend a cookie-only queda como trabajo de seguimiento |
| pgvector con catálogo pequeño no refleja rendimiento a escala | Baja | Bajo | Aceptado — el volumen actual (decenas de paquetes) no justifica un índice ANN afinado; documentado en [ADR-009](adr/ADR-009-rag-pgvector.md) |
