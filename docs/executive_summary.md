# Resumen Ejecutivo — Everywhere Travel Sistema Multiagente

## 1.1 Problema

Everywhere Travel es una agencia de viajes con múltiples sedes que opera con hojas de
cálculo compartidas para cotizar paquetes, coordinar reservas entre sedes y liquidar
comisiones. Este modelo produce cotizaciones lentas (2-4 horas por consulta compleja),
riesgo de doble reserva por falta de coordinación en tiempo real, errores de redondeo en
cálculos financieros hechos a mano, y ausencia de un rastro de auditoría verificable para
compliance regulatorio (IGV).

## 1.2 Solución propuesta

Una plataforma interna de gestión operada por **9 agentes especializados**
(Orchestrator, Sales, Quotation, Reservation, Finance, Document, Validation, Monitoring,
Notification, más Itinerary) que colaboran a través de un contrato de mensajería explícito
(MCP Envelope) sobre un event bus (RabbitMQ), coordinados con el patrón Saga para
garantizar que ninguna transacción distribuida quede en estado inconsistente.

Un LLM local (Ollama, `qwen3:8b`) se usa **solo** donde hay ambigüedad de lenguaje
natural o generación creativa genuina (interpretar la consulta del cliente, estimar
paquetes personalizados, redactar itinerarios, evaluar conflictos operativos) — el resto
del sistema (compliance, aritmética financiera, locking, circuit breaking) es
deliberadamente determinístico, con las salidas del LLM forzadas a un schema JSON y
validadas con Pydantic antes de usarse en cualquier flujo de negocio (ver
[ADR-010](adr/ADR-010-salida-estructurada-forzada.md)).

## 1.3 Resultado esperado

- Cotización de paquetes de catálogo en menos de 30 segundos; paquetes personalizados en
  minutos, limitados por la latencia del LLM local.
- Cero doble reservas mediante locking optimista sobre Redis.
- Ledger financiero inmutable, auditable, con IGV y márgenes calculados en `Decimal`
  exacto.
- Continuidad operativa ante fallos parciales: un agente caído no bloquea al resto del
  sistema (circuit breaker, dead-letter queue, escalación automática a un humano cuando
  la confianza de una decisión del LLM cae por debajo de un umbral, ver `agents/orchestrator/agent.py::HUMAN_ESCALATION_CONFIDENCE_THRESHOLD`).
- Observabilidad real: métricas Prometheus con alertas activas, dashboard Grafana
  provisionado automáticamente, y una capa de evaluación local (golden set) que sustituye
  a LangSmith sin requerir cuenta externa (ver [ADR-011](adr/ADR-011-evaluacion-local-sin-langsmith.md)).

El detalle de cada decisión de arquitectura está en [docs/adr/](adr/README.md); el mapeo
completo del sistema, en [docs/architecture.md](architecture.md).
