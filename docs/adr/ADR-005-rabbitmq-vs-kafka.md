# ADR-005 — RabbitMQ topic exchange en vez de Kafka

**Estado:** Aceptado

## Contexto
Se necesita un event bus para el enrutamiento de `MCPEnvelope` entre los 9 agentes, con
soporte de dead-letter queue, prioridad de mensajes y routing por patrón (`orchestrator.*`,
`quotation.*`, etc.).

## Decisión
RabbitMQ con topic exchange (`everywheretravel.events`) + dead-letter exchange.

## Alternativas consideradas
| Alternativa | Por qué no |
|---|---|
| Kafka | Pensado para streams de alto volumen con particionamiento y replay largo; el volumen de este sistema (mensajes de coordinación entre 9 agentes) no lo justifica, e introduce complejidad operacional (Zookeeper/KRaft, gestión de particiones) innecesaria para el caso de uso. |

## Consecuencias
- Routing por topic pattern (`*.route`, `quotation.*`) mapea naturalmente a los `payload_type` del contrato MCP.
- Dead-letter queue nativo simplifica la lógica de reintentos de `MonitoringAgent._dead_letter_loop()`.
- Costo: RabbitMQ no ofrece replay de mensajes ya consumidos como Kafka — la auditoría de largo plazo vive en PostgreSQL (`sagas`, `validation_logs`), no en el bus.
