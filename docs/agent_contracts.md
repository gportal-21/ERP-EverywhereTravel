# Contratos MCP por Agente — Everywhere Travel

Cada agente define un contrato explícito: qué acepta, qué produce, qué routing key usa.
Todos los mensajes viajan envueltos en `MCPEnvelope` (ver `core/mcp/envelope.py`).

---

## Envelope Base (todos los mensajes)

```json
{
  "message_id":    "uuid-v4",
  "saga_id":       "uuid-v4",
  "sender_agent":  "sales-agent",
  "receiver_agent":"quotation-agent",
  "timestamp":     "2026-05-22T10:30:00Z",
  "correlation_id":"uuid-v4",
  "payload_type":  "PackageRequest",
  "payload":       { ... },
  "retry_count":   0,
  "ttl_seconds":   300,
  "priority":      5
}
```

**Agentes válidos:**
`orchestrator-agent` · `sales-agent` · `quotation-agent` · `reservation-agent` ·
`finance-agent` · `document-agent` · `validation-agent` · `monitoring-agent` ·
`notification-agent` · `api-gateway`

---

## 1. OrchestratorAgent

### Entradas
| payload_type | routing_key | Origen |
|---|---|---|
| `PackageInquiry` | `orchestrator.route` | api-gateway |
| `PackageRequest` | `orchestrator.route` | sales-agent |
| `QuotationResult` | `orchestrator.route` | quotation-agent |
| `ReservationCreate` | `orchestrator.route` | api-gateway |
| `PaymentEvent` | `orchestrator.route` | api-gateway |
| `ConflictNotification` | `orchestrator.conflict` | any agent |
| `AgentDegraded` | `orchestrator.route` | monitoring-agent |
| `ValidationBlocking` | `orchestrator.blocking` | validation-agent |

### Salidas
| payload_type | routing_key | Destino |
|---|---|---|
| `PackageInquiry` | `sales.inquiry` | sales-agent |
| `PackageRequest` | `quotation.request` | quotation-agent |
| `QuotationResult` | `validation.check` | validation-agent |
| `ReservationCreate` | `reservation.create` | reservation-agent |
| `PaymentEvent` | `finance.payment` | finance-agent |
| `DocumentRequest` | `document.generate` | document-agent |
| `ConflictResolved` | `monitoring.conflict_resolved` | monitoring-agent |

### Contrato de resolución de conflictos
```json
{
  "payload_type": "ConflictNotification",
  "payload": {
    "entity_type": "availability|quotation|reservation",
    "entity_id": "uuid",
    "agents": ["agent-a", "agent-b"],
    "reason": "string"
  }
}
```

---

## 2. SalesAgent

### Entradas
| payload_type | routing_key |
|---|---|
| `PackageInquiry` | `sales.inquiry` |
| `QuotationResult` | `sales.quotation_validated` |

### PackageInquiry (Input Schema)
```json
{
  "client_id":      "uuid",
  "destination":    "Cusco, Perú",
  "start_date":     "2026-08-01",
  "end_date":       "2026-08-06",
  "budget_min":     1500.0,
  "budget_max":     3000.0,
  "traveler_count": 2,
  "preferences":    ["hotel 4*", "vuelo incluido"],
  "inquiry_source": "dashboard"
}
```

### Salidas
| payload_type | routing_key |
|---|---|
| `PackageRequest` | `orchestrator.route` |

### PackageRequest (Output Schema)
```json
{
  "inquiry_id":          "uuid",
  "client_id":           "uuid",
  "package_template_id": "uuid | null",
  "destination":         "Cusco, Perú",
  "start_date":          "2026-08-01",
  "end_date":            "2026-08-06",
  "traveler_count":      2,
  "customizations":      { "hotel_category": "4*" },
  "budget_range":        { "min": 1500.0, "max": 3000.0 },
  "priority":            "NORMAL"
}
```

**Invariantes:**
- Nunca calcula precios — delega a QuotationAgent
- Nunca crea reservas — delega a ReservationAgent
- Siempre actualiza `memory:client:{id}` en Redis

---

## 3. QuotationAgent

### Entradas
| payload_type | routing_key |
|---|---|
| `PackageRequest` | `quotation.request` |

### Salidas
| payload_type | routing_key |
|---|---|
| `QuotationResult` | `orchestrator.route` → validation |

### QuotationResult (Output Schema)
```json
{
  "quote_id":    "uuid",
  "version":     1,
  "package_id":  "uuid | null",
  "client_id":   "uuid",
  "line_items": [
    {
      "concept":    "Cusco Mágico — 2 personas",
      "unit_price": 1800.0,
      "quantity":   2,
      "subtotal":   3600.0
    },
    {
      "concept":    "IGV (18%)",
      "unit_price": 648.0,
      "quantity":   1,
      "subtotal":   648.0
    }
  ],
  "total_cost":    4392.0,
  "margin_pct":    20.0,
  "currency":      "PEN",
  "valid_until":   "2026-05-24T10:30:00Z",
  "status":        "DRAFT",
  "anomaly_flags": []
}
```

