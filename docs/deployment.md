# Guía de Despliegue — Everywhere Travel Sistema Multiagente

## Requisitos del sistema

| Requisito | Mínimo | Recomendado |
|---|---|---|
| RAM | 8 GB (Ollama + modelo 8B) | 16 GB |
| CPU | 4 cores | 8 cores |
| Disco | 15 GB libre (incluye modelos Ollama) | 30 GB libre |
| Docker | 24.0+ | última versión |
| Docker Compose | 2.20+ | última versión |
| Ollama | Requerido en el host, con `qwen3:8b` y `nomic-embed-text` descargados | — |

> El sistema usa **Ollama local** como proveedor LLM por defecto (`LLM_PROVIDER=ollama`), no Anthropic.
> `ANTHROPIC_API_KEY` es opcional y solo se usa si cambias `LLM_PROVIDER=anthropic` explícitamente.

---

## Paso 1: Preparación del entorno

```bash
# Verificar Docker
docker --version
docker compose version

# Instalar y preparar Ollama en el host (no corre dentro de docker compose)
# https://ollama.com/download
ollama pull qwen3:8b
ollama pull nomic-embed-text
ollama serve   # si no está corriendo ya como servicio

# Clonar el repositorio
git clone <url-repositorio>
cd sistema-everywheretravel

# Configurar variables de entorno
cp .env.example .env
```

Editar `.env` con tu editor favorito:
```bash
# Windows PowerShell
notepad .env

# Linux/Mac
nano .env
```

Contenido mínimo requerido:
```
LLM_PROVIDER=ollama
LLM_MODEL=ollama/qwen3:8b
OLLAMA_DOCKER_BASE_URL=http://host.docker.internal:11434   # así los contenedores alcanzan Ollama del host
SECRET_KEY=tu-clave-secreta-aqui      # ← REEMPLAZAR en producción
```

> Si en vez de Ollama prefieres un proveedor de pago, cambia `LLM_PROVIDER=anthropic` y define
> `ANTHROPIC_API_KEY=sk-ant-...`; el código de fallback está declarado pero no se activa salvo que
> configures explícitamente este proveedor.

---

## Paso 2: Construcción y arranque

```bash
# Construir imágenes y levantar todos los servicios
docker compose up --build -d

# Ver logs en tiempo real (todos los servicios)
docker compose logs -f

# Ver logs de un servicio específico
docker compose logs -f api
docker compose logs -f orchestrator
docker compose logs -f monitoring_worker
```

**Tiempo estimado de arranque:** 2-4 minutos (primera vez, descarga imágenes).

---

## Paso 3: Verificación de servicios

```bash
# 1. Estado de todos los contenedores
docker compose ps

# Todos deben estar en estado "running":
# et_postgres       ✓
# et_redis          ✓
# et_rabbitmq       ✓
# et_minio          ✓
# et_api            ✓
# et_orchestrator   ✓
# et_sales          ✓
# et_quotation      ✓
# et_document       ✓ (×3 réplicas)
# et_monitoring     ✓
# et_prometheus     ✓
# et_grafana        ✓
# et_frontend       ✓
```

```bash
# 2. Health check de la API
curl http://localhost:8000/health
# Esperado: { "status": "healthy", "service": "everywheretravel-api" }

# 3. Health check de los agentes (desde API)
curl http://localhost:8000/api/v1/monitoring/health
# Esperado: { "healthy_count": 9, "total_agents": 9, ... }

# 4. RabbitMQ Management UI
open http://localhost:15672
# Usuario: etrabbit | Contraseña: etrabbitpass
# Verificar: exchanges y queues creados (Queues tab → 9 queues)

# 5. Dashboard web
open http://localhost:3000
```

---

## Paso 4: Autenticación y primer uso

```bash
# Obtener token JWT
curl -X POST http://localhost:8000/api/v1/auth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=admin1234"

# Respuesta:
# { "access_token": "eyJ...", "token_type": "bearer", "role": "admin" }
```

```bash
# Usar el token en requests siguientes
TOKEN="eyJ..."

# Crear un cliente
curl -X POST http://localhost:8000/api/v1/clients \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"full_name": "María García", "email": "maria@test.com"}'
```

---

## Paso 5: Demo end-to-end

```bash
# Instalar dependencias del script demo (en host)
pip install httpx rich

# Ejecutar todos los escenarios
python scripts/demo_flow.py

# Solo escenario específico
python scripts/demo_flow.py --scenario A

# Escenario B con 5 consultas simultáneas
python scripts/demo_flow.py --scenario B --concurrent 5
```

---

## Paso 6: Ejecutar tests

