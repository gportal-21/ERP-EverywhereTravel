# Arquitectura del Sistema Multiagente — Everywhere Travel

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

## 7. Flujo de Mensajes MCP

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

## 8. Shared State Architecture

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
