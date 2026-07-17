# ADR-003 — Topología híbrida jerárquica-estrella

**Estado:** Aceptado

## Contexto
Con 9 agentes especializados, la topología de comunicación determina tanto la
trazabilidad de los flujos como el acoplamiento entre agentes.

## Decisión
Topología **híbrida**: el `OrchestratorAgent` centraliza el enrutamiento inicial y la
gestión de Sagas (jerárquica), pero dentro de cada dominio de negocio los agentes se
comunican directamente entre sí sin pasar por el Orchestrator en cada hop — p. ej.
`SalesAgent` → `QuotationAgent` → `ValidationAgent` (estrella interna por dominio).

## Alternativas consideradas
| Alternativa | Por qué no |
|---|---|
| Malla pura (cualquier agente habla con cualquiera) | Acoplamiento excesivo; imposible razonar sobre el flujo de una Saga sin rastrear 9×9 posibles rutas. |
| Estrella pura (todo pasa por el Orchestrator) | Cuello de botella único y punto de fallo central; cada hop de negocio duplicaría latencia innecesariamente. |

## Consecuencias
- El Orchestrator mantiene visibilidad completa de cada Saga sin ser un cuello de botella de tráfico.
- Los dominios (Ventas, Finanzas, Documentos) pueden evolucionar su comunicación interna sin tocar el Orchestrator.
- Costo: la lógica de "quién le habla a quién" vive repartida entre `ROUTING_TABLE` del Orchestrator y los `_register_handlers()` de cada agente — requiere `docs/agent_contracts.md` actualizado como fuente de verdad.
