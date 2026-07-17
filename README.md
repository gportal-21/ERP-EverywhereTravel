# Everywhere Travel — Sistema Multiagente Interno

> **Proyecto académico — UPAO | 7mo Ciclo | Automatización Inteligente de Procesos**
> Implementación de sistema multiagente real con Claude Code, Swarms, MCP, Redis, RabbitMQ y FastAPI.

---

## Índice

1. [Descripción del Sistema](#descripción-del-sistema)
2. [Arquitectura General](#arquitectura-general)
3. [Topología Multiagente](#topología-multiagente)
4. [Agentes Especializados](#agentes-especializados)
5. [Stack Tecnológico](#stack-tecnológico)
6. [Requisitos Previos](#requisitos-previos)
7. [Instalación y Despliegue](#instalación-y-despliegue)
8. [Flujos de Negocio](#flujos-de-negocio)
9. [API Reference](#api-reference)
10. [Métricas de Rendimiento](#métricas-de-rendimiento)
11. [Casos de Prueba](#casos-de-prueba)
12. [Pruebas Adversariales](#pruebas-adversariales)
13. [Observabilidad](#observabilidad)
14. [Estructura del Proyecto](#estructura-del-proyecto)

**Documentación extendida:** [Informe maestro (mapa del índice completo)](docs/informe.md) ·
[Resumen ejecutivo](docs/executive_summary.md) ·
[Análisis (objetivos/requisitos/riesgos)](docs/analysis.md) ·
[Arquitectura](docs/architecture.md) · [BPMN](docs/bpmn/escenario_a_cotizacion.bpmn) ·
[Catálogo de herramientas](docs/tools_catalog.md) ·
[Catálogo de prompts](docs/prompts_catalog.md) · [Seguridad y privacidad](docs/security.md) ·
[Plan de evaluación](docs/evaluation.md) · [ROI](docs/roi.md) · [ADRs](docs/adr/README.md)

---

## Descripción del Sistema

Everywhere Travel es una agencia de viajes con múltiples sedes. Este sistema reemplaza hojas de cálculo compartidas con una **plataforma interna centralizada** que automatiza:

| Proceso | Antes | Ahora |
|---|---|---|
| Cotización de paquetes | Manual, 2-4 horas | Automático, < 30 segundos |
| Reservas simultáneas | Cola manual, errores de doble reserva | Atómica con optimistic locking |
| Liquidaciones financieras | Excel con fórmulas frágiles | Ledger inmutable con audit trail |
| Emisión de documentos | Manual en Word | Generación async PDF en cola |
| Coordinación entre sedes | Email + teléfono | Event bus centralizado |

**Sistema NO público** — uso interno exclusivo de agentes de ventas, finanzas y administración.

---

## Arquitectura General

```
┌─────────────────────────────────────────────────────────────────────┐
│                     CAPA DE PRESENTACIÓN                            │
│  Next.js Dashboard (puerto 3000)  ←→  WebSocket Redis pub/sub       │
└─────────────────────────┬───────────────────────────────────────────┘
                          │ HTTP/WS
┌─────────────────────────▼───────────────────────────────────────────┐
│                     API GATEWAY (FastAPI :8000)                     │
│  REST /api/v1/*  ·  WebSocket /ws/{channel}  ·  Métricas /metrics  │
└────────┬────────────────────────────────────────┬───────────────────┘
         │ MCP Envelope                           │ SQLAlchemy async
         ▼                                        ▼
┌────────────────────┐                  ┌──────────────────────┐
│   ORCHESTRATION    │                  │   PostgreSQL :5432   │
│                    │◄────────────────►│   (persistent store) │
│  OrchestratorAgent │                  └──────────────────────┘
│  MonitoringAgent   │
└────────┬───────────┘
         │ RabbitMQ topic exchange
         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     AGENT LAYER                                     │
│                                                                     │
│  SalesAgent  →  QuotationAgent  →  ValidationAgent                 │
│                                                                     │
│  ReservationAgent  →  FinanceAgent  →  DocumentAgent (×3 workers)  │
│                                                                     │
│  NotificationAgent                                                  │
└─────────────────────────────────────────────────────────────────────┘
         │ Read/Write
         ▼
┌────────────────────────────────────────────────────────────────────┐
│                     SHARED STATE LAYER                             │
│                                                                    │
│  Redis :6379                                                       │
│  ├── saga:{id}           Working memory (TTL 1h)                  │
│  ├── lock:{type}:{id}    Optimistic locking (TTL 30s)             │
│  ├── processed:{msg_id}  Deduplication (TTL 24h)                  │
│  ├── heartbeat:{agent}   Health check (TTL 90s)                   │
│  └── circuit:{service}   Circuit breaker state                    │
│                                                                    │
│  RabbitMQ :5672 (topic exchange + dead-letter)                    │
│  MinIO :9000 (document storage S3-compatible)                     │
└────────────────────────────────────────────────────────────────────┘
```

---

## Topología Multiagente

**Decisión:** Topología **Híbrida Jerárquica-Estrella**

```
                    ┌─────────────────────────────────┐
                    │       ORCHESTRATOR AGENT         │
                    │  (Enrutamiento · Sagas · Conflicts│
                    └──────────────┬──────────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                    │
     ┌────────▼────────┐  ┌────────▼────────┐  ┌───────▼────────┐
     │  DOMINIO VENTAS │  │ DOMINIO FINANZAS│  │  DOMINIO DOCS  │
     └────────┬────────┘  └────────┬────────┘  └───────┬────────┘
      Sales · Quotation    Finance · Validation   Document · Notif
      · Validation                                · Monitoring
```

**Justificación técnica:**
- `Jerárquica` → el Orchestrator centraliza la política y mantiene trazabilidad de Sagas
- `Estrella interna por dominio` → Sales puede coordinar Quotation sin pasar por Orchestrator
- Evita la `malla` (acoplamiento excesivo) y la `estrella pura` (cuello de botella único)

---

## Agentes Especializados

### 1. OrchestratorAgent
| Campo | Valor |
|---|---|
| **Cola** | `orchestrator-commands` |
| **Routing** | Recibe TODO, delega por `payload_type` |
| **Herramientas** | SagaCoordinator, CircuitBreaker, ConflictResolver, Claude API |
| **Exclusivo** | Saga coordination, conflict arbitration, SLA monitoring |

### 2. SalesAgent
| Campo | Valor |
|---|---|
| **Cola** | `sales-events` |
| **Input** | `PackageInquiry` |
| **Output** | `PackageRequest` → Quotation Agent |
| **Herramientas** | catalog.search, customer.memory, Claude API |
| **Exclusivo** | Interfaz comercial, memoria de cliente, selección de catálogo |

### 3. QuotationAgent
| Campo | Valor |
|---|---|
| **Cola** | `quotation-events` |
| **Input** | `PackageRequest` |
| **Output** | `QuotationResult` (versionado, inmutable) |
| **Herramientas** | pricing.calculate (Decimal), anomaly.detect, Claude API |
| **Exclusivo** | Cálculo de precios, versionado de cotizaciones, anomaly flags |

### 4. ReservationAgent
| Campo | Valor |
|---|---|
| **Cola** | `reservation-events` |
| **Input** | `QuotationResult` (status=VALIDATED) |
| **Output** | `ReservationRecord` + lock atómico |
| **Herramientas** | Redis SETNX, availability.check, code.generate |
| **Exclusivo** | Disponibilidad atómica, reservation_code único, notificación proveedores |

### 5. FinanceAgent
| Campo | Valor |
|---|---|
| **Cola** | `finance-events` |
| **Input** | `ReservationRecord`, `PaymentEvent` |
| **Output** | `LiquidationRecord`, cronograma de pagos |
| **Herramientas** | ledger.record, schedule.generate, commission.calculate |
| **Exclusivo** | Contabilidad, comisiones (8%), cronogramas, detección de mora |

### 6. DocumentAgent
| Campo | Valor |
|---|---|
| **Cola** | `document-jobs` (prioridad, durable) |
| **Workers** | 3 concurrentes |
| **Output** | PDF en MinIO, URL firmada 7 días |
| **Herramientas** | Jinja2, WeasyPrint, MinIO S3, retry exponencial |
| **Exclusivo** | Generación async de PDFs, gestión de cola de trabajos |

### 7. ValidationAgent
| Campo | Valor |
|---|---|
| **Disparo** | Antes de cualquier finalización de cotización o reserva |
| **Rules** | R001-R012 con severidades INFO/WARNING/ERROR/BLOCKING |
| **Output** | `ValidationResult` + audit log inmutable |
| **Exclusivo** | Motor de reglas, compliance IGV (18%), auditoría inmutable |

### 8. MonitoringAgent
| Campo | Valor |
|---|---|
| **Loops** | Heartbeat (30s), Stale Sagas (60s), Dead-Letter (120s) |
| **Output** | Alertas, circuit breaker transitions, escalación a humano |
| **Exclusivo** | Circuit breaker, dead-letter requeue, saga compensation |

### 9. NotificationAgent
| Campo | Valor |
|---|---|
| **Cola** | `notification-events` |
| **Canales** | Redis pub/sub → WebSocket dashboard, email |
| **Dedup** | 60s por evento+referencia |
| **Exclusivo** | Entrega y deduplicación de notificaciones |

---

## Stack Tecnológico

```
Backend:        Python 3.12 + FastAPI 0.115 + SQLAlchemy 2 (async)
Frontend:       Next.js 15 + React 18 + TailwindCSS
Multiagente:    Ollama local (qwen3:8b) vía swarms.Agent — ver nota de proveedor LLM abajo
RAG:            PostgreSQL + pgvector, embeddings Ollama (nomic-embed-text)
MCP:            JSON Schema Draft-07 + Pydantic v2
Persistencia:   PostgreSQL 16 (ACID, JSONB para payloads MCP, pgvector para RAG)
Estado caliente:Redis 7 (TTL, SETNX, pub/sub)
Event Bus:      RabbitMQ 3.13 (topic exchange, dead-letter, priority queues)
Documentos:     Jinja2 + WeasyPrint → PDF → MinIO (S3-compatible)
Observabilidad: Prometheus + Grafana + structured logging (structlog) + agent_interaction_logs (trazas LLM locales)
Contenedores:   Docker + Docker Compose
Tests:          pytest + pytest-asyncio + httpx
```

### Nota sobre el proveedor LLM

El sistema corre **100% sobre Ollama local** (`LLM_MODEL=ollama/qwen3:8b`, ver `.env.example`) a través de
`agents/swarms_compat.py`, que expone una implementación mínima de `Agent` cuando detecta un modelo `ollama/*`
y llama directo al endpoint HTTP `/api/generate` de Ollama, sin pasar por `swarms`/`litellm`.

**Por qué Ollama y no un proveedor de pago (Anthropic/OpenAI):**
- Costo cero por token — crítico para poder correr cientos de sagas de prueba/demo sin factura variable.
- Latencia predecible en local, sin depender de rate limits externos durante la evaluación.
- El volumen y la complejidad de las tareas de este dominio (clasificar, extraer, resumir JSON acotado)
  no requieren un modelo frontier; un modelo de 8B es suficiente con schemas y validación estrictos.

Esto es una decisión consciente, no una limitación oculta: la salida de cada agente se fuerza a JSON Schema
(ver `core/mcp/validator.py` y la sección [Salidas Estructuradas](#salidas-estructuradas)) precisamente para
compensar que un modelo local de 8B es menos confiable "razonando en libre forma" que un modelo frontier.
El SDK `anthropic` queda declarado en `requirements.txt` como *punto de extensión* para producción real
(cambiar `LLM_PROVIDER=anthropic` + `ANTHROPIC_API_KEY`), pero no se invoca en el código por defecto.

---

## Requisitos Previos

```bash
# Software requerido
Docker >= 24.0
Docker Compose >= 2.20
Git
Ollama (host) con los modelos:
  ollama pull qwen3:8b
  ollama pull nomic-embed-text   # embeddings para RAG

# Variables de entorno obligatorias (ver .env.example)
LLM_PROVIDER=ollama
LLM_MODEL=ollama/qwen3:8b
OLLAMA_BASE_URL=http://localhost:11434
```

---

## Instalación y Despliegue

### Paso 1 — Clonar y configurar entorno

```bash
git clone <repositorio>
cd sistema-everywheretravel
cp .env.example .env
```

Editar `.env` y agregar tu `ANTHROPIC_API_KEY`.

### Paso 2 — Levantar toda la infraestructura

```bash
docker compose up --build -d
```

Servicios que inician:

| Servicio | Puerto | URL |
|---|---|---|
| PostgreSQL | 5432 | — |
| Redis | 6379 | — |
| RabbitMQ | 5672 / 15672 | http://localhost:15672 (etrabbit/etrabbitpass) |
| MinIO | 9000 / 9001 | http://localhost:9001 (etminio/etminiopass) |
| API Gateway | 8000 | http://localhost:8000/docs |
| Dashboard | 3000 | http://localhost:3000 |
| Grafana | 3001 | http://localhost:3001 (admin/etgrafana) |
| Prometheus | 9090 | http://localhost:9090 |

### Paso 3 — Verificar que todos los agentes están activos

```bash
# Verificar heartbeats de los 9 agentes
curl http://localhost:8000/api/v1/monitoring/health
```

Respuesta esperada:
```json
{
  "system": "everywheretravel",
  "agents": {
    "orchestrator-agent": "HEALTHY",
    "sales-agent": "HEALTHY",
    "quotation-agent": "HEALTHY",
    "reservation-agent": "HEALTHY",
    "finance-agent": "HEALTHY",
    "document-agent": "HEALTHY",
    "validation-agent": "HEALTHY",
    "monitoring-agent": "HEALTHY",
    "notification-agent": "HEALTHY"
  },
  "healthy_count": 9,
  "total_agents": 9
}
```

### Paso 4 — Ejecutar demo end-to-end

```bash
# Desde el host (requiere Python 3.12 + httpx)
pip install httpx
python scripts/demo_flow.py
```

### Paso 5 — Ejecutar tests

```bash
# Tests unitarios (no requieren servicios)
pytest tests/unit/ -v

# Tests adversariales (no requieren servicios)
pytest tests/adversarial/ -v

# Tests de integración (requieren docker compose up)
pytest tests/integration/ -v -m integration
```

---

## Flujos de Negocio

### Escenario A: Paquete Personalizado

```
POST /api/v1/inquiries
{
  "client_id": "uuid",
  "destination": "Cusco",
  "start_date": "2026-08-01",
  "end_date": "2026-08-06",
  "budget_min": 1500,
  "budget_max": 3000,
  "traveler_count": 2,
  "preferences": ["hotel 4*", "vuelo incluido"]
}

→ Saga iniciada
→ Sales Agent: busca catálogo, construye PackageRequest
→ Quotation Agent: calcula precio (Decimal), genera QuotationResult v1
→ Validation Agent: valida R001-R012, marca VALIDATED
→ Sales Agent: notifica resultado vía WebSocket
← { saga_id, quote_id, total_cost, status: "VALIDATED" }
```

### Escenario B: Cotizaciones Simultáneas

```
3 clientes diferentes consultan simultáneamente
→ 3 sagas independientes creadas
→ 3 PackageRequests paralelos a Quotation Agent
→ Quotation Agent: genera quote_id único por cliente
→ Sin colisión: Redis deduplication + optimistic locking
→ 3 QuotationResults independientes, sin interferencia
```

### Escenario C: Reserva + Liquidación + Documentos

```
POST /api/v1/reservations (con QuotationResult VALIDATED)

→ Reservation Agent:
   ├── SETNX lock atómico en Redis
   ├── Crea ReservationRecord (ET-20260801-XXXXX)
   └── Publica ReservationCreated

→ Finance Agent:
   ├── Genera cronograma de pagos (según monto)
   ├── Crea LiquidationRecord (status=PARTIAL)
   └── Solicita INVOICE al Document Agent

→ Document Agent (async):
   ├── Worker 1: genera PDF factura
   ├── Sube a MinIO → URL firmada
   └── Publica DocumentReady → Notification Agent

→ Notification Agent:
   └── WebSocket push al dashboard del agente de ventas
```

### Escenario D: Generación Asincrónica de Documentos

```
EventBus: DocumentJob{type=LIQUIDATION, priority=HIGH}

→ Cola document-jobs (RabbitMQ, durable=True, priority=10)
→ Document Agent Worker (uno de 3):
   ├── Dequeue job (prefetch=1)
   ├── Validar campos requeridos
   ├── Render Jinja2 template
   ├── WeasyPrint → PDF bytes
   ├── MinIO upload → presigned URL (7 días)
   └── Retry exponencial si falla: 1s → 2s → 4s
→ PATCH /api/v1/document-jobs/{id} status=COMPLETE
→ DocumentReady event → Notification Agent → WebSocket
```

### Escenario E: Continuidad Operativa

```
Finance Agent pierde conectividad:

[Monitoring Agent — loop heartbeat 30s]
├── Heartbeat ausente #1 → WARNING
├── Heartbeat ausente #2 → DEGRADED
│   ├── CircuitBreaker: CLOSED → OPEN
│   ├── Redis alert → WebSocket admin
│   └── Sagas de Finance: pausadas

[Después de 30s cooldown]
├── CircuitBreaker: OPEN → HALF_OPEN
├── Test request enviado a Finance Agent
│   ├── SUCCESS → CLOSED, sagas retomadas
│   └── FAIL → OPEN nuevamente, escalación a humano

[Dead-letter recovery]
├── Mensajes fallidos en dead-letter-queue
├── Monitoring Agent: requeue con backoff (1s,2s,4s)
└── Después de 3 fallos → REQUIRES_MANUAL_INTERVENTION
```

---

## API Reference

### Autenticación

```bash
POST /api/v1/auth/token
Content-Type: application/x-www-form-urlencoded
username=admin&password=admin1234

# Response
{ "access_token": "eyJ...", "token_type": "bearer", "role": "admin" }
```

### Endpoints principales

| Método | Endpoint | Descripción |
|---|---|---|
| `POST` | `/api/v1/inquiries` | Inicia flujo multiagente de cotización |
| `GET` | `/api/v1/packages/search` | Busca paquetes turísticos |
| `GET` | `/api/v1/quotations/{quote_id}` | Consulta cotización por ID |
| `POST` | `/api/v1/reservations` | Crea reserva (lock atómico) |
| `GET` | `/api/v1/reservations/{code}` | Consulta reserva |
| `POST` | `/api/v1/liquidations/{code}/transactions` | Registra pago |
| `GET` | `/api/v1/sagas` | Lista sagas (filtrable por status) |
| `GET` | `/api/v1/sagas/{saga_id}` | Detalle de saga |
| `GET` | `/api/v1/monitoring/health` | Health check de todos los agentes |
| `GET` | `/api/v1/monitoring/circuit-breakers` | Estado de circuit breakers |
| `GET` | `/metrics` | Métricas Prometheus |

### WebSocket

```javascript
// Notificaciones en tiempo real para un cliente
const ws = new WebSocket('ws://localhost:8000/ws/client:{client_id}')

// Alertas del sistema (admin)
const ws = new WebSocket('ws://localhost:8000/ws/system:alerts')

ws.onmessage = (e) => {
  const { type, message, data, saga_id } = JSON.parse(e.data)
}
```

---

## Métricas de Rendimiento

### Latencias objetivo por operación

| Operación | P50 | P95 | P99 |
|---|---|---|---|
| Cotización simple (paquete predefinido) | < 2s | < 5s | < 8s |
| Cotización personalizada (LLM) | < 5s | < 12s | < 20s |
| Creación de reserva | < 500ms | < 1.5s | < 3s |
| Generación PDF (Document Agent) | < 3s | < 8s | < 15s |
| Health check | < 100ms | < 200ms | < 500ms |

### Throughput por agente

| Agente | Mensajes/min (nominal) | Con 3× carga |
|---|---|---|
| Orchestrator | 120 | 60 (circuit breaker) |
| Sales | 60 | 40 |
| Quotation | 40 | 25 |
| Reservation | 80 | 80 (stateless lock) |
| Finance | 50 | 40 |
| Document | 30 (×3 workers = 90) | 75 |
| Validation | 100 | 80 |

### Token usage promedio por saga completa

| Agente | Tokens/saga | Modelo |
|---|---|---|
| OrchestratorAgent (conflict) | ~300 | claude-sonnet-4-6 |
| SalesAgent | ~400 | claude-sonnet-4-6 |
| QuotationAgent (custom) | ~500 | claude-sonnet-4-6 |
| Total saga completa | ~1,200 | — |

### Tasa de éxito esperada (sistema sano)

| Métrica | Valor |
|---|---|
| Cotizaciones exitosas | > 98% |
| Reservas sin conflicto | > 99.5% |
| Documentos generados sin retry | > 95% |
| Mensajes deduplicados correctamente | 100% |
| Circuit breaker false positives | < 0.1% |

---

## Casos de Prueba

### Tests unitarios (`tests/unit/`)

#### `test_mcp_envelope.py`

| Test | Descripción | Resultado esperado |
|---|---|---|
| `test_valid_envelope_creation` | Envelope con agentes válidos | Creación exitosa, UUIDs generados |
| `test_invalid_sender_agent_raises` | Agente emisor no registrado | `ValueError` |
| `test_invalid_receiver_agent_raises` | Agente receptor no registrado | `ValueError` |
| `test_envelope_not_expired` | Mensaje reciente | `is_expired() = False` |
| `test_envelope_expired` | Timestamp hace 400s, TTL=300s | `is_expired() = True` |
| `test_make_reply` | Reply invierte sender/receiver | Correlación preservada |
| `test_json_serialization` | Round-trip JSON | `message_id` idéntico |
| `test_package_inquiry_valid` | Datos válidos | Modelo creado |
| `test_package_inquiry_max_travelers` | 51 viajeros | Validación Pydantic falla |

#### `test_circuit_breaker.py`

| Test | Descripción | Resultado esperado |
|---|---|---|
| `test_closed_state_allows_calls` | Circuito CLOSED, función OK | Retorna resultado |
| `test_open_after_threshold_failures` | 5 fallos consecutivos | Estado → OPEN |
| `test_open_circuit_raises_without_calling` | Circuito OPEN | `CircuitBreakerOpenError`, función no llamada |
| `test_success_resets_circuit` | HALF_OPEN + éxito | Estado → CLOSED |

### Tests de integración (`tests/integration/`)

| Test | Escenario | Verificación |
|---|---|---|
| `test_submit_inquiry_creates_saga` | Escenario A | `saga_id` en respuesta, `status=processing` |
| `test_concurrent_quotations_independent` | Escenario B | 3 `saga_id` únicos, sin colisión |
| `test_package_search_returns_results` | Catálogo | Lista de paquetes no vacía |
| `test_duplicate_reservation_code_rejected` | Conflicto | Segunda reserva rechazada |
| `test_payment_schedule_low_amount` | ≤ 1000 PEN | 1 cuota, 100% |
| `test_payment_schedule_high_amount` | > 5000 PEN | 3 cuotas: 30/40/30% |

---

## Pruebas Adversariales

### `tests/adversarial/test_adversarial.py`

| Test | Ataque/Edge Case | Comportamiento esperado |
|---|---|---|
| `test_empty_payload_accepted` | Payload `{}` | Aceptado por envelope, rechazado por schema |
| `test_very_large_payload` | 100K chars en payload | Serialización exitosa, sin OOM |
| `test_retry_count_exceeds_max` | `retry_count=11` | Pydantic `ValidationError` |
| `test_sql_injection_in_payload` | `'; DROP TABLE clients; --` | Almacenado como JSON string, no ejecutado |
| `test_negative_budget_envelope` | `budget_min=-1000` | Schema JSON rechaza |
| `test_zero_margin_detection` | Margen = 0% | Flag `ERROR` en ValidationAgent |
| `test_zero_cost_detection` | `total_cost=0` | Flag `ZERO_COST_ERROR` |
| `test_over_budget_detection` | Costo 120% presupuesto | Flag `OVER_BUDGET` |
| `test_reservation_code_format_invalid` | Formatos incorrectos | Regex no matchea |
| `test_reservation_code_format_valid` | `ET-20260801-AB123` | Regex matchea |
| `test_deduplication_blocks_same_message_twice` | Mismo `message_id` × 2 | Primero `True`, segundo `False` |
| `test_total_amounts_sum_correctly` | 12,500 PEN → 3 cuotas | Suma = total ± 1.00 |
| `test_exactly_1000_pen` | Exactamente 1000 PEN | 1 cuota (límite inclusivo) |
| `test_exactly_5000_pen` | Exactamente 5000 PEN | 2 cuotas (límite inclusivo) |

---

## Observabilidad

### Prometheus — Métricas expuestas en `/metrics`

```
# Latencia por endpoint
http_request_duration_seconds{method, handler, status}

# Mensajes procesados por agente
et_agent_messages_total{agent_id, payload_type}

# Errores por agente
et_agent_errors_total{agent_id, error_type}

# Circuit breaker state
et_circuit_breaker_state{service}  # 0=CLOSED, 1=HALF_OPEN, 2=OPEN

# Token usage LLM
et_llm_tokens_total{agent_id, model}

# Sagas activas
et_sagas_active_total

# Dead-letter queue size
et_dead_letter_queue_size
```

### Grafana — Dashboard principal

Acceso: `http://localhost:3001` (admin / etgrafana)

Paneles incluidos:
- Latencia p50/p95/p99 por endpoint
- Throughput de mensajes por agente
- Estado de circuit breakers (semáforo)
- Sagas activas vs completadas vs fallidas
- Token usage acumulado por agente
- Dead-letter queue size

### Logs estructurados (structlog)

```json
{
  "timestamp": "2026-05-22T10:30:00Z",
  "level": "INFO",
  "agent": "quotation-agent",
  "saga_id": "abc-123",
  "message_id": "xyz-456",
  "event": "quotation_calculated",
  "quote_id": "q-789",
  "total_cost": 2340.50,
  "anomaly_flags": []
}
```

---

## Estructura del Proyecto

```
sistema-everywheretravel/
│
├── agents/                          # 9 agentes especializados
│   ├── base_agent.py                # Clase abstracta base
│   ├── orchestrator/agent.py        # Enrutamiento + Sagas + Conflictos
│   ├── sales/agent.py               # Ciclo comercial + memoria de cliente
│   ├── quotation/agent.py           # Cálculo de precios + versionado
│   ├── reservation/agent.py         # Disponibilidad atómica + lock
│   ├── finance/agent.py             # Liquidaciones + comisiones
│   ├── document/agent.py            # PDFs async + cola + MinIO
│   ├── validation/agent.py          # Motor de reglas + audit inmutable
│   ├── monitoring/agent.py          # Circuit breaker + dead-letter + heartbeats
│   └── notification/agent.py       # WebSocket + email
│
├── core/                            # Infraestructura core del sistema
│   ├── mcp/
│   │   ├── envelope.py              # MCPEnvelope + payloads tipados
│   │   └── validator.py             # JSON Schema Draft-07 validator
│   ├── event_bus/
│   │   ├── publisher.py             # RabbitMQ publisher
│   │   └── consumer.py              # Consumer + deduplication + retry
│   ├── shared_state/
│   │   └── redis_store.py           # Estado compartido + locks + heartbeats
│   ├── circuit_breaker.py           # Circuit breaker distribuido
│   ├── saga_coordinator.py          # Saga pattern distribuido
│   └── metrics.py                   # Recolección de métricas
│
├── api/                             # FastAPI Gateway
│   ├── main.py                      # App principal + lifespan + WebSocket
│   ├── config.py                    # Settings desde env vars
│   ├── database.py                  # SQLAlchemy async engine
│   ├── models.py                    # ORM models (11 tablas)
│   └── routes/                      # 9 routers REST
│
├── schemas/                         # JSON Schema Draft-07
│   ├── package_inquiry.json
│   ├── package_request.json
│   ├── quotation_result.json
│   ├── reservation_record.json
│   ├── liquidation_record.json
│   ├── document_job.json
│   └── agent_heartbeat.json
│
├── infrastructure/
│   ├── postgres/init.sql            # Schema + datos iniciales
│   ├── rabbitmq/definitions.json    # Exchanges + queues + bindings
│   └── prometheus/prometheus.yml    # Scrape config
│
├── frontend/                        # Next.js 15 Dashboard
│   └── app/(dashboard)/            # Dashboard interno con WebSocket
│
├── tests/
│   ├── unit/                        # Sin dependencias externas
│   ├── integration/                 # Requieren docker compose
│   ├── adversarial/                 # Edge cases + seguridad
│   └── evaluation/                  # Golden set (evaluación local de LLM)
│
├── scripts/
│   ├── demo_flow.py                 # Demo end-to-end reproducible
│   ├── build_rag_index.py           # (Re)indexa embeddings RAG
│   └── run_evaluation.py            # Corre el golden set + reporte
│
├── core/rag/                        # Embedder + fuentes de conocimiento RAG
│
├── docs/
│   ├── informe.md                   # Documento maestro: control de versiones + mapa del índice
│   ├── executive_summary.md         # Resumen ejecutivo
│   ├── analysis.md                  # Objetivos, requisitos, riesgos, inventario RAG/tools
│   ├── bpmn/                        # Diagrama BPMN 2.0 (abrir en bpmn.io/Camunda)
│   ├── architecture.md              # Diagramas detallados + orquestación + RAG + HITL
│   ├── agent_contracts.md           # Contratos MCP por agente
│   ├── tools_catalog.md             # Ficha de cada tool (Args/Returns/errores)
│   ├── prompts_catalog.md           # Catálogo de prompts por agente
│   ├── security.md                  # Seguridad y privacidad — estado real, sin maquillar
│   ├── evaluation.md                # Plan de evaluación (golden set, sin LangSmith)
│   ├── roi.md                       # Medición de éxito y ROI
│   ├── test_cases.md                # Documentación de tests
│   ├── deployment.md                # Guía de despliegue detallada
│   └── adr/                         # Registro de decisiones de arquitectura (11 ADRs)
│
├── docker-compose.yml               # 10 servicios orquestados
├── Dockerfile.api                   # Backend + WeasyPrint
├── requirements.txt                 # 20 dependencias Python
├── pytest.ini                       # Config de tests
└── .env.example                     # Variables de entorno
```

---

## Decisiones de Arquitectura Clave

Resumen rápido — el detalle completo (contexto, alternativas, consecuencias) está en
[docs/adr/](docs/adr/README.md) como ADRs formales:

| Decisión | Alternativa considerada | Razón de la elección | ADR |
|---|---|---|---|
| Saga + event bus | LangGraph | LangGraph asume orquestación centralizada en un proceso; los 9 agentes son contenedores independientes | [001](docs/adr/ADR-001-saga-vs-langgraph.md) |
| Ollama local | Anthropic Claude API | Costo cero por token para correr cientos de sagas de prueba/demo | [002](docs/adr/ADR-002-ollama-vs-anthropic.md) |
| Topología híbrida | Malla pura | La malla complica la trazabilidad; la híbrida mantiene jerarquía con paralelismo | [003](docs/adr/ADR-003-topologia-hibrida.md) |
| Optimistic locking Redis | Locks de BD | Redis SETNX es O(1) y no bloquea la BD | [004](docs/adr/ADR-004-optimistic-locking-redis.md) |
| RabbitMQ topic exchange | Kafka | RabbitMQ es suficiente para el volumen; Kafka introduce complejidad operacional innecesaria | [005](docs/adr/ADR-005-rabbitmq-vs-kafka.md) |
| Decimal en precios | float | `float` acumula errores de punto flotante en finanzas; `Decimal` es exacto | [006](docs/adr/ADR-006-decimal-en-finanzas.md) |
| Audit log inmutable | Soft delete | Los registros contables deben ser inmutables para compliance | [007](docs/adr/ADR-007-audit-log-inmutable.md) |
| JSON Schema Draft-07 | Solo Pydantic | Pydantic valida en Python; JSON Schema valida en cualquier lenguaje (frontend, tests) | [008](docs/adr/ADR-008-doble-validacion-schema.md) |
| RAG con pgvector | Vector store dedicado / retrievers LangChain | PostgreSQL ya es el almacén único; evita reintroducir LangChain | [009](docs/adr/ADR-009-rag-pgvector.md) |
| Salida estructurada forzada | Solo prompt engineering | Constrained decoding de Ollama es más confiable que "Return ONLY JSON" con un modelo de 8B | [010](docs/adr/ADR-010-salida-estructurada-forzada.md) |
| Evaluación local (golden set) | LangSmith | No requiere cuenta externa; el sistema no usa LangChain/LangGraph en su camino principal | [011](docs/adr/ADR-011-evaluacion-local-sin-langsmith.md) |

---

*Generado con Claude Code | Everywhere Travel © 2026*
