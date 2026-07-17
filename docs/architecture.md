# Arquitectura del Sistema Multiagente — Everywhere Travel

> **Nota sobre notación:** los diagramas de esta sección usan **Mermaid** (sequenceDiagram,
> stateDiagram, erDiagram, flowchart) porque renderizan directamente en GitHub/editores
> Markdown. Adicionalmente existe un **diagrama BPMN 2.0 formal** del flujo principal
> (Escenario A: cotización) en [`docs/bpmn/escenario_a_cotizacion.bpmn`](bpmn/escenario_a_cotizacion.bpmn)
> — es XML estándar BPMN 2.0 con lanes por agente (API Gateway, Orchestrator, Sales,
> Quotation, Validation), gateway exclusivo para el caso BLOCKING y eventos de fin
> COMPLETED/FAILED. Se abre en [demo.bpmn.io](https://demo.bpmn.io), Camunda Modeler o
> draw.io (importar BPMN), desde donde puede exportarse como imagen para el informe.

## 1. Diagrama de Componentes (Mermaid)

```mermaid
graph TB
    subgraph Frontend["Frontend Layer"]
        UI["Dashboard Next.js\n:3000"]
        WS_CLIENT["WebSocket Client\nReal-time notifications"]
    end

    subgraph Gateway["API Gateway — FastAPI :8000"]
        REST["REST /api/v1/*"]
        WS_SERVER["WebSocket /ws/{channel}"]
        AUTH["JWT Auth Middleware"]
        METRICS["/metrics Prometheus"]
    end

    subgraph Orchestration["Orchestration Layer"]
        OA["OrchestratorAgent\nSaga · Routing · Conflicts"]
        MON["MonitoringAgent\nCircuit Breaker · Dead-Letter"]
    end

    subgraph SalesDomain["Sales Domain"]
        SA["SalesAgent\nCatalog · Memory"]
        QA["QuotationAgent\nPricing · Versioning"]
    end

    subgraph FinanceDomain["Finance Domain"]
        FA["FinanceAgent\nLedger · Commissions"]
        VA["ValidationAgent\nRules · Compliance"]
    end

    subgraph DocDomain["Document Domain"]
        DA["DocumentAgent\n3 async workers"]
        NA["NotificationAgent\nWebSocket · Email"]
    end

    subgraph ResDomain["Reservation Domain"]
        RA["ReservationAgent\nAtomic Lock · Code Gen"]
    end

    subgraph Infra["Infrastructure Layer"]
        EB["RabbitMQ :5672\nTopic Exchange"]
        REDIS["Redis :6379\nShared State · Locks"]
        PG["PostgreSQL :5432\nPersistent Store"]
        S3["MinIO :9000\nDocument Storage"]
    end

    UI -->|HTTP| REST
    WS_CLIENT <-->|WebSocket| WS_SERVER
    REST --> AUTH
    AUTH --> OA

    OA <-->|MCP Envelope| EB
    OA --> SA & FA & RA
    OA <--> REDIS

    SA -->|PackageRequest| QA
    QA -->|QuotationResult| VA
    VA -->|VALIDATED| SA

    RA -->|ReservationRecord| FA
    FA -->|DocumentJob| DA
    DA -->|DocumentReady| NA

    EB --> SA & QA & RA & FA & DA & NA & MON
    MON <--> REDIS

    SA & QA & RA & FA & VA & DA & NA & MON --> PG
    DA --> S3
    NA --> WS_SERVER
```

## 2. Diagrama de Secuencia — Escenario A: Paquete Personalizado

```mermaid
sequenceDiagram
    participant API as API Gateway
    participant OA as Orchestrator
    participant SA as Sales Agent
    participant QA as Quotation Agent
    participant VA as Validation Agent
    participant DB as PostgreSQL
    participant RD as Redis

    API->>OA: MCPEnvelope{PackageInquiry}
    OA->>RD: saga.start(saga_id)
    OA->>SA: route(PackageRequest)

    SA->>RD: get_client_memory(client_id)
    SA->>DB: packages.search(destination, budget)
    SA->>SA: build_package_request (LLM)
    SA->>RD: set_client_memory(client_id, updated)
    SA->>QA: MCPEnvelope{PackageRequest}

    QA->>DB: fetch_package(template_id)
    QA->>QA: calculate_price (Decimal)
    QA->>QA: detect_anomalies()
    QA->>RD: incr(quote_version:{quote_id})
    QA->>DB: INSERT quotation (DRAFT)
    QA->>VA: MCPEnvelope{QuotationResult DRAFT}

    VA->>VA: evaluate_rules R001-R012
    VA->>DB: INSERT validation_log (immutable)

    alt PASS
        VA->>SA: MCPEnvelope{QuotationResult VALIDATED}
        SA->>RD: publish(client:{id}, quotation_ready)
    else BLOCKING
        VA->>OA: MCPEnvelope{ValidationBlocking}
        OA->>OA: halt_saga(saga_id)
    end
```

## 3. Diagrama de Secuencia — Escenario C: Reserva + Liquidación + Documentos

```mermaid
sequenceDiagram
    participant RA as Reservation Agent
    participant FA as Finance Agent
    participant DA as Document Agent
    participant NA as Notification Agent
    participant RD as Redis
    participant DB as PostgreSQL
    participant S3 as MinIO

    RA->>RD: SETNX lock:availability:{pkg}:{date}
    Note over RA,RD: Atomic lock (TTL=30s)

    alt Lock acquired
        RA->>DB: INSERT reservation (PENDING_PAYMENT)
        RA->>RD: release_lock()
        RA-->>FA: MCPEnvelope{ReservationRecord}

        FA->>FA: build_payment_schedule(total)
        FA->>FA: calculate_commission(8%)
        FA->>DB: INSERT liquidation (PARTIAL)
        FA-->>DA: MCPEnvelope{DocumentJob INVOICE}

        DA->>DA: validate_required_fields()
        DA->>DA: render_jinja2_template()
        DA->>DA: weasyprint → PDF
        DA->>S3: upload(pdf_bytes)
        S3-->>DA: presigned_url (7 days)
        DA->>DB: PATCH document_job (COMPLETE)
        DA-->>NA: MCPEnvelope{DocumentReady}

        NA->>RD: publish(client:{id}, document_ready)
        NA-->>Client: WebSocket push
    else Lock not acquired
        RA-->>OA: MCPEnvelope{ConflictNotification}
        OA->>OA: resolve_conflict (LLM)
    end
```

## 4. Diagrama de Estado — Circuit Breaker

```mermaid
stateDiagram-v2
    [*] --> CLOSED

    CLOSED --> OPEN: 5 failures in 60s
    OPEN --> HALF_OPEN: 30s cooldown elapsed
    HALF_OPEN --> CLOSED: 1 success
    HALF_OPEN --> OPEN: 1 failure (immediate)
    CLOSED --> CLOSED: success (reset counters)

    note right of OPEN
        Calls rejected immediately
        CircuitBreakerOpenError raised
        No downstream calls made
    end note

    note right of HALF_OPEN
        1 test call allowed
        Decides recovery or re-open
    end note
```

## 5. Diagrama de Estado — Saga

```mermaid
stateDiagram-v2
    [*] --> RUNNING: saga.start()

    RUNNING --> COMPLETED: all steps COMPLETED
    RUNNING --> COMPENSATING: step FAILED
    RUNNING --> FAILED: stale > 5min (monitoring)

    COMPENSATING --> FAILED: compensation complete
    COMPENSATING --> REQUIRES_MANUAL: 3 retries exhausted

    FAILED --> [*]
    COMPLETED --> [*]
    REQUIRES_MANUAL --> [*]: human intervention
```

## 6. Diagrama ER — Entidades principales

```mermaid
erDiagram
    clients {
        uuid id PK
        string full_name
        string email UK
        jsonb preferences
    }

    packages {
        uuid id PK
        string name
        string destination
        numeric base_price
        int duration_days
        jsonb includes
    }

    quotations {
        uuid id PK
        uuid quote_id
        int version
        uuid client_id FK
        uuid package_id FK
        jsonb line_items
        numeric total_cost
        numeric margin_pct
        string status
    }

    reservations {
        uuid id PK
        string reservation_code UK
        uuid quote_id
        uuid client_id FK
        timestamp travel_start
        timestamp travel_end
        string status
        int version
    }

    liquidations {
        uuid id PK
        string liquidation_code UK
        uuid reservation_id FK
        numeric total_charged
        numeric total_paid
        numeric commission_amount
        string status
    }

    transactions {
        uuid id PK
        uuid liquidation_id FK
        numeric amount
        string payment_method
        timestamp created_at
    }

    sagas {
        uuid id PK
        string saga_type
        string status
        jsonb steps
        jsonb context
    }

    validation_logs {
        uuid id PK
        string entity_type
        uuid entity_id
        jsonb rules_checked
        string overall_status
    }

    clients ||--o{ quotations : "requests"
    clients ||--o{ reservations : "books"
    packages ||--o{ quotations : "quoted_as"
    packages ||--o{ reservations : "reserved_as"
    reservations ||--o| liquidations : "has"
    liquidations ||--o{ transactions : "contains"
```

## 7. Orquestación: Saga + Event Bus vs. LangGraph

Este sistema **no usa LangGraph**. La orquestación es un patrón Saga (`core/saga_coordinator.py`)
sobre un event bus (RabbitMQ), con cada agente como proceso/contenedor independiente —
justificación completa en [ADR-001](adr/ADR-001-saga-vs-langgraph.md).

```mermaid
flowchart TB
    subgraph LangGraph["Modelo LangGraph (no usado)"]
        LG_STATE["StateGraph en memoria\n(un solo proceso)"]
        LG_NODE1["Nodo: Sales"] --> LG_STATE
        LG_NODE2["Nodo: Quotation"] --> LG_STATE
        LG_NODE3["Nodo: Validation"] --> LG_STATE
        LG_CP["Checkpointer\n(requiere backend compartido)"]
        LG_STATE -.->|"aristas condicionales\nen el grafo"| LG_CP
    end

    subgraph Saga["Modelo Saga + Event Bus (usado)"]
        SA_ORCH["SagaCoordinator\n(Redis hot + Postgres cold)"]
        SA_A["SalesAgent\n(contenedor propio)"] -->|MCPEnvelope| SA_BUS["RabbitMQ\ntopic exchange"]
        SA_B["QuotationAgent\n(contenedor propio,\nescalable independiente)"] -->|MCPEnvelope| SA_BUS
        SA_C["ValidationAgent\n(contenedor propio)"] -->|MCPEnvelope| SA_BUS
        SA_BUS --> SA_ORCH
        SA_MON["MonitoringAgent\ndetecta sagas estancadas\n(> 5 min)"] --> SA_ORCH
    end
```

**Por qué el modelo de la derecha:** cada agente ya necesita ser un proceso independiente
(Document Agent corre en 3 réplicas; cualquier agente puede caerse sin tumbar a los demás).
LangGraph asume que el grafo vive en un solo proceso con un checkpointer compartido —
forzar esa forma sobre 9 contenedores independientes habría significado reconstruir a mano
el mismo event bus que RabbitMQ ya provee, sin ganar nada a cambio. El "checkpointing" de
LangGraph se resuelve aquí con el log de pasos de la Saga en Redis + Postgres, que además
sirve como auditoría permanente (`sagas.steps`), algo que un checkpointer de grafo no da
gratis.

## 7bis. Subsistema RAG

`SalesAgent` e `ItineraryAgent` recuperan conocimiento por similaridad semántica en vez de
match exacto de string — justificación completa en [ADR-009](adr/ADR-009-rag-pgvector.md).

```mermaid
flowchart LR
    subgraph Fuentes["Fuentes de conocimiento"]
        PKG["packages\n(catálogo turístico)"]
        DK["destination_knowledge\n(core/rag/content.py,\nguías curadas de destino)"]
    end

    subgraph Indexacion["Indexación (scripts/build_rag_index.py)"]
        EMB["Ollama /api/embeddings\nnomic-embed-text (768 dim)"]
    end

    PKG --> EMB
    DK --> EMB
    EMB -->|"embedding vector(768)"| PGV[("PostgreSQL + pgvector\nidx ivfflat cosine")]

    subgraph Consumo
        SALES["SalesAgent\n_tool_semantic_search_packages\n(fallback si búsqueda exacta falla)"]
        ITIN["ItineraryAgent\n_tool_get_destination_info\n(RAG primero, dict estático como fallback)"]
    end

    SALES -->|"GET /packages/semantic-search"| PGV
    ITIN -->|"GET /knowledge/destinations/search"| PGV
```

Flujo de recuperación: la consulta del cliente (destino + preferencias) se embebe con el
mismo modelo, y `ORDER BY embedding <=> :query_embedding LIMIT k` (operador de distancia
de coseno de pgvector) devuelve los `k` resultados más cercanos. Si Ollama no está
disponible, el endpoint responde `503` y el agente cae a su fallback determinístico
existente (mismo patrón de resiliencia usado en el resto del sistema).

## 7ter. Salida estructurada (constrained decoding)

Ver [ADR-010](adr/ADR-010-salida-estructurada-forzada.md). Cada agente con LLM define su
contrato de salida como modelo Pydantic; `.model_json_schema()` se pasa como
`response_schema` al `Agent` de `agents/swarms_compat.py`, que lo reenvía a Ollama como
`format` — el modelo queda restringido a emitir JSON conforme al schema durante el
decoding, no solo "instruido" a hacerlo por prompt. `core/structured_output.py::parse_structured_output()`
valida el resultado contra el mismo modelo Pydantic como segunda capa, con extracción
manual de bloques JSON como red de seguridad final antes de caer al fallback determinístico.

## 7quater. Human-in-the-loop (HITL)

El punto de entrada de HITL es la evaluación de conflictos del Orchestrator
(`agents/orchestrator/agent.py::_handle_conflict`, Fase 3). No es un simple "avisar a
alguien" — es un _gate_ de decisión basado en confianza medida, no en intuición:

```mermaid
flowchart TD
    CONF["ConflictNotification\n(ej. dos agentes reportan estado distinto\npara la misma entidad)"]
    CONF --> VAL["conflict-validation-agent\n¿es un problema de integridad?\nconfidence: 0.0-1.0"]
    CONF --> MON["conflict-monitoring-agent\n¿impacto operativo?\nneeds_escalation: bool"]

    VAL --> CHECK{"confidence < 0.7\nO needs_escalation=true?"}
    MON --> CHECK

    CHECK -->|"No"| AUTO["Resolución automática\n(ConflictResolved, needs_escalation=false)"]
    CHECK -->|"Sí"| ESC["MonitoringAgent._handle_conflict_resolved()\n→ _escalate_to_human()"]
    ESC --> ALERT["Redis pub/sub: system:alerts\ntype=REQUIRES_MANUAL_INTERVENTION"]
    ALERT --> WS["WebSocket → Dashboard\n(operador humano revisa)"]
```

**Por qué 0.7 como umbral:** es el valor que ya prometía
`agents/orchestrator/prompts/system_prompt.txt` ("Escalate to human review when
confidence < 0.7") — antes de esta iteración esa era una instrucción de prompt sin
ningún cálculo real detrás (el LLM no tenía forma de que su "confidence" llegara a
ningún lado). Ahora `ConflictValidationOutput.confidence` es un campo forzado por JSON
Schema (ver [ADR-010](adr/ADR-010-salida-estructurada-forzada.md)), así que el umbral
opera sobre un número real, no sobre una promesa de prompt.

**Otros dos puntos de escalación humana** (no pasan por confidence, son deterministas):
`MonitoringAgent._requeue_message()` tras 3 reintentos fallidos de un mensaje
dead-letter, y `_handle_doc_failure()` tras 3 fallos consecutivos de generación de
documento — ambos comparten el mismo `_escalate_to_human()`.

**Limitación conocida:** la escalación es de _notificación_ (el operador se entera vía
WebSocket/alerta), no de _aprobación bloqueante_ — no hay un endpoint `POST
/approve` que pause la Saga hasta que un humano actúe explícitamente. La Saga queda en
`REQUIRES_MANUAL` (ver diagrama de estado de Saga en la sección 5) esperando
intervención manual directa sobre los datos, no un "reanudar" programático. Formalizar
un endpoint de aprobación/rechazo es la extensión natural si el proceso de negocio lo
exige.

## 8. Flujo de Mensajes MCP

```mermaid
flowchart LR
    subgraph Schema["MCP Envelope — JSON Schema"]
        E["message_id: UUID\nsaga_id: UUID\nsender_agent: str\nreceiver_agent: str\ntimestamp: ISO8601\ncorrelation_id: UUID\npayload_type: str\npayload: object\nretry_count: 0-10\nttl_seconds: int\npriority: 1-10"]
    end

    subgraph Validation["Validación en cada hop"]
        V1["1. Agent registry check\n(sender + receiver válidos)"]
        V2["2. TTL expiry check\n(timestamp + ttl_seconds)"]
        V3["3. Dedup check\n(Redis processed_ids)"]
        V4["4. JSON Schema Draft-07\n(payload vs schema)"]
    end

    E --> V1 --> V2 --> V3 --> V4
    V4 -->|PASS| Handler["Agent Handler"]
    V4 -->|FAIL| DLQ["Dead-Letter Queue"]
```

## 9. Shared State Architecture

```
Redis Key Space:

saga:{uuid}                → SagaState JSON           TTL: 1h
lock:{type}:{id}           → agent_id (owner)         TTL: 30s
processed:{message_id}     → "1"                      TTL: 24h
heartbeat:{agent_id}       → AgentHeartbeat JSON       TTL: 90s
circuit:{service}          → CircuitState JSON         TTL: 5min
circuit:failures:{service} → int counter               TTL: 60s
memory:client:{id}         → ClientMemory JSON         no TTL
notif:{type}:{ref_id}      → "1" (dedup)              TTL: 60s

PostgreSQL Tables (persistent):
quotations    → versionadas, inmutables por (quote_id, version)
validation_logs → inmutables (no UPDATE/DELETE en producción)
sagas         → audit trail de flujos
transactions  → ledger financiero inmutable
```