```bash
# Instalar dependencias de test en host (opcional, también funciona en contenedor)
pip install pytest pytest-asyncio httpx

# Tests unitarios (no requieren servicios)
pytest tests/unit/ -v --tb=short

# Tests adversariales (no requieren servicios)
pytest tests/adversarial/ -v --tb=short

# Tests de integración (requieren docker compose up)
pytest tests/integration/ -v -m integration

# Todos los tests
pytest tests/ -v

# Con reporte de cobertura HTML
pytest tests/unit/ tests/adversarial/ --cov=core --cov=agents --cov-report=html
open htmlcov/index.html
```

---

## Paso 7: Observabilidad

### Prometheus — Métricas del sistema

```
http://localhost:9090
```

Queries útiles:
```promql
# Latencia p95 del endpoint de inquiries
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket{handler="/api/v1/inquiries"}[5m]))

# Mensajes procesados por agente en los últimos 5 minutos
rate(et_agent_messages_total[5m])

# Circuit breakers abiertos
et_circuit_breaker_state == 2

# Token usage acumulado
et_llm_tokens_total
```

### Grafana — Dashboard visual

```
http://localhost:3001
Usuario: admin
Contraseña: etgrafana
```

El datasource de Prometheus y el dashboard "Everywhere Travel — Overview" (sagas activas,
DLQ, circuit breakers, latencia LLM p95, errores por agente) se provisionan
automáticamente al arrancar (`infrastructure/grafana/datasources/`,
`infrastructure/grafana/dashboards/`) — no requiere configuración manual.

### Alertas Prometheus

Reglas en `infrastructure/prometheus/rules/alerts.yml` (circuit breaker abierto, DLQ > 10,
tasa de errores alta, sagas estancadas, latencia LLM p95 > 20s, API caída). Visibles en
`http://localhost:9090/alerts`. **No hay Alertmanager desplegado** — las alertas se
evalúan y muestran en la UI de Prometheus pero no se enrutan a Slack/email todavía (requiere
credenciales de notificación que este proyecto académico no tiene configuradas).

### RabbitMQ Management

```
http://localhost:15672
Usuario: etrabbit
Contraseña: etrabbitpass
```

Métricas importantes:
- **Queues → document-jobs**: profundidad indica backlog de PDFs pendientes
- **Queues → dead-letter-queue**: mensajes fallidos a investigar
- **Overview → Messages rates**: throughput del sistema

### MinIO Console

```
http://localhost:9001
Usuario: etminio
Contraseña: etminiopass
```

Bucket `everywheretravel-docs`: documentos PDF generados.

---

## Paso 8: Detener el sistema

```bash
# Detener sin eliminar datos
docker compose stop

# Detener y eliminar contenedores (datos preservados en volumes)
docker compose down

# Detener, eliminar contenedores Y datos (reset completo)
docker compose down -v
```

---

## Entornos

| Entorno | Existe | Configuración | Diferencias clave |
|---|---|---|---|
| **Desarrollo** | Sí (el descrito en esta guía) | `.env` (desde `.env.example`), `docker compose up`, `Dockerfile.api` con `--reload` y código montado como volumen | Logs legibles con color (ConsoleRenderer de structlog), CORS a `localhost:3000`, `SECRET_KEY` de desarrollo, cookie JWT sin flag `secure` |
| **Producción** | Definido pero no desplegado (no hay servidor productivo para este proyecto académico) | `.env.production` + `Dockerfile.prod` (multi-stage, sin reload, healthcheck HTTP), `ENVIRONMENT=production` | Al activar `ENVIRONMENT=production`: logs en JSON (para log shipper), cookie JWT con `secure=true`; exige rotar `SECRET_KEY` y credenciales de Postgres/Redis/RabbitMQ/MinIO (los valores por defecto son de desarrollo) |
| **Staging** | No existe | — | Decisión de alcance: con un solo evaluador/operador no aporta valor frente a su costo; el equivalente funcional es correr `scripts/demo_flow.py` completo contra el stack local antes de cualquier release |

La variable `ENVIRONMENT` (`api/config.py`) es el interruptor único entre comportamientos
de desarrollo y producción — no hay ramas de código separadas por entorno.

---

## Estrategias de Release

El proyecto no tiene todavía un pipeline de despliegue continuo a un entorno de
producción real (ver [ADR-002](adr/ADR-002-ollama-vs-anthropic.md) y el resto de ADRs —
es un despliegue académico auto-alojado vía `docker compose`), pero la estrategia
prevista para cuando exista un entorno de producción es:

| Estrategia | Aplicación en este sistema |
|---|---|
| **Rolling update por agente** | Cada agente es un contenedor independiente (`docker-compose.yml`) — se puede actualizar `sales_worker` sin tocar `quotation_worker`. RabbitMQ retiene los mensajes mientras el contenedor se reinicia, así que un rolling restart agente-por-agente no pierde mensajes en tránsito. |
| **Réplicas para servicios sin estado** | `document_worker` ya corre en 3 réplicas (`docker-compose.yml`) — el patrón se replica a cualquier agente si el volumen lo exige, sin cambios de código (los agentes son *stateless* entre mensajes; el estado vive en Redis/Postgres). |
| **Migraciones de esquema** | `api/database.py::ensure_schema_compatibility()` aplica cambios idempotentes (`ADD COLUMN IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`) en cada arranque — compatible con rolling updates porque una versión N+1 de la API puede arrancar mientras trabajadores en versión N siguen corriendo (los campos nuevos son siempre opcionales/con default). |
| **Feature flags ya usadas como mecanismo de release gradual** | `ENABLE_INLINE_QUOTATION_PIPELINE` y `ENABLE_LLM_ITINERARY` (`.env.example`) permiten activar código nuevo (pipeline Swarms inline, generación de itinerario vía LLM) sin desplegar una versión distinta — el mismo patrón se usaría para cualquier feature de alto riesgo antes de activarla por defecto. |
| **Blue-green / canary** | No implementado — requeriría un balanceador delante de la API (hoy expuesta directo en `:8000`) y un segundo stack completo. Queda como trabajo futuro si el volumen de tráfico lo justifica; con el volumen actual (proyecto académico) el rolling update por contenedor es suficiente. |

**Versionado:** `docker-compose.yml` no fija tags de imagen propios (usa `build: context: .`)
— el versionado real es el historial de Git (`git tag` por release). Un pipeline de CI/CD
real (extensión de `.github/workflows/ci.yml`) construiría y etiquetaría imágenes
(`everywheretravel-api:v1.2.0`) en cada tag, no implementado todavía porque no hay un
registro de contenedores (Docker Hub/GHCR) configurado para este proyecto académico.

## Escalado y FinOps

**Escalado horizontal ya presente:** `document_worker` corre en 3 réplicas
(`docker-compose.yml`) porque la generación de PDF (WeasyPrint/xhtml2pdf) es la operación
más costosa en CPU del sistema — el resto de agentes corren en 1 réplica porque su carga
es predominantemente I/O-bound (esperando RabbitMQ/Postgres/Ollama), donde escalar
réplicas ayuda menos que escalar el recurso compartido (Ollama, Postgres).

**Cuellos de botella conocidos ante escalado:**
| Recurso | Límite | Mitigación si el volumen crece |
|---|---|---|
| Ollama (LLM local) | Un solo proceso, sin balanceo | Sería el primer cuello de botella real — la extensión natural es un pool de instancias Ollama detrás de un balanceador, o migrar a `LLM_PROVIDER=anthropic` (ver [ADR-002](adr/ADR-002-ollama-vs-anthropic.md)) donde el proveedor absorbe el escalado a cambio de costo por token |
| PostgreSQL | Instancia única | Réplicas de lectura para `packages`/`destination_knowledge` (RAG es solo lectura intensiva) antes de necesitar sharding |
| RabbitMQ | Instancia única | Clustering nativo de RabbitMQ si el throughput de mensajes lo exige — no necesario al volumen actual |

**FinOps:** con Ollama local el costo marginal por LLM es US$0 (ver
[ADR-002](adr/ADR-002-ollama-vs-anthropic.md) y el cálculo de ROI en
[docs/roi.md](roi.md)) — el costo de operación es esencialmente el de la infraestructura
(cómputo + almacenamiento), no de tokens. Si el proyecto migrara a un proveedor de pago,
`et_llm_tokens_total` (Prometheus, ya instrumentado) sería la métrica base para proyectar
costo mensual: `costo ≈ tokens_total × precio_por_token_del_proveedor`, agrupable por
`agent_id` para saber qué agente concentra el gasto.

---

## Procedimiento ante Incidentes (Runbook)

### Niveles de severidad

| Severidad | Ejemplo | Respuesta esperada |
|---|---|---|
| **Crítica** | `CircuitBreakerOpen`, `APIDown` (ver `infrastructure/prometheus/rules/alerts.yml`) | Revisar de inmediato — el sistema no puede vender/reservar |
| **Alta** | `HighAgentErrorRate`, `DeadLetterQueueGrowing` | Revisar en el día — degradación parcial, el sistema sigue operando con fallbacks |
| **Media** | `LLMCallLatencyHigh`, `SagasStuckRunning` | Revisar en la semana — impacto en experiencia, no en integridad de datos |

### Camino de escalación

1. **Alerta Prometheus dispara** (`http://localhost:9090/alerts`) → visible también en el
   dashboard de Grafana.
2. **Auto-recuperación primero:** `MonitoringAgent` ya reintenta automáticamente (circuit
   breaker HALF_OPEN, requeue de dead-letter con backoff exponencial) — la mayoría de
   incidentes de severidad Alta/Media se resuelven solos en minutos.
