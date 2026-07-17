# ADR-012 — Agentes especializados de flujo fijo en vez de patrón Deep Agent

**Estado:** Aceptado

## Contexto

El patrón "Deep Agent" (popularizado por `deepagents` de LangChain) consiste en un
**agente planificador** que descompone una tarea abierta y de largo horizonte en pasos
dinámicos, usando una lista de tareas (todo list) como memoria de planificación, un
sistema de archivos virtual como scratchpad, y la capacidad de invocar sub-agentes
especializados *ad hoc* según lo que el planificador decida en tiempo de ejecución. Es el
patrón correcto para tareas como "investiga X y escribe un informe" donde ni el número de
pasos ni su orden se conocen de antemano.

Everywhere Travel, en cambio, tiene **procesos de negocio fijos y conocidos**: una
cotización siempre pasa por Sales → Quotation → Validation; una reserva siempre pasa por
Reservation → Finance → Document. El orden de los pasos no lo decide un LLM en tiempo de
ejecución — lo decide el analista de negocio que definió el proceso, y debe ser 100%
predecible y auditable (compliance regulatorio, IGV).

## Decisión

Usar **9 agentes especializados con responsabilidad fija** (`agents/*/agent.py`)
coordinados por un flujo de Saga explícito (ver [ADR-001](ADR-001-saga-vs-langgraph.md)),
en vez de un único Deep Agent que planifique dinámicamente qué agente invocar y en qué
orden.

## Alternativas consideradas

| Alternativa | Por qué no |
|---|---|
| Deep Agent (planificador + sub-agentes dinámicos) | El *valor* del patrón Deep Agent es manejar incertidumbre sobre qué pasos son necesarios — aquí no hay esa incertidumbre: los pasos de una cotización o una reserva están definidos por reglas de negocio y compliance, no por lo que un LLM "decida explorar". Dejar que un planificador decida dinámicamente el orden de validación de una cotización sería introducir no-determinismo exactamente donde el sistema necesita lo contrario. |
| Deep Agent solo para el flujo de paquete personalizado (el más "abierto" del sistema) | Se evaluó, pero incluso ahí el espacio de decisión es acotado (elegir componentes de un catálogo fijo de tipos: vuelo/hotel/traslado/guía) — ya cubierto por `_tool_estimate_component_price` dentro de `QuotationAgent` sin necesitar un planificador de propósito general. |

## Consecuencias

**Positivas:**
- Cada paso del proceso de negocio es rastreable 1:1 a un agente y un archivo de código concreto — auditable por diseño, requisito no negociable para compliance (IGV, registros contables inmutables).
- El comportamiento del sistema ante una misma entrada es predecible; un Deep Agent podría explorar rutas distintas entre corridas para la misma tarea.

**Negativas / trade-offs aceptados:**
- El sistema no puede manejar tareas verdaderamente abiertas ("arma el mejor viaje posible dado este presupuesto y estas 10 restricciones vagas") sin que un desarrollador añada explícitamente la lógica/tool correspondiente — no hay planificación emergente. Se acepta porque no es un caso de uso real de la agencia; si apareciera, el punto de extensión natural sería añadir un Deep Agent **acotado** dentro de `QuotationAgent` para el sub-problema de armar paquetes verdaderamente custom, sin tocar el resto del flujo determinista.
