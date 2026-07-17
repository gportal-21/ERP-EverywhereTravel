# Proceso de Negocio — Everywhere Travel (AS-IS vs TO-BE)

Descripción narrativa completa del proceso comercial de la agencia, desde que un cliente
hace su primera consulta hasta que la compra del paquete turístico queda cerrada y
liquidada. Se presenta en dos versiones:

- **AS-IS** — cómo operaba la agencia **de forma manual, antes** del ERP multiagente.
- **TO-BE** — cómo opera **ahora, con** el ERP multiagente.

> **Nota sobre las fuentes.** El **TO-BE está aterrizado sobre el código real** del sistema
> (agentes, saga, contratos MCP, ver `docs/architecture.md` y `docs/agent_contracts.md`).
> El **AS-IS es una reconstrucción** a partir de la tabla "Antes / Ahora" del README y de
> la práctica típica de una agencia de viajes peruana con varias sedes; los supuestos que
> no se derivan del sistema van marcados con **(supuesto)** para que puedas ajustarlos al
> caso real que evalúe tu profesor.

---

# PARTE 1 — AS-IS: Proceso manual (antes del ERP)

## Actores y herramientas

| Actor | Rol en el proceso |
|---|---|
| **Cliente** | Persona que quiere comprar un paquete turístico |
| **Vendedor** (agente de ventas de sede) | Atiende al cliente, cotiza a mano, negocia, arma la venta |
| **Jefe / Gerente de sede** | Aprueba cotizaciones de margen bajo o monto alto **(supuesto)** |
| **Área de Finanzas / Contabilidad** | Registra pagos, controla cuotas, calcula comisiones |
| **Coordinador de Operaciones** | Confirma disponibilidad con proveedores, coordina entre sedes |
| **Herramientas** | Teléfono / WhatsApp, hoja de cálculo Excel compartida, plantillas Word, correo electrónico, archivador físico |

## Narrativa del proceso manual

### Fase 1 — Recepción de la consulta
El cliente llega a una sede física o llama por teléfono/WhatsApp **(supuesto: canal mixto)**.
El **vendedor** lo atiende y toma nota, en un cuaderno o en un correo para sí mismo, de los
datos de la solicitud: destino deseado, fechas aproximadas, número de viajeros, presupuesto
estimado y preferencias sueltas ("hotel bueno", "que incluya vuelo", "algo tranquilo").
No hay un formato estándar: cada vendedor registra la consulta como puede, y con frecuencia
la información queda incompleta (falta una fecha, no se anotó el presupuesto máximo).

### Fase 2 — Búsqueda y armado de la cotización
El vendedor abre la **hoja de cálculo Excel compartida** entre sedes, donde están los
paquetes y precios base. Busca manualmente un paquete que se acerque al pedido. Si no hay
uno que calce, arma un paquete "a medida" sumando componentes (vuelo + hotel + traslados +
guía), copiando precios de otras hojas, correos de proveedores o de memoria.

Calcula a mano el precio final: suma los componentes, agrega el margen de la agencia y el
IGV (18%). Este cálculo se hace con fórmulas de Excel frágiles que se copian y pegan entre
celdas, y es donde **se cuelan errores de redondeo y de fórmula** con frecuencia.

Este paso puede tardar **entre 2 y 4 horas**, sobre todo para paquetes personalizados,
porque implica llamar a proveedores para confirmar precios y disponibilidad, y esperar sus
respuestas.

### Fase 3 — Aprobación interna
Si la cotización tiene un margen por debajo del mínimo de la política, o el monto es alto,
el vendedor debe conseguir la **aprobación del jefe/gerente de sede** antes de presentarla
**(supuesto)**. Esto se hace por correo o verbalmente. Si el gerente no está disponible, la
cotización **se queda detenida** hasta que aparezca. No hay registro formal de quién aprobó
qué ni cuándo.