**Anomaly flags posibles:**
| Flag | Condición |
|---|---|
| `OVER_BUDGET` | `total_cost > budget_max * 1.1` |
| `LOW_MARGIN` | `margin_pct < 15` |
| `ZERO_COST_ERROR` | `total_cost == 0` |

**Fórmula de precios:**
```
base_cost  = sum(line_items.subtotal) — sin impuestos ni margen
margin     = base_cost × margin_pct / 100
taxes      = base_cost × 0.18          (IGV Perú)
total_cost = base_cost + margin + taxes
```

**Versioning:** Cada llamada a `handle_message` incrementa `Redis[quote_version:{quote_id}]`.

---

## 4. ValidationAgent

### Entradas
| payload_type | routing_key |
|---|---|
| `QuotationResult` | `quotation.request` (shared queue) |
| `ReservationRecord` | `reservation.create` (shared queue) |

### Salidas
| payload_type | routing_key | Condición |
|---|---|---|
| `QuotationResult` (VALIDATED) | `sales.quotation_validated` | overall_status=PASS |
| `ValidationBlocking` | `orchestrator.blocking` | severity=BLOCKING |

### ValidationResult (Output Schema)
```json
{
  "validation_id": "uuid",
  "entity_type":   "QuotationResult",
  "entity_id":     "quote-uuid",
  "rules_checked": [
    { "rule_id": "R001", "passed": true,  "severity": "INFO",  "message": "Margen OK (20%)" },
    { "rule_id": "R002", "passed": true,  "severity": "INFO",  "message": "Costo positivo" },
    { "rule_id": "R003", "passed": true,  "severity": "INFO",  "message": "Vigencia OK" },
    { "rule_id": "R004", "passed": true,  "severity": "INFO",  "message": "3 items" }
  ],
  "overall_status":  "PASS",
  "compliance_flags": [],
  "audited_at":      "2026-05-22T10:30:01Z"
}
```

### Reglas implementadas
| ID | Entidad | Condición | Severidad si falla |
|---|---|---|---|
| R001 | Quotation | `margin_pct >= 15` | ERROR / BLOCKING si < 0 |
| R002 | Quotation | `total_cost > 0` | BLOCKING |
| R003 | Quotation | `valid_until > now` | ERROR |
| R004 | Quotation | `len(line_items) > 0` | BLOCKING |
| R010 | Reservation | `travel_start >= now + 48h` | ERROR |
| R011 | Reservation | `code matches ET-YYYYMMDD-XXXXX` | ERROR |
| R012 | Reservation | `traveler_count >= 1` | BLOCKING |

**Invariante:** El audit log es **inmutable** — nunca se actualiza ni elimina un `validation_log`.

---

## 5. ReservationAgent

### Entradas
| payload_type | routing_key |
|---|---|
| `ReservationCreate` | `reservation.create` |
| `QuotationResult` (VALIDATED) | `reservation.create` |

### Salidas
| payload_type | routing_key | Condición |
|---|---|---|
| `ReservationRecord` | `finance.reservation_created` | Éxito |
| `ReservationFailed` | `orchestrator.route` | Validación falla |
| `ConflictNotification` | `orchestrator.conflict` | Lock no adquirido |

### ReservationRecord (Output Schema)
```json
{
  "reservation_code": "ET-20260801-AB123",
  "quote_id":         "uuid",
  "client_id":        "uuid",
  "package_id":       "uuid | null",
  "travel_start":     "2026-08-01T00:00:00Z",
  "travel_end":       "2026-08-06T00:00:00Z",
  "traveler_count":   2,
  "status":           "PENDING_PAYMENT",
  "version":          1,
  "created_by_agent": "reservation-agent"
}
```

**Formato del código:** `ET-{YYYYMMDD}-{5 chars hex uppercase}`

**Lock atómico:**
```
Redis SETNX key="lock:availability:{package_id}:{date}" value=agent_id TTL=30s
→ True: lock adquirido, procede
→ False: ConflictNotification al Orchestrator
```

---

## 6. FinanceAgent

### Entradas
| payload_type | routing_key |
|---|---|
| `ReservationRecord` | `finance.reservation_created` |
| `PaymentEvent` | `finance.payment` |

### Salidas
| payload_type | routing_key | Condición |
|---|---|---|
| `DocumentJob` (INVOICE) | `document.generate` | Al crear liquidación |
| `DocumentJob` (LIQUIDATION) | `document.generate` | Al completar pago |
| `LiquidationRecord` | `document.generate` | Al balance = 0 |
| `PaymentOverdue` | `notification.payment_overdue` | Pago vencido |

