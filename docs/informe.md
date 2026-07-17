# Informe Técnico — Sistema Multiagente Everywhere Travel

Documento maestro: mapea cada sección del índice del informe académico al artefacto del
repositorio que la desarrolla. Para armar el documento final (Word/PDF), seguir este
orden e incorporar el contenido de cada archivo referenciado.

## Control de versiones

| Versión | Fecha | Autor | Descripción del cambio |
|---|---|---|---|
| 0.1 | 2026-05-22 | Gerson Portal | Arquitectura inicial: 9 agentes, Saga + RabbitMQ, MCP Envelope, tests, demo E2E; login JWT; ItineraryAgent + generación de PDF |
| 0.2 | 2026-06-29 | Gerson Portal | Mejoras en agentes backend, API y configuración de infraestructura (migración a Ollama local vía swarms_compat) |
| 0.3 | 2026-06-30 | Gerson Portal | Mejoras de UI del dashboard y componentes reutilizables |
| 1.0 | 2026-07-17 | Gerson Portal | Cierre del informe: RAG (pgvector), salida estructurada forzada, HITL con confidence real, observabilidad conectada, seguridad (JWT verificado), golden set + evaluación local, CI, alertas, dashboard Grafana, 12 ADRs, BPMN, catálogos de prompts/tools, ROI |

## Tabla de contenidos — mapeo índice → artefacto

### 1. Resumen ejecutivo
| Sección | Artefacto |
|---|---|
| 1.1 Problema · 1.2 Solución propuesta · 1.3 Resultado esperado | [executive_summary.md](executive_summary.md) |

### 2. Análisis
| Sección | Artefacto |
|---|---|
| 2.1 Justificación: ¿se necesita un LLM? | [analysis.md](analysis.md) §2.1 |
| 2.2 Objetivos y alcance (general, específicos, dentro/fuera) | [analysis.md](analysis.md) §2.2 |
| 2.3 Requisitos funcionales | [analysis.md](analysis.md) §2.3 (RF-01…RF-06) |
| 2.4 Requisitos no funcionales (propios de IA) | [analysis.md](analysis.md) §2.4 (RNF-01…RNF-05) |
| 2.5 Inventario de conocimiento (RAG) y acciones (tools) | [analysis.md](analysis.md) §2.5 + [tools_catalog.md](tools_catalog.md) |
| 2.6 Criterios de éxito y golden set | [analysis.md](analysis.md) §2.6 + `tests/evaluation/golden_set.py` |
| 2.7 Análisis de riesgos | [analysis.md](analysis.md) §2.7 |

### 3. Diseño
| Sección | Artefacto |
|---|---|
| 3.1 Arquitectura general (patrón de orquestación, composición) | [architecture.md](architecture.md) §1 + README "Topología Multiagente" |
| 3.2 Diagrama de proceso (BPMN) | [bpmn/escenario_a_cotizacion.bpmn](bpmn/escenario_a_cotizacion.bpmn) (BPMN 2.0, abrir en bpmn.io/Camunda para exportar imagen) + diagramas de secuencia en architecture.md §2-3 |
| 3.3 Subsistema RAG | [architecture.md](architecture.md) §7bis + [ADR-009](adr/ADR-009-rag-pgvector.md) · código: `core/rag/`, `api/routes/knowledge.py`, `scripts/build_rag_index.py` |
| 3.4 Especificación de herramientas (fichas) | [tools_catalog.md](tools_catalog.md) (11 fichas) |
| 3.5 Orquestación con estado — nota: el sistema NO usa LangGraph; equivalentes: estado compartido = Saga en Redis/Postgres + Pydantic (`MCPEnvelope`); nodos/aristas = agentes + `ROUTING_TABLE`; checkpointing = log de pasos de Saga; HITL = confidence + escalación | [architecture.md](architecture.md) §7 y §7quater + [ADR-001](adr/ADR-001-saga-vs-langgraph.md) |
| 3.6 Deep Agents — cuándo elegirlo y por qué aquí no | [ADR-012](adr/ADR-012-deep-agents-vs-multiagente-especializado.md) · catálogo de agentes: [agent_contracts.md](agent_contracts.md) · límites operativos: [prompts_catalog.md](prompts_catalog.md) |
| 3.7 Esquemas de salida estructurada | [architecture.md](architecture.md) §7ter + [ADR-010](adr/ADR-010-salida-estructurada-forzada.md) · código: `core/structured_output.py` |
| 3.8 Robustez operativa | [architecture.md](architecture.md) §4-5 (circuit breaker, saga) + README "Escenario E: Continuidad Operativa" |
| 3.9 Seguridad y privacidad | [security.md](security.md) |

### 4. Registro de decisiones de arquitectura (ADR)
| Sección | Artefacto |
|---|---|
| ADR-001 … ADR-012 | [adr/README.md](adr/README.md) (índice) + un archivo por ADR |

### 5. Plan de evaluación
| Sección | Artefacto |
|---|---|
| 5.1 Golden set · 5.2 Métricas · 5.3 LangSmith (decisión: sustituido por evaluación local, con equivalentes 5.3.1-5.3.4) · 5.4 Procedimiento · 5.5 Reporte | [evaluation.md](evaluation.md) + [ADR-011](adr/ADR-011-evaluacion-local-sin-langsmith.md) · código: `tests/evaluation/`, `scripts/run_evaluation.py` |

### 6. Catálogo de prompts
| Sección | Artefacto |
|---|---|
| Catálogo + texto completo de los prompts | [prompts_catalog.md](prompts_catalog.md) |

### 7. Medición de éxito y ROI
| Sección | Artefacto |
|---|---|
| 7.1 KPIs · 7.2 Línea base · 7.3 Cálculo de ROI (costos, beneficios, fórmula) · 7.4 Tablero · 7.5 Cadencia | [roi.md](roi.md) |

### 8. Despliegue y operación
| Sección | Artefacto |
|---|---|
| 8.1 Entornos | [deployment.md](deployment.md) "Entornos" |
| 8.2 CI/CD y versionado | `.github/workflows/ci.yml` + [deployment.md](deployment.md) "Estrategias de Release" (versionado) |
| 8.3 Topología de despliegue | `docker-compose.yml` (17 servicios) + [deployment.md](deployment.md) "Arquitectura de puertos" + [architecture.md](architecture.md) §1 |
| 8.4 Configuración y secretos | [deployment.md](deployment.md) "Variables de Entorno" + [security.md](security.md) "Gestión de secretos" |
| 8.5 Estrategias de release | [deployment.md](deployment.md) "Estrategias de Release" |
| 8.6 Monitoreo y alertas | `infrastructure/prometheus/rules/alerts.yml` + `infrastructure/grafana/dashboards/overview.json` + [deployment.md](deployment.md) "Observabilidad" |
| 8.7 Procedimiento ante incidentes | [deployment.md](deployment.md) "Procedimiento ante Incidentes (Runbook)" |
| 8.8 Escalado y FinOps | [deployment.md](deployment.md) "Escalado y FinOps" |