### Fase 4 — Presentación al cliente y negociación
El vendedor copia el resultado a una **plantilla Word**, le da formato, y se la envía al
cliente por correo o WhatsApp. El cliente pregunta, pide cambios ("¿y si son 3 noches en
vez de 4?", "¿tienen algo más barato?"). Cada cambio obliga a **volver a la Fase 2**:
rehacer el cálculo, y muchas veces **reconseguir la aprobación** de la Fase 3. Se generan
varias versiones de la cotización, guardadas como archivos sueltos (`cotizacion_final.docx`,
`cotizacion_final_v2.docx`, `cotizacion_final_definitiva.docx`) **sin control de versiones
real**.

### Fase 5 — Confirmación y reserva
Cuando el cliente acepta, el vendedor debe **reservar la disponibilidad**. Consulta con el
**coordinador de operaciones** o directamente con el proveedor si el cupo sigue libre.
Aquí ocurre el **riesgo de doble reserva**: si dos vendedores de sedes distintas venden el
mismo cupo (mismo paquete, misma fecha) casi al mismo tiempo, ambos creen tenerlo, y el
conflicto recién se descubre cuando el proveedor rechaza la segunda reserva — con el
cliente ya comprometido. La resolución es manual, por teléfono, y a veces implica
conseguirle otro hotel o fecha al cliente sobre la marcha.

El vendedor anota la reserva en la hoja de Excel compartida y le asigna un código de
reserva a mano.

### Fase 6 — Pago
El cliente paga según el cronograma que el vendedor le comunicó de palabra (por ejemplo,
un adelanto ahora y el saldo antes del viaje). El **área de finanzas** registra el pago en
otra hoja de cálculo. El control de cuotas pendientes depende de que alguien **revise
manualmente** la hoja y detecte los saldos vencidos — con frecuencia se pasan por alto.

### Fase 7 — Emisión de documentos
Finanzas y/o el vendedor generan **manualmente en Word** el voucher, la factura y el
comprobante de liquidación, copiando los datos de la reserva a cada plantilla. Es lento,
propenso a errores de tipeo (un nombre mal escrito, un monto que no coincide con la
cotización) y depende de que la persona esté disponible.

### Fase 8 — Liquidación y comisiones
Al final, finanzas calcula la **comisión del vendedor** (un porcentaje de la venta) en otra
hoja de cálculo, y cierra la liquidación. No hay un registro contable inmutable: las hojas
se editan, y una corrección posterior **borra el historial** de lo que decía antes, lo que
complica cualquier auditoría.

## Problemas del proceso AS-IS (resumen)

| Problema | Causa raíz |
|---|---|
| Cotización lenta (2-4 h) | Búsqueda y cálculo 100% manual |
| Errores de cálculo financiero | Fórmulas de Excel frágiles, copiar/pegar |
| Doble reserva | Sin bloqueo de disponibilidad en tiempo real entre sedes |
| Aprobaciones que detienen todo | Dependen de que una persona esté disponible |
| Sin trazabilidad ni control de versiones | Archivos Word/Excel sueltos, editables |
| Documentos con errores de tipeo | Copiado manual a plantillas |
| Saldos vencidos que se pasan por alto | Control manual de cuotas |
| Auditoría imposible | Registros editables sin historial |

---

# PARTE 2 — TO-BE: Proceso automatizado (con el ERP multiagente)

## Actores y componentes

| Actor / Componente | Rol en el proceso |
|---|---|
| **Cliente** | Igual que antes — hace la consulta (hoy la ingresa el vendedor al sistema) |
| **Vendedor** | Ahora **ingresa la consulta al dashboard** y hace seguimiento en tiempo real; ya no calcula ni arma nada a mano |
| **Operador / Administrador** | Interviene **solo cuando el sistema escala** un caso (HITL) — no en cada venta |
| **OrchestratorAgent** | Punto de entrada único; inicia la Saga, enruta y coordina |
| **SalesAgent** | Interpreta la consulta, busca en catálogo (incluye búsqueda semántica RAG), arma el `PackageRequest` |
| **QuotationAgent** | Calcula el precio exacto (Decimal), versiona la cotización, detecta anomalías |
| **ValidationAgent** | Motor de reglas de negocio y compliance (R001-R012); audita cada validación |
| **ReservationAgent** | Bloquea disponibilidad de forma atómica y crea la reserva |
| **FinanceAgent** | Genera el cronograma de pago, registra el ledger, calcula comisiones |
| **DocumentAgent** | Genera vouchers/facturas/liquidaciones en PDF de forma asíncrona |
| **ItineraryAgent** | Redacta el itinerario día a día y lo entrega en PDF |
| **NotificationAgent** | Envía notificaciones en tiempo real (dashboard/WebSocket, email) |
| **MonitoringAgent** | Supervisa salud del sistema, recupera fallos, escala a humano cuando toca |
| **Infraestructura** | PostgreSQL (persistencia + auditoría inmutable), Redis (estado + locks), RabbitMQ (bus de eventos), MinIO (PDFs) |

> Cada mensaje entre agentes viaja envuelto en un **MCP Envelope** validado, y todo el flujo
> queda registrado como una **Saga** con log de pasos inmutable (ver `docs/architecture.md`).

## Narrativa del proceso automatizado

### Fase 1 — Recepción de la consulta
El **vendedor ingresa la consulta al dashboard** con un formulario estructurado: cliente,
destino, fechas, número de viajeros, rango de presupuesto (mínimo/máximo) y preferencias.
El sistema **exige los campos clave**, así que la consulta ya no queda incompleta. Esto
genera un `PackageInquiry` que entra por la API (`POST /api/v1/inquiries`).

El **OrchestratorAgent** recibe el `PackageInquiry`, **inicia una Saga** (le asigna un
identificador único que acompañará toda la transacción) y la enruta al SalesAgent. Desde
este momento, cada paso queda registrado y es rastreable.

### Fase 2 — Armado de la solicitud (SalesAgent)
El **SalesAgent** busca en el catálogo de paquetes. Primero por búsqueda estructurada
(destino + presupuesto); si no encuentra coincidencia exacta, hace una **búsqueda semántica
(RAG)** sobre los embeddings del catálogo — así encuentra paquetes aunque el destino esté
escrito distinto o la preferencia venga en texto libre ("algo relajante en la playa").

Con un LLM local (Ollama), interpreta las preferencias y arma un `PackageRequest`
estructurado. La salida del LLM está **forzada a un esquema JSON** y validada; si algo
falla, cae a una selección determinística — **nunca se detiene la venta**. El SalesAgent
**nunca calcula precios ni reserva**: solo arma la solicitud y la delega. Además, guarda la
memoria del cliente (última consulta, destino) en Redis para personalizar futuras
interacciones.

### Fase 3 — Cotización (QuotationAgent)
El **QuotationAgent** recibe el `PackageRequest` y calcula el precio con aritmética
**Decimal exacta** (sin errores de redondeo): costo base + margen (20%) + IGV (18%). Para
paquetes personalizados sin precio de catálogo, estima cada componente (vuelo, hotel,
traslados) con ayuda del LLM. Genera un `QuotationResult` **versionado**: cada recálculo
produce una versión nueva e inmutable, en vez de sobrescribir la anterior — **el problema
de las "N versiones de Word" desaparece**. Detecta anomalías automáticamente
(sobre-presupuesto, margen bajo, costo cero) y marca la cotización con esos flags. Todo esto
toma **segundos**, no horas.

### Fase 4 — Validación y compliance (ValidationAgent)
Aquí está el reemplazo de la **aprobación manual** de la Fase 3 del AS-IS. El
**ValidationAgent** evalúa la cotización contra un motor de **reglas de negocio y compliance
(R001-R012)**: margen mínimo, IGV correcto, costo positivo, ítems no vacíos, vigencia, etc.
Cada regla tiene una severidad (INFO / WARNING / ERROR / **BLOCKING**), y **cada validación
se escribe en un log de auditoría inmutable** en PostgreSQL.

- Si **todo pasa**, la cotización se marca `VALIDATED` y el cliente recibe una notificación
  en tiempo real (WebSocket) de que su cotización está lista.
- Si hay una regla **BLOCKING**, el flujo se detiene y se notifica al Orchestrator — el
  equivalente automático a "el gerente no aprueba", pero **sin depender de que una persona
  esté disponible** y con el motivo exacto registrado.

La aprobación deja de ser un cuello de botella humano y pasa a ser una decisión
**determinista, instantánea y auditable**.

### Fase 5 — Reserva (ReservationAgent)
Cuando el cliente acepta, el **ReservationAgent** **bloquea la disponibilidad de forma
atómica** usando un lock en Redis (`SETNX`, con expiración) **antes** de crear la reserva.
Esto **elimina el riesgo de doble reserva**: si dos vendedores de sedes distintas intentan
el mismo cupo (mismo paquete, misma fecha) al mismo tiempo, **solo uno obtiene el lock**; el
otro recibe un `ConflictNotification` que el Orchestrator resuelve automáticamente, en vez de
descubrir el choque cuando ya es tarde.

El agente crea la reserva con un **código único** (formato `ET-YYYYMMDD-XXXXX`), la persiste,
y dispara la fase financiera. Nunca procesa pagos: eso lo delega.

### Fase 6 — Liquidación financiera (FinanceAgent)
El **FinanceAgent** genera automáticamente el **cronograma de pago** según reglas de política
(por ejemplo: 100% si el total ≤ 1000 PEN; 50/50 hasta 5000; 30/40/30 por encima). Registra
cada transacción en un **ledger inmutable** y calcula la **comisión del vendedor** (8%). Cuando
el saldo llega a cero, crea la `LiquidationRecord` en estado COMPLETE y **dispara la generación
de documentos**. El control de cuotas vencidas ya no depende de que alguien revise una hoja:
el agente emite eventos `PaymentOverdue` automáticamente.

### Fase 7 — Emisión de documentos (DocumentAgent + ItineraryAgent)
El **DocumentAgent** genera los documentos (voucher, factura, liquidación) **automáticamente**
a partir de plantillas, **validando que todos los campos requeridos estén presentes** antes de
renderizar — así se evitan los errores de tipeo del AS-IS, porque los datos vienen de la
reserva, no se copian a mano. Produce un **PDF**, lo sube a MinIO y devuelve un enlace de
descarga con vigencia. Corre en **3 réplicas en paralelo**, de modo que un pico de solicitudes
no genera cola. En paralelo, el **ItineraryAgent** puede redactar un **itinerario día a día**
personalizado (con datos de destino recuperados vía RAG) y entregarlo también en PDF.

El **NotificationAgent** avisa al cliente y al vendedor, en tiempo real, cuando cada documento
está listo.

### Fase 8 — Cierre y trazabilidad
La **Saga se marca COMPLETED**. Todo el recorrido —cada paso, cada validación, cada
transacción— quedó registrado en tablas **inmutables** de PostgreSQL, lo que hace la
**auditoría trivial** (a diferencia de las hojas editables del AS-IS). Si en algún punto algo
falló, el **MonitoringAgent** ya intervino: reintentó automáticamente, aplicó el circuit
breaker, y **solo si la recuperación automática falló 3 veces escaló a un operador humano**
(HITL) con el contexto completo del problema. La intervención humana pasa de ser el motor de
cada venta a ser la **excepción** para los casos que el sistema no puede resolver solo.

---

# PARTE 3 — Comparación AS-IS vs TO-BE (punto por punto)

| Fase | AS-IS (manual) | TO-BE (ERP multiagente) |
|---|---|---|
| **Consulta** | Nota informal, datos incompletos | Formulario estructurado que exige los campos clave (`PackageInquiry`) |
| **Cotización** | Búsqueda y cálculo manual en Excel, 2-4 h | SalesAgent + QuotationAgent en segundos, con RAG y Decimal exacto |
| **Versiones** | Archivos Word sueltos sin control | Cotizaciones versionadas e inmutables |
| **Aprobación** | Gerente aprueba, detiene todo si no está | ValidationAgent: reglas deterministas, instantáneas, auditadas |
| **Reserva** | Riesgo de doble reserva, resolución telefónica | Lock atómico Redis; conflictos resueltos automáticamente |
| **Pago** | Registro en hoja, control manual de cuotas | Cronograma automático, ledger inmutable, alertas de vencimiento |
| **Documentos** | Word manual, errores de tipeo | PDF automático desde datos de la reserva, en paralelo (×3) |
| **Comisiones/Liquidación** | Hoja editable, sin historial | Ledger inmutable, comisión calculada automáticamente |
| **Trazabilidad** | Inexistente | Saga + audit logs inmutables — auditoría trivial |
| **Rol del humano** | Motor de cada paso | Supervisor; interviene solo en escalaciones (HITL) |
| **Continuidad ante fallos** | Si alguien falta, el proceso se detiene | Reintentos automáticos, circuit breaker, escalación solo si es necesario |
