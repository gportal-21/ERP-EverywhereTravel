# Casos de Prueba — Everywhere Travel Sistema Multiagente

## Taxonomía de Tests

```
tests/
├── unit/          Sin dependencias externas. Siempre deben pasar.
├── integration/   Requieren docker compose up. Validan flujos reales.
└── adversarial/   Edge cases extremos, seguridad, límites del sistema.
```

---

## TESTS UNITARIOS

### Suite: MCP Envelope (`tests/unit/test_mcp_envelope.py`)

---

#### TC-U-001: Creación válida de envelope
**Categoría:** Unitario — Happy path
**Precondición:** Ninguna

**Entrada:**
```python
MCPEnvelope(
    saga_id="saga-123",
    sender_agent="sales-agent",
    receiver_agent="quotation-agent",
    payload_type="PackageRequest",
    payload={"client_id": "c1", "destination": "Lima"},
)
```
**Resultado esperado:** Objeto creado sin errores. `message_id`, `correlation_id` generados automáticamente. `retry_count=0`.
**Cobertura:** Flujo principal de comunicación inter-agente.

---

#### TC-U-002: Agente emisor inválido
**Categoría:** Unitario — Validación de contrato
**Entrada:** `sender_agent="unknown-agent"` (no registrado)
**Resultado esperado:** `ValueError: sender_agent inválido`
**Cobertura:** Enforza el registry de agentes válidos. Previene mensajes de fuentes no autorizadas.

---

#### TC-U-003: Agente receptor inválido
**Categoría:** Unitario — Validación de contrato
**Entrada:** `receiver_agent="hacker-agent"`
**Resultado esperado:** `ValueError: receiver_agent inválido`
**Cobertura:** Previene routing a destinos inexistentes.

---

#### TC-U-004: Detección de mensaje no expirado
**Categoría:** Unitario — TTL
**Entrada:** Envelope creado ahora, `ttl_seconds=300`
**Resultado esperado:** `is_expired() == False`

---

#### TC-U-005: Detección de mensaje expirado
**Categoría:** Unitario — TTL
**Entrada:** Timestamp hace 400 segundos, `ttl_seconds=300`
**Resultado esperado:** `is_expired() == True`
**Cobertura:** Previene el procesamiento de mensajes obsoletos en el sistema.

---

#### TC-U-006: Make reply invierte sender/receiver
**Categoría:** Unitario — Protocolo de respuesta
**Entrada:** Envelope de sales-agent → quotation-agent
**Resultado esperado:** Reply tiene sender=quotation-agent, receiver=sales-agent. `correlation_id` idéntico al original.
**Cobertura:** Garantiza que las respuestas lleguen al emisor correcto.

---

#### TC-U-007: Round-trip JSON
**Categoría:** Unitario — Serialización
**Entrada:** Envelope completo
**Resultado esperado:** `MCPEnvelope.model_validate_json(env.model_dump_json()).message_id == env.message_id`
**Cobertura:** Integridad de datos en tránsito por RabbitMQ.

---

#### TC-U-008: PackageInquiry con 51 viajeros
**Categoría:** Unitario — Límites de dominio
**Entrada:** `traveler_count=51`
**Resultado esperado:** `ValidationError` (Pydantic, máximo 50)
**Cobertura:** Límite operacional real de la agencia.

---

### Suite: Circuit Breaker (`tests/unit/test_circuit_breaker.py`)

---

#### TC-U-010: Estado CLOSED permite llamadas
**Categoría:** Unitario — Happy path
**Precondición:** Circuit en estado CLOSED (por defecto)
**Resultado esperado:** Función ejecutada, resultado retornado.

---

#### TC-U-011: CLOSED → OPEN tras 5 fallos
**Categoría:** Unitario — Transición de estado
**Entrada:** 5 llamadas consecutivas que lanzan excepción
**Resultado esperado:** `Redis["circuit:test-service"]["state"] == "OPEN"`
**Cobertura:** Protege servicios downstream ante fallos en cascada.

---

#### TC-U-012: OPEN rechaza sin ejecutar
**Categoría:** Unitario — Protección activa
**Precondición:** Circuit en OPEN, `last_failure` hace 10s (< 30s cooldown)
**Resultado esperado:** `CircuitBreakerOpenError` lanzado. Función downstream NUNCA llamada.
**Métrica clave:** `call_count == 0` (verificado con counter externo)

---

