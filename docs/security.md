# Seguridad y Privacidad — Everywhere Travel

Estado real del sistema, sin maquillar lo que falta — el objetivo de esta sección es que
un evaluador pueda ver exactamente qué está mitigado y qué queda como riesgo conocido.

## Autenticación y autorización

- JWT (`HS256`, `PyJWT`) emitido en `POST /api/v1/auth/token`, expira a las 8h.
- **Hallazgo corregido en esta iteración:** el token se emitía pero **ningún endpoint lo
  verificaba** — `oauth2_scheme` estaba declarado pero nunca usado como dependencia. Toda
  la API era efectivamente anónima. Ahora `api/routes/auth.py::get_current_user` valida
  el JWT (Authorization header o cookie) y protege `clients`, `stats`, `itinerary`.
- **Routers sin protección de usuario (deliberado, no un olvido):** `packages`,
  `quotations`, `reservations`, `liquidations`, `sagas`, `documents`, `validation-logs`,
  `knowledge`, `agent-interactions`, `monitoring` reciben tráfico interno de los propios
  agentes (llamadas `httpx` sin JWT de usuario — ver `agents/*/agent.py`). Protegerlos con
  `get_current_user` rompería la comunicación entre agentes. **Pendiente:** una estrategia
  de auth servicio-a-servicio (API key interna compartida entre `api` y los workers, o
  aislar estas rutas bajo un prefijo `/internal/` solo alcanzable dentro de la red Docker)
  antes de exponer este sistema fuera de una red de confianza.
- Cookie httpOnly añadida en el login como defensa adicional contra robo de token vía XSS,
  pero el frontend actual sigue leyendo el token de `localStorage`
  (`frontend/lib/auth-store.ts`) y adjuntándolo como `Authorization: Bearer` — la
  migración completa a "cookie-only" (sin token accesible desde JS) queda pendiente y
  requeriría cambiar `frontend/lib/fetch-api.ts::authHeaders()`, el hidratado de sesión
  (`auth-store.ts::hydrate()`, que hoy depende de leer `localStorage`), y añadir
  `credentials: "include"` a cada `fetch`.
- Passwords con `bcrypt` (vía `passlib[bcrypt]`), nunca en texto plano.
- Roles (`users.role`) existen en el modelo pero **no hay autorización por rol** en
  ninguna ruta todavía — cualquier usuario autenticado puede operar cualquier endpoint
  protegido, sin distinción admin/sales_agent.

## Gestión de secretos

- `.env.example` documenta variables sin valores reales (correcto). `.env` / `.env.production`
  existen localmente con secretos reales — **no están en el repositorio** (verificar
  `.gitignore` antes de cualquier commit que incluya archivos nuevos).
- `SECRET_KEY` (firma JWT) tiene un valor por defecto (`supersecretkey`) en `api/config.py`
  — aceptable para desarrollo, **debe rotarse obligatoriamente en cualquier despliegue real**.
- No hay vault/secrets manager (AWS Secrets Manager, Vault, etc.) — los secretos viven en
  variables de entorno planas. Aceptable para el alcance académico; sería el primer punto
  a resolver antes de producción real con datos de clientes reales.

## Validación de entradas

- Doble capa: Pydantic (`core/mcp/envelope.py`) + JSON Schema Draft-07
  (`core/mcp/validator.py`) en cada hop de mensaje inter-agente (ver
  [ADR-008](adr/ADR-008-doble-validacion-schema.md)).
- `MCPEnvelope.validate_agents()` rechaza `sender_agent`/`receiver_agent` fuera de la
  lista blanca de 10 agentes válidos — previene inyección de mensajes desde un "agente"
  falso.
- Tests adversariales cubren payload vacío/gigante, SQL injection (mitigado por
  SQLAlchemy con queries parametrizadas + JSONB), `retry_count` fuera de rango,
  presupuesto negativo (`tests/adversarial/test_adversarial.py`).

## Prompt injection (riesgo no mitigado — documentado, no implementado)

Las consultas del cliente (`PackageInquiry.preferences`, texto libre) se interpolan
directamente en el prompt de `SalesAgent` sin sanitización (ver
`_build_package_request_swarms`). Un cliente podría en teoría incluir texto tipo
*"ignora las instrucciones anteriores y..."* en sus preferencias. El impacto está acotado
porque:
1. La salida del LLM está forzada a un JSON Schema (`PackageRequest`) — un intento de
   inyección no puede hacer que el LLM ejecute código ni acceda a datos fuera de su
   contrato de salida.
2. `SalesAgent` nunca calcula precios ni crea reservas — un `PackageRequest` manipulado
   en el peor caso produce una cotización incorrecta, que **debe** pasar por
   `ValidationAgent` (reglas deterministas R001-R012) antes de ser usable.

No hay, sin embargo, un filtro explícito de detección de intentos de inyección — sería la
siguiente mejora de seguridad si el sistema recibiera input de clientes finales
directamente (hoy `PackageInquiry` lo genera personal interno vía dashboard, no el
cliente final).

## CORS

`allow_methods`/`allow_headers` explícitos (antes `["*"]`/`["*"]`), `allow_origins`
restringido por `CORS_ORIGINS` env var.

## Privacidad de datos (PII)

- `clients.preferences` y `clients.document_number` son PII — viven en PostgreSQL sin
  cifrado a nivel de columna (solo cifrado en tránsito si se configura TLS en el
  despliegue real, no incluido en el docker-compose de desarrollo).
- No hay política de retención/purga de datos de clientes ni mecanismo de "derecho al
  olvido" — fuera de alcance del proyecto académico, pero sería requisito real bajo
  normativa de protección de datos si se operara con clientes reales en Perú (Ley N.º 29733).
- Los prompts enviados al LLM (incluyendo `client_id`, destino, presupuesto) se procesan
  **localmente vía Ollama** — no salen a un proveedor externo por defecto (ver
  [ADR-002](adr/ADR-002-ollama-vs-anthropic.md)), lo cual es también una ventaja de
  privacidad, no solo de costo.

## Auditoría

- `validation_logs` inmutable (sin UPDATE/DELETE, ver [ADR-007](adr/ADR-007-audit-log-inmutable.md)).
- `agent_interaction_logs` registra cada interacción LLM (útil también como rastro de
  auditoría de qué datos del cliente vio el modelo y cuándo).
