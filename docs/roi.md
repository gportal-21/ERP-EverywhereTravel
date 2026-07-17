# Medición de Éxito y ROI — Everywhere Travel

> Nota metodológica: Everywhere Travel es una agencia ficticia para efectos del proyecto
> académico. Las cifras de esta sección son **estimaciones ilustrativas** basadas en
> supuestos explícitos (marcados como tal), no datos reales de negocio — el objetivo es
> demostrar la metodología de cálculo de ROI para un sistema de agentes de IA, aplicable
> directamente el día que existan datos reales de la operación.

## 7.1 KPIs de negocio

| KPI | Línea base (manual) | Objetivo con el sistema |
|---|---|---|
| Tiempo de cotización | 2-4 horas (agente humano busca precios, arma Excel) | < 30s (catálogo) / minutos (personalizado con LLM) |
| Errores de doble reserva | Ocurrencia no cuantificada, dependiente de coordinación manual entre sedes | 0 (optimistic locking, ver [ADR-004](adr/ADR-004-optimistic-locking-redis.md)) |
| Tiempo de emisión de documentos | Manual en Word, minutos-horas según carga | Automático, segundos (cola async, `DocumentAgent` ×3 réplicas) |
| Errores de cálculo financiero (redondeo) | Riesgo real con fórmulas de Excel | 0 (aritmética `Decimal`, ver [ADR-006](adr/ADR-006-decimal-en-finanzas.md)) |
| Disponibilidad ante fallo parcial | Un agente de ventas ausente detiene el proceso | Circuit breaker + dead-letter + escalación humana automática |

## 7.2 Línea base (pre-IA)

Supuesto de partida (agencia con múltiples sedes, según `docs/architecture.md`): un agente
de ventas dedica 2-4 horas a armar una cotización de paquete personalizado (buscar
disponibilidad, calcular precio con margen e IGV a mano, redactar itinerario). Con el
sistema, esa misma tarea se resuelve en segundos para paquetes de catálogo y en minutos
para paquetes personalizados (limitado por la latencia del LLM local, ver
`et_llm_call_duration_seconds`).

## 7.3 Cálculo de ROI

Todas las cifras en **soles (S/)**. Estimaciones ilustrativas con supuestos explícitos, no
datos reales de la operación; el objetivo es demostrar la metodología de cálculo.

### Supuestos del modelo (caso base)

| Parámetro | Valor | Justificación |
|---|---|---|
| Costo laboral cargado del vendedor | S/ 20 / hora | Sueldo base + beneficios sociales peruanos (~45%: EsSalud, CTS, gratificaciones, vacaciones) |
| Volumen de cotizaciones | 200 / mes (~50 / semana) | Agencia con varias sedes |
| Mix catálogo / personalizado | 60% / 40% | Los personalizados son los más costosos de armar a mano |
| Tiempo manual (AS-IS) | Catálogo 1.0 h · Personalizado 3.0 h | Rango observado 2-4 h para personalizados |
| Tiempo con el sistema (TO-BE) | Catálogo ~5 min · Personalizado ~20 min | Incluye la revisión humana del resultado |
| Ahorro por cotización | Catálogo 0.92 h · Personalizado 2.67 h | Diferencia AS-IS − TO-BE |
| Dobles reservas evitadas | 2 / mes × S/ 300 | Reacomodo, pérdida de margen y goodwill por incidente |

### Costos del proyecto

**Inversión inicial (una sola vez)** — desarrollo valorizado a precio de mercado (en el
proyecto académico no se factura, pero se incluye para un ROI realista):

| Concepto | Cálculo | Monto |
|---|---|---|
| Desarrollo del sistema (una vez) | 1 desarrollador × 3 meses × S/ 6,000/mes | **S/ 18,000** |

**Costos recurrentes (mensuales):**