3. **Si la auto-recuperación falla 3 veces:** `MonitoringAgent._escalate_to_human()`
   publica `REQUIRES_MANUAL_INTERVENTION` a `system:alerts` (Redis pub/sub) → WebSocket →
   dashboard. Esto es lo que un operador humano debe monitorear activamente.
4. **Intervención manual:** el operador consulta `agent_interaction_logs` /
   `validation_logs` / `sagas` (todas inmutables/auditables) para diagnosticar la causa
   raíz antes de actuar directamente sobre los datos.

### Diagnóstico técnico (por síntoma)

### Agente no aparece como HEALTHY

```bash
# Verificar logs del agente específico
docker compose logs sales_worker --tail=50

# Verificar que Redis está accesible
docker compose exec redis redis-cli -a etredispass ping
# Esperado: PONG

# Verificar que RabbitMQ está listo
docker compose exec rabbitmq rabbitmq-diagnostics ping
```

### API no responde

```bash
# Ver logs de la API
docker compose logs api --tail=100

# Verificar que PostgreSQL está listo
docker compose exec postgres pg_isready -U etuser -d everywheretravel

# Reiniciar solo la API
docker compose restart api
```

### Dead-letter queue con mensajes

```bash
# Ver mensajes en DLQ desde RabbitMQ UI
# → http://localhost:15672 → Queues → dead-letter-queue → Get messages

# El Monitoring Agent reencola automáticamente cada 120s
# Si después de 3 reintentos sigue fallando, revisar logs del agente destino
```

### Base de datos vacía tras reinicio

```bash
# Los datos están en el volume postgres_data (persistente)
# Si se usó "docker compose down -v", los datos se eliminaron

# Verificar volúmenes
docker volume ls | grep everywheretravel

# Ver paquetes en DB
docker compose exec postgres psql -U etuser -d everywheretravel \
  -c "SELECT name, destination, base_price FROM packages;"
```

### Ollama no responde / agentes LLM fallan

```bash
# Verificar que Ollama está corriendo en el host
curl http://localhost:11434/api/tags

# Verificar que los contenedores lo alcanzan (usan host.docker.internal)
docker compose exec sales_worker curl http://host.docker.internal:11434/api/tags

# Si Ollama no responde, los agentes que usan LLM caen a su fallback determinístico
# (sin LLM) — ver *_fallback_* en cada agents/<nombre>/agent.py.
# El sistema sigue funcionando para operaciones sin LLM (reservas, liquidaciones).
```

---

## Variables de Entorno — Referencia completa

| Variable | Descripción | Valor por defecto |
|---|---|---|
| `LLM_PROVIDER` | Proveedor LLM activo (`ollama` o `anthropic`) | `ollama` |
| `LLM_MODEL` | Modelo usado por los agentes | `ollama/qwen3:8b` |
| `OLLAMA_DOCKER_BASE_URL` | URL de Ollama alcanzable desde los contenedores | `http://host.docker.internal:11434` |
| `ANTHROPIC_API_KEY` | Clave API de Anthropic (solo si `LLM_PROVIDER=anthropic`) | (no requerido por defecto) |
| `DATABASE_URL` | URL de PostgreSQL async | `postgresql+asyncpg://etuser:etpassword@postgres:5432/everywheretravel` |
| `REDIS_URL` | URL de Redis con auth | `redis://:etredispass@redis:6379/0` |
| `RABBITMQ_URL` | URL AMQP de RabbitMQ | `amqp://etrabbit:etrabbitpass@rabbitmq:5672/everywheretravel` |
| `MINIO_ENDPOINT` | Host:puerto de MinIO | `minio:9000` |
| `MINIO_ACCESS_KEY` | Access key de MinIO | `etminio` |
| `MINIO_SECRET_KEY` | Secret key de MinIO | `etminiopass` |
| `SECRET_KEY` | Clave JWT para tokens | `supersecretkey` |
| `ENVIRONMENT` | `development` o `production` | `development` |
| `DB_API_URL` | URL interna de la API (para agentes) | `http://api:8000` |

---

## Arquitectura de puertos

| Servicio | Puerto externo | Puerto interno | Protocolo |
|---|---|---|---|
| API Gateway | 8000 | 8000 | HTTP/WebSocket |
| Frontend Next.js | 3000 | 3000 | HTTP |
| PostgreSQL | 5432 | 5432 | TCP |
| Redis | 6379 | 6379 | TCP |
| RabbitMQ AMQP | 5672 | 5672 | AMQP |
| RabbitMQ Mgmt | 15672 | 15672 | HTTP |
| MinIO API | 9000 | 9000 | HTTP/S3 |
| MinIO Console | 9001 | 9001 | HTTP |
| Prometheus | 9090 | 9090 | HTTP |
| Grafana | 3001 | 3000 | HTTP |
