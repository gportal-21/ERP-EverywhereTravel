# Guía de Despliegue — Everywhere Travel Sistema Multiagente

## Requisitos del sistema

| Requisito | Mínimo | Recomendado |
|---|---|---|
| RAM | 4 GB | 8 GB |
| CPU | 2 cores | 4 cores |
| Disco | 10 GB libre | 20 GB libre |
| Docker | 24.0+ | última versión |
| Docker Compose | 2.20+ | última versión |
| ANTHROPIC_API_KEY | Requerido | — |

---

## Paso 1: Preparación del entorno

```bash
# Verificar Docker
docker --version
docker compose version

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
ANTHROPIC_API_KEY=sk-ant-api03-...   # ← REEMPLAZAR
SECRET_KEY=tu-clave-secreta-aqui      # ← REEMPLAZAR en producción
```

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

## Troubleshooting

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

### ANTHROPIC_API_KEY no configurada

```bash
# Verificar que la variable está en .env
cat .env | grep ANTHROPIC

# Si la variable está vacía, los agentes que usan LLM fallarán
# El sistema sigue funcionando para operaciones sin LLM (reservas, liquidaciones)
```

---

## Variables de Entorno — Referencia completa

| Variable | Descripción | Valor por defecto |
|---|---|---|
| `ANTHROPIC_API_KEY` | Clave API de Anthropic | (requerido) |
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