#### TC-U-013: HALF_OPEN + éxito → CLOSED
**Categoría:** Unitario — Recuperación
**Precondición:** Circuit en HALF_OPEN
**Resultado esperado:** `Redis["circuit:test-service"]["state"] == "CLOSED"`
**Cobertura:** El sistema se recupera automáticamente sin intervención humana.

---

## TESTS DE INTEGRACIÓN

### Suite: Flujo de Cotización (`tests/integration/test_quotation_flow.py`)

---

#### TC-I-001: Consulta inicia saga
**Categoría:** Integración — Escenario A
**Precondición:** `docker compose up` corriendo. Cliente creado.
**Entrada:**
```json
POST /api/v1/inquiries
{
  "client_id": "uuid",
  "destination": "Cusco",
  "start_date": "2026-08-01",
  "end_date": "2026-08-06",
  "budget_min": 1000,
  "budget_max": 3000,
  "traveler_count": 2
}
```
**Resultado esperado:**
```json
{ "saga_id": "uuid", "status": "processing", "message_id": "uuid" }
```
**Verificación adicional:** `GET /api/v1/sagas/{saga_id}` retorna saga en estado `RUNNING`.

---

#### TC-I-002: 3 consultas simultáneas generan sagas únicas
**Categoría:** Integración — Escenario B (concurrencia)
**Precondición:** API corriendo
**Mecanismo:** 3 threads Python simultáneos
**Resultado esperado:** 3 `saga_id` distintos. Sin colisiones. Sin errores 500.
**Métrica:** Tiempo total < 3× tiempo de una sola consulta (paralelismo real).

---

#### TC-I-003: Búsqueda de catálogo retorna resultados
**Categoría:** Integración — Catálogo
**Entrada:** `GET /api/v1/packages/search?destination=Cusco&budget_max=5000`
**Resultado esperado:** Lista no vacía de paquetes con `base_price <= 5000`.

---

#### TC-I-004: Reserva duplicada rechazada
**Categoría:** Integración — Conflicto de disponibilidad
**Mecanismo:** Dos POST a `/api/v1/reservations` con `reservation_code` idéntico
**Resultado esperado:** Segunda llamada retorna error (constraint de BD o 4xx).
**Cobertura:** Garantía de unicidad del `reservation_code`.

---

#### TC-I-005: Cronograma de pagos — monto bajo
**Categoría:** Integración — Lógica financiera
**Entrada:** `total=800 PEN`
**Resultado esperado:** `len(schedule) == 1`, `schedule[0]["pct"] == 100`

---

#### TC-I-006: Cronograma de pagos — monto alto
**Categoría:** Integración — Lógica financiera
**Entrada:** `total=7500 PEN`
**Resultado esperado:** `len(schedule) == 3`, `pcts == [30, 40, 30]`, `sum(pcts) == 100`

---

## TESTS ADVERSARIALES

### Suite: Seguridad y Edge Cases (`tests/adversarial/test_adversarial.py`)

---

#### TC-A-001: Payload vacío no rompe el sistema
**Categoría:** Adversarial — Robustez
**Entrada:** `payload={}`
**Resultado esperado:** Envelope creado. Error capturado en la capa de schema, no en el agente.
**Razón:** El sistema debe degradarse de forma controlada, no hacer crash.

---

#### TC-A-002: Payload de 100,000 caracteres
**Categoría:** Adversarial — DoS / Memory
**Entrada:** `payload={"key": "x" * 100_000}`
**Resultado esperado:** Serialización exitosa. Sin OOM. Sin timeout.
**Límite:** RabbitMQ rechaza mensajes > 128MB por configuración del broker.

---

#### TC-A-003: retry_count=11 rechazado
**Categoría:** Adversarial — Contrato de envelope
**Entrada:** `retry_count=11` (máximo permitido: 10)
**Resultado esperado:** `ValidationError` de Pydantic.
**Razón:** Previene ciclos infinitos de reintento.

---

#### TC-A-004: SQL Injection en payload
**Categoría:** Adversarial — Seguridad
**Entrada:** `{"client_id": "'; DROP TABLE clients; --"}`
**Resultado esperado:** String almacenado literalmente como JSON. Sin ejecución SQL.
**Mecanismo:** SQLAlchemy usa queries parametrizadas. El payload es JSONB, no SQL directo.

---

