# ADR-004 — Optimistic locking con Redis SETNX

**Estado:** Aceptado

## Contexto
`ReservationAgent` debe evitar doble reserva del mismo paquete/fecha cuando llegan
solicitudes concurrentes (Escenario B: cotizaciones simultáneas).

## Decisión
Usar `SETNX` de Redis (`lock:{type}:{id}`, TTL 30s) como lock optimista antes de insertar
la reserva en PostgreSQL, en vez de un lock a nivel de base de datos (`SELECT ... FOR UPDATE`).

## Alternativas consideradas
| Alternativa | Por qué no |
|---|---|
| Locks de PostgreSQL (`FOR UPDATE`) | Bloquea filas/tablas durante la transacción, compitiendo con el resto de la carga de la BD; Redis `SETNX` es O(1) y no toca el motor transaccional. |

## Consecuencias
- Si el proceso que toma el lock muere antes de liberarlo, el TTL de 30s garantiza que no quede huérfano indefinidamente.
- El lock es *advisory*: solo protege contra otros agentes que respeten el mismo protocolo — no es una restricción a nivel de esquema de BD. Se acepta porque `ReservationAgent` es el único escritor de `reservations`.