### LiquidationRecord (Output Schema)
```json
{
  "liquidation_id":    "uuid",
  "reservation_code":  "ET-20260801-AB123",
  "total_charged":     4392.0,
  "total_paid":        4392.0,
  "commission_amount": 351.36,
  "status":            "COMPLETE",
  "transactions": [
    {
      "date":      "2026-05-22T10:00:00Z",
      "amount":    2196.0,
      "method":    "TRANSFER",
      "reference": "TXN-001"
    }
  ]
}
```

### Cronograma de pagos por monto
| Rango total | Cuotas | Distribución |
|---|---|---|
| ≤ 1,000 PEN | 1 | 100% al reservar |
| 1,001 – 5,000 PEN | 2 | 50% reservar · 50% 30d antes viaje |
| > 5,000 PEN | 3 | 30% reservar · 40% 30d antes · 30% 7d antes |

**Comisión:** 8% fija sobre `total_cost`. Asignada al `created_by_agent` de la reserva.

---

## 7. DocumentAgent

### Entradas
| payload_type | routing_key |
|---|---|
| `DocumentJob` | `document.generate` |

### DocumentJob (Input Schema)
```json
{
  "job_id":         "uuid",
  "document_type":  "INVOICE",
  "reference_id":   "ET-20260801-AB123",
  "reference_type": "reservation",
  "template_data":  { ... },
  "priority":       "HIGH",
  "requested_by":   "finance-agent"
}
```

### Salidas
| payload_type | routing_key | Condición |
|---|---|---|
| `DocumentReady` | `notification.document_ready` | Éxito |
| `DocumentFailed` | `monitoring.document_failed` | 3 reintentos agotados |

### DocumentReady (Output Schema)
```json
{
  "job_id":         "uuid",
  "document_type":  "INVOICE",
  "reference_id":   "ET-20260801-AB123",
  "document_url":   "https://minio.../invoice/2026/05/job-id.pdf?X-Amz-...",
  "expires_at":     "2026-05-29T10:30:00Z",
  "generated_at":   "2026-05-22T10:30:05Z"
}
```

### Campos requeridos por tipo de documento
| Tipo | Campos obligatorios en `template_data` |
|---|---|
| INVOICE | `reservation_code`, `total_cost` |
| LIQUIDATION | `reservation_code`, `total_charged`, `total_paid` |
| VOUCHER | `reservation_code`, `destination` |
| REPORT | `report_type`, `period` |
| CONTRACT | `reservation_code`, `client_id` |

**Política de retry:** Exponential backoff 1s → 2s → 4s (max 3 intentos). Tras 3 fallos → `DocumentFailed`.

---

## 8. MonitoringAgent

### Entradas (event bus)
| payload_type | routing_key |
|---|---|
| `AgentDegraded` | `monitoring.#` |
| `SagaCompensate` | `monitoring.compensate` |
| `DocumentFailed` | `monitoring.document_failed` |
| `ConflictResolved` | `monitoring.conflict_resolved` |

### Loops activos
| Loop | Intervalo | Acción |
|---|---|---|
| Heartbeat check | 30s | Verifica TTL de `heartbeat:{agent_id}` en Redis |
| Stale saga detection | 60s | Sagas RUNNING sin progreso > 5min → compensar |
| Dead-letter requeue | 120s | Procesa hasta 10 mensajes del DLQ con backoff |

### AgentHeartbeat (Schema emitido por cada agente)
```json
{
  "agent_id":    "quotation-agent",
  "agent_type":  "quotation-agent",
  "status":      "HEALTHY",
  "timestamp":   "2026-05-22T10:30:00Z",
  "metrics": {
    "messages_processed": 45,
    "errors_last_minute": 0,
    "avg_latency_ms":     320
  }
}
```

---

## 9. NotificationAgent

### Entradas
| payload_type | Canal destino |
|---|---|
| `DocumentReady` | `client:{client_id}` WebSocket |
| `ReservationConfirmed` | `client:{client_id}` WebSocket |
| `PaymentOverdue` | `client:{client_id}` + email |
| `AgentDegraded` | `system:alerts` WebSocket |
| `ValidationFailed` | `client:{client_id}` WebSocket |

### Deduplicación
- Key Redis: `notif:{event_type}:{reference_id}` con TTL 60s
- Si key existe: mensaje ignorado sin entregar

### Plantillas de mensaje
| Event | Template |
|---|---|
| `DocumentReady` | "Documento disponible: {document_type}. Descarga: {document_url}" |
| `ReservationConfirmed` | "Reserva {reservation_code} confirmada. Viaje: {travel_start}" |
| `PaymentOverdue` | "ALERTA: Pago vencido — Reserva {reservation_code}" |
| `AgentDegraded` | "ALERTA SISTEMA: Agente {agent_id} degradado" |