| Concepto | Cálculo | Monto / mes |
|---|---|---|
| Infraestructura (VPS gama media con RAM para Ollama) | Alquiler mensual del servidor | S/ 300 |
| LLM (Ollama local, qwen3:8b) | Costo por token | S/ 0 |
| Mantenimiento (monitoreo, actualizaciones) | 6 h/mes × S/ 40/h | S/ 240 |
| **Total recurrente** | | **S/ 540** |

### Beneficios cuantificables

| Beneficio | Cálculo (mensual) | Monto / mes |
|---|---|---|
| Ahorro laboral — cotizaciones de catálogo | 120 × 0.92 h × S/ 20 | S/ 2,208 |
| Ahorro laboral — cotizaciones personalizadas | 80 × 2.67 h × S/ 20 | S/ 4,272 |
| Doble reserva evitada | 2 × S/ 300 | S/ 600 |
| **Beneficio bruto** | | **S/ 7,080** |

No se monetizan otros beneficios reales pero difíciles de cuantificar (eliminación de
errores de cálculo con Decimal exacto, reducción de reprocesos por versiones, documentos
sin errores de tipeo), por lo que el ROI calculado es conservador.

### Fórmula de ROI y cálculo (caso base)

```
ROI = (Beneficio neto acumulado − Costo total) / Costo total × 100

Beneficio neto mensual  = 7,080 − 540               = S/ 6,540 / mes
Payback (recuperación)  = 18,000 / 6,540            ≈ 2.8 meses

Horizonte 12 meses:
  Beneficio bruto anual = 7,080 × 12                = S/ 84,960
  Costo total año 1     = 18,000 + (540 × 12)       = S/ 24,480
  Beneficio neto anual  = 84,960 − 24,480           = S/ 60,480
  ROI (12 meses)        = 60,480 / 24,480 × 100     ≈ 247%
```

### Análisis de sensibilidad

| Escenario | Supuestos | Beneficio neto/mes | Payback | ROI 12 meses |
|---|---|---|---|---|
| Conservador | 120 cot/mes · S/ 18/h · 1 doble reserva | S/ 3,259 | ~5.5 meses | ~86% |
| Base | 200 cot/mes · S/ 20/h · 2 dobles reservas | S/ 6,540 | ~2.8 meses | ~247% |
| Optimista | 320 cot/mes · S/ 22/h · 3 dobles reservas | S/ 11,765 | ~1.5 meses | ~503% |

Incluso en el escenario conservador el proyecto se recupera en menos de 7 meses y arroja un
ROI positivo en el primer año; el caso base recupera la inversión en menos de 3 meses.

## 7.4 Tablero de éxito (técnico + negocio)

| Dimensión | Métrica | Dónde se mide |
|---|---|---|
| Técnico | Latencia p95 por endpoint, tasa de error por agente, estado de circuit breakers | Grafana "Everywhere Travel — Overview" (`infrastructure/grafana/dashboards/overview.json`) |
| Técnico | % golden set que pasa | `scripts/run_evaluation.py` (CI en cada PR) |
| Negocio | Tiempo promedio de cotización a VALIDATED | `sagas` (timestamp `created_at` → paso `validation_complete`) |
| Negocio | Tasa de sagas que llegan a COMPLETED sin intervención manual | `sagas.status`, agrupado |
| Negocio | Tasa de escalación a humano (HITL) | `ConflictResolved.needs_escalation` vía `agent_interaction_logs` / logs de `MonitoringAgent` |

## 7.5 Cadencia de revisión

- **Diaria (automática):** alertas Prometheus (`infrastructure/prometheus/rules/alerts.yml`) — circuit breakers, DLQ, latencia LLM.
- **Semanal:** revisión del dashboard de Grafana y de `agent_interaction_logs` para detectar degradación de calidad del LLM (tasa de fallback determinístico en aumento).
- **Por release/PR:** golden set en CI (`.github/workflows/ci.yml`) — ningún cambio se mergea si el golden set falla.
- **Mensual (si hay datos reales de negocio):** recalcular el ROI de la sección 7.3 con cifras reales de volumen de cotizaciones y tiempo ahorrado medido, no estimado.
