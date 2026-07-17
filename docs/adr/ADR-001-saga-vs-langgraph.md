# ADR-001 — Orquestación Saga + Event Bus en vez de LangGraph

**Estado:** Aceptado

## Contexto

El sistema necesita coordinar 9 agentes especializados (Sales, Quotation, Reservation,
Finance, Document, Validation, Monitoring, Notification, Itinerary) a través de flujos de
negocio de larga duración (una cotización puede tardar segundos; una reserva con
liquidación y documentos, minutos) que deben sobrevivir al reinicio de cualquier agente
individual y permitir compensación ante fallos parciales.

LangGraph es el framework de referencia para orquestación de agentes con estado
explícito (grafo de nodos y aristas condicionales, checkpointing), pero está diseñado
para un **único proceso** que mantiene el grafo en memoria (o un checkpointer compartido).
Nuestros agentes son **procesos/contenedores independientes** que ya necesitan comunicarse
por red de todas formas (para escalar Document Agent a 3 réplicas, por ejemplo).

## Decisión

Usar el **patrón Saga** (`core/saga_coordinator.py`) sobre un **event bus** (RabbitMQ,
topic exchange + dead-letter) como mecanismo de orquestación, en vez de LangGraph.

- Cada paso de una Saga se registra en Redis (hot) y se sincroniza a PostgreSQL (cold,
  audit trail permanente).
- Los agentes se comunican exclusivamente vía mensajes `MCPEnvelope` (contrato propio,
  ver `core/mcp/envelope.py`) enrutados por topic exchange — no hay llamadas RPC directas
  entre agentes.
- `MonitoringAgent` detecta sagas estancadas (>5 min sin progreso) y dispara compensación
  o escalación humana — el equivalente funcional al "resume desde checkpoint" de LangGraph,
  pero implementado sobre infraestructura de mensajería que de todas formas era necesaria.

## Alternativas consideradas

| Alternativa | Por qué no |
|---|---|
| LangGraph (StateGraph + checkpointer) | Asume orquestación centralizada en un proceso; forzar 9 agentes-contenedor independientes dentro de un único grafo requeriría o bien colapsarlos en un monolito (contradice el objetivo del curso de arquitectura multiagente real) o construir un checkpointer distribuido custom — reinventando el propio event bus que ya se necesita. |
| 2-Phase Commit | No escala con agentes que pueden estar caídos o degradados; bloquea recursos mientras dura la transacción. |
| Orquestación RPC directa (agente llama a agente por HTTP) | Acopla agentes entre sí, dificulta el reemplazo/escalado independiente de cada uno, y no da un log de auditoría de la transacción distribuida "gratis" como sí lo da el patrón Saga. |

## Consecuencias

**Positivas:**
- Cada agente escala independientemente (Document Agent corre en 3 réplicas sin tocar el resto).
- El log de pasos de la Saga (`sagas.steps` en PostgreSQL) es auditoría nativa — no requiere instrumentación adicional.
- Un agente caído no bloquea a los demás; RabbitMQ retiene los mensajes hasta que el agente vuelve.

**Negativas / trade-offs aceptados:**
- No hay una visualización de grafo "out of the box" como la de LangGraph/LangSmith — se compensa con los diagramas Mermaid de `docs/architecture.md` y el endpoint `/api/v1/sagas/{id}`.
- La lógica condicional de routing vive en `if/else` de Python (`ROUTING_TABLE`, `_handle_conflict`) en vez de aristas declarativas de un grafo — más difícil de visualizar estáticamente, pero más simple de razonar para un sistema con procesos verdaderamente distribuidos.
