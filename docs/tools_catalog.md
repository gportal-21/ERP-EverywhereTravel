# Catálogo de Herramientas (Tools) — Everywhere Travel

Todas las tools son funciones Python **síncronas** (restricción de `swarms.Agent`, ver
`agents/swarms_compat.py`), registradas en el `tools=[...]` del agente correspondiente en
`initialize()`. Con el proveedor activo (Ollama), el modelo no las invoca vía
function-calling nativo — su nombre y primera línea de docstring se inyectan como
contexto en el prompt (`_OllamaAgent._tool_context()`) y el LLM razona en texto sobre
cuándo usarlas; el propio código Python interpreta la respuesta después (ver limitación
en [ADR-002](adr/ADR-002-ollama-vs-anthropic.md)). Si `LLM_PROVIDER=anthropic`, estas
mismas funciones sí se exponen como tool-calling estructurado real vía `swarms`/`litellm`.

---

## SalesAgent

### Ficha de herramienta — `_tool_select_package`
| Campo | Valor |
|---|---|
| Archivo | `agents/sales/agent.py` |
| Propósito | Selecciona el mejor paquete de catálogo disponible dado presupuesto y destino |
| Args | `packages_json: str` (JSON de paquetes disponibles), `budget_max: float`, `destination: str` |
| Returns | JSON `{selected, name, price}` o `{selected: null, reason}` |
| I/O externo | Ninguno — cómputo puro sobre el JSON recibido |
| Errores | Excepción capturada internamente → retorna `{selected: null, error}` |

### Ficha de herramienta — `_tool_validate_dates`
| Campo | Valor |
|---|---|
| Archivo | `agents/sales/agent.py` |
| Propósito | Valida que las fechas de viaje sean lógicas y con ≥48h de anticipación |
| Args | `start_date: str` (ISO), `end_date: str` (ISO) |
| Returns | JSON `{valid, duration_days, advance_days, issues[]}` |
| I/O externo | Ninguno |
| Errores | Excepción capturada → `{valid: false, error}` |

### Ficha de herramienta — `_tool_build_customizations`
| Campo | Valor |
|---|---|
| Archivo | `agents/sales/agent.py` |
| Propósito | Construye el dict de personalizaciones a partir de preferencias en texto libre |
| Args | `preferences_list: str` (JSON array), `budget_min: float`, `budget_max: float` |
| Returns | JSON `{hotel_category, includes_flight, includes_transfer, budget_range, raw_preferences}` |
| I/O externo | Ninguno |
| Errores | Excepción capturada → dict parcial con `error` |

### Ficha de herramienta — `_tool_semantic_search_packages`
| Campo | Valor |
|---|---|
| Archivo | `agents/sales/agent.py` |
| Propósito | Búsqueda RAG de paquetes por similaridad semántica (fallback cuando la búsqueda exacta no encuentra resultados) |
| Args | `query: str` (texto libre: destino + preferencias), `top_k: int = 5` |
| Returns | JSON `{packages: [...]}` |
| I/O externo | `GET /api/v1/packages/semantic-search` (HTTP síncrono, timeout 30s) |
| Errores | Timeout/503 (Ollama caído) → `{packages: [], error}` |

---

## QuotationAgent

### Ficha de herramienta — `_tool_calculate_igv`
| Campo | Valor |
|---|---|
| Archivo | `agents/quotation/agent.py` |
| Propósito | Calcula IGV (18%) sobre un monto base |
| Args | `base_amount: float` |
| Returns | JSON `{igv_amount, total_with_igv, rate_used, currency}` |
| I/O externo | Ninguno |
| Errores | No falla — es aritmética pura |

### Ficha de herramienta — `_tool_check_margin_policy`
| Campo | Valor |
|---|---|
| Archivo | `agents/quotation/agent.py` |
| Propósito | Valida si un margen cumple la política mínima (15%) |
| Args | `margin_pct: float` |
| Returns | JSON `{compliant, minimum_required, proposed, recommendation, severity}` |
| I/O externo | Ninguno |
| Errores | No falla |

### Ficha de herramienta — `_tool_estimate_component_price`
| Campo | Valor |
|---|---|
| Archivo | `agents/quotation/agent.py` |
| Propósito | Estima el precio de un componente (vuelo/hotel/traslado/guía/actividades) según destino y duración |
| Args | `component_type: str`, `destination: str`, `traveler_count: int`, `duration_days: int` |
| Returns | JSON `{concept, unit_price, quantity, subtotal, currency}` |
| I/O externo | Ninguno — tabla de precios base hardcodeada en el propio archivo |
| Errores | No falla — usa precio por defecto si `component_type` no está en la tabla |

### Ficha de herramienta — `_tool_detect_budget_anomaly`
| Campo | Valor |
|---|---|
| Archivo | `agents/quotation/agent.py` |
| Propósito | Detecta anomalías de precio: sobre-presupuesto, margen bajo, costo cero |
| Args | `total_cost: float`, `budget_max: float`, `margin_pct: float` |
| Returns | JSON `{anomaly_flags[], has_anomalies, severity}` |
| I/O externo | Ninguno |
| Errores | No falla |

---

## ItineraryAgent

### Ficha de herramienta — `_tool_get_destination_info`
| Campo | Valor |
|---|---|
| Archivo | `agents/itinerary/agent.py` |
| Propósito | Obtiene clima/altitud/cultura/tips de un destino — RAG primero, diccionario estático como fallback |
| Args | `destination: str` |
| Returns | JSON `{destination, source: "rag"\|implícito estático, knowledge[] o climate/altitude/currency/culture/tips}` |
| I/O externo | `GET /api/v1/knowledge/destinations/search` (HTTP síncrono, timeout 15s); si falla, cae al diccionario estático local (sin I/O) |
| Errores | Nunca propaga error — siempre retorna algo, aunque sea el fallback genérico |

### Ficha de herramienta — `_tool_calculate_days`
| Campo | Valor |
|---|---|
| Archivo | `agents/itinerary/agent.py` |
| Propósito | Calcula distribución de días del viaje (llegada/días completos/salida) |
| Args | `start_date: str`, `end_date: str` |
| Returns | JSON `{total_days, arrival_day, departure_day, full_days, suggestion}` |
| I/O externo | Ninguno |
| Errores | Excepción capturada → itinerario por defecto de 5 días |

### Ficha de herramienta — `_tool_get_included_services`
| Campo | Valor |
|---|---|
| Archivo | `agents/itinerary/agent.py` |
| Propósito | Extrae servicios incluidos desde los `line_items` de la cotización |
| Args | `line_items_json: str` (JSON de la cotización) |
| Returns | JSON `{included[], not_included[]}` |
| I/O externo | Ninguno |
| Errores | Excepción capturada → lista genérica de incluidos/no incluidos |

---

## Resumen de idempotencia y efectos secundarios

Todas las tools son **puras o de solo-lectura** (ninguna escribe en PostgreSQL, Redis ni
RabbitMQ directamente) — el único efecto observable es la llamada HTTP de solo-lectura de
`_tool_semantic_search_packages` y `_tool_get_destination_info` hacia los endpoints RAG.
Esto es deliberado: las tools alimentan la *decisión* del LLM, pero la *persistencia* de
esa decisión (guardar la cotización, publicar el evento MCP) siempre la ejecuta el código
determinístico del agente después de recibir la respuesta del LLM — nunca la tool misma.