#### TC-A-005: Presupuesto negativo rechazado por JSON Schema
**Categoría:** Adversarial — Validación de datos
**Entrada:** `budget_min=-1000, budget_max=-500`
**Resultado esperado:** JSON Schema rechaza (minimum=0 para budget_min, minimum=1 para budget_max).
**Cobertura:** El schema es la barrera antes de que el dato llegue a cualquier agente.

---

#### TC-A-006: Margen 0% detectado como anomalía
**Categoría:** Adversarial — Compliance financiero
**Entrada:** `margin_pct=0`
**Resultado esperado:** ValidationAgent retorna `R001: ERROR`.
**Cobertura:** Previene venta a pérdida o sin margen.

---

#### TC-A-007: Costo total cero detectado
**Categoría:** Adversarial — Datos corruptos
**Entrada:** `total_cost=0`
**Resultado esperado:** `anomaly_flags=["ZERO_COST_ERROR"]`. ValidationAgent retorna BLOCKING.

---

#### TC-A-008: Presupuesto superado en 20%
**Categoría:** Adversarial — Anomalía de pricing
**Entrada:** `total_cost=1200, budget_max=1000`
**Resultado esperado:** `anomaly_flags=["OVER_BUDGET"]`

---

#### TC-A-009: Formatos inválidos de reservation_code
**Categoría:** Adversarial — Integridad de datos
**Inputs:** `"ET-abc-12345"`, `"RS-20260101-AAAAA"`, `"ET20260101AAAAA"`, `""`
**Resultado esperado:** Regex `^ET-\d{8}-[A-Z0-9]{5}$` falla para todos.

---

#### TC-A-010: Deduplicación bloquea el mismo mensaje dos veces
**Categoría:** Adversarial — At-exactly-once delivery
**Mecanismo:** Mismo `message_id` procesado dos veces
**Resultado esperado:** `mark_processed(id)` → True primera vez, False segunda vez.
**Garantía:** Los agentes son idempotentes por diseño.

---

#### TC-A-011: Suma de cuotas siempre igual al total
**Categoría:** Adversarial — Precisión financiera
**Inputs:** Varios montos (800, 1000, 5000, 12500 PEN)
**Resultado esperado:** `|sum(schedule.amounts) - total| < 1.00`
**Razón:** Decimal.ROUND_HALF_UP garantiza precisión, pero cuotas porcentuales pueden tener diferencia de centavos por redondeo.

---

#### TC-A-012: Límites exactos del cronograma de pagos
**Categoría:** Adversarial — Casos límite
**Input 1:** Exactamente 1000 PEN → 1 cuota
**Input 2:** Exactamente 5000 PEN → 2 cuotas
**Razón:** Los límites `<=` deben ser inclusivos, no exclusivos.

---

## Matriz de Cobertura

| Componente | Unitarios | Integración | Adversariales | Total |
|---|---|---|---|---|
| MCPEnvelope | 7 | — | 3 | 10 |
| CircuitBreaker | 4 | — | — | 4 |
| QuotationAgent | — | 3 | 3 | 6 |
| ReservationAgent | — | 1 | 2 | 3 |
| FinanceAgent | — | 2 | 2 | 4 |
| ValidationAgent | — | — | 2 | 2 |
| SharedState | — | — | 1 | 1 |
| **Total** | **11** | **6** | **13** | **30** |

---

## Instrucciones de Ejecución

```bash
# 1. Solo unitarios (sin servicios)
pytest tests/unit/ -v --tb=short

# 2. Solo adversariales (sin servicios)
pytest tests/adversarial/ -v --tb=short

# 3. Con servicios levantados
docker compose up -d
pytest tests/integration/ -v -m integration --tb=long

# 4. Todos los tests con reporte de cobertura
pytest tests/ -v --cov=core --cov=agents --cov-report=html

# 5. Solo un test específico
pytest tests/unit/test_mcp_envelope.py::TestMCPEnvelope::test_envelope_expired -v

# 6. Tests en paralelo (requiere pytest-xdist)
pytest tests/unit/ tests/adversarial/ -n auto
```

---

## Métricas de Calidad

| Métrica | Objetivo | Medición |
|---|---|---|
| Cobertura de código (unitarios) | > 80% | `pytest --cov` |
| Tests que pasan sin servicios | 100% (unit + adversarial) | CI pipeline |
| Tests de integración OK (sistema sano) | 100% | Post-deploy smoke |
| Tiempo de ejecución (unit + adversarial) | < 30 segundos | `pytest --durations=10` |
| Falsos positivos en adversariales | 0 | Revisión manual |
