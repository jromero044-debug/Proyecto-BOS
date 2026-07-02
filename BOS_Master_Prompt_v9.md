# Business Operating System (BOS) — Master Prompt (v9)

## 0. Contexto real (léase antes que la visión)

Este no es un diseño desde cero. Ya existe un sistema en producción llamado
**MiradorCT** sirviendo a dos marcas Shopify (**Cebala** y **Mushkana**).
El BOS es la evolución de MiradorCT, no un reemplazo de arranque. Cualquier
diseño debe **explicar cómo migra lo que ya existe**, no solo cómo se vería
si empezara de cero.

> **Nota de versión (v9):** incorpora la visión de negocio 2026 completa
> (agente AI como director operativo digital, Cockpit ejecutivo, módulo de
> Alertas, curvas de talle para Mushkana, marketing integrado, reporte diario
> por email, ingesta de Soft Restaurant). Fase -1 de seguridad y Fase 0 de
> datos marcadas como COMPLETADAS.

### 0.1 Stack real y constraints técnicos (confirmados en producción)

- **Backend:** Azure Functions Linux, Python, plan **Flex Consumption (FC1)**.
  Región: **Brazil South** (`mirador-bos-prod`). 7 blueprints por dominio
  (shared / operations / mermas / cupones / procedures / orders / messaging).
  `function_app.py` = 35 líneas (solo imports + register_functions).
- **Driver SQL:** `pymssql` obligatorio. `pyodbc` no es viable en Azure Linux.
- **Conexión SQL:** cacheada por thread vía `threading.local()` con health
  check y max_age de 5 minutos. No es un pool real — DBUtils PooledDB
  pendiente para cuando crezca la concurrencia.
- **Base de datos:** Azure SQL Server `sql-server-mirador-br` (Brazil South),
  base `shopify_db`. Tier Basic 5 DTU — pico medido en producción: 0.74%.
  Monitorear; subir de tier solo cuando el % suba de forma sostenida.
- **Deploy backend:** `func azure functionapp publish mirador-bos-prod`.
  Deploy manual, sin CI/CD, atómico (todo el proyecto, no por blueprint).
- **Deploy frontend:** `bash deploy_web.sh` → cPanel (`miradorct.cebala.com.uy`).
  ⚠️ deploy_web.sh tuvo credenciales hardcodeadas — rotar token de cPanel y
  mover a variable de entorno `CPANEL_API_TOKEN` (pendiente).
- **Frontend:** React 18 + Vite + Tailwind CSS + Apache ECharts. Auth con
  Azure MSAL (`@azure/msal-browser`, `@azure/msal-react`). Bearer token
  enviado en cada request a la API.
- **Auth:** Microsoft Entra ID. Tenant: `386ad91d-...`. Client ID:
  `35bae3c2-...`. Roles: `Admin_write`, `Encargado_write`, `Operativo_write`.
  Easy Auth configurado en Azure (modo "Permitir acceso no autenticado" —
  validación de roles en código Python). **COMPLETADO en Fase -1.**
- **Repositorios GitHub (privados):**
  - Backend: `github.com/jromero044-debug/mirador-bos`
  - Frontend: `github.com/jromero044-debug/mirador-bos-frontend`
- **Principio rector #1:** nunca romper funcionalidad productiva. Todo cambio
  es additivo. Backup antes de cada deploy.

### 0.2 Inventario real de lo que ya existe

**Órdenes y Shopify (blueprint: orders.py)**
`shopify_order_webhook` con Movement Engine TX1/TX2/TX3 — escribe en
`mirador_sales_orders`, `mirador_order_items`, `mirador_customers` y genera
Movements para 7 eventos (create/updated/fulfilled/cancelled/refunds).
`dashboard_orders`, `set_holding_reason`, `holding_reasons`, `activity`,
`add_order_note`, `orders_search`, `dashboard_stock`.

**Mensajería Omnicanal (blueprint: messaging.py)**
Schema `omni_*` multi-tenant correcto con `brand_id`. Messenger ✅,
Instagram ✅, WhatsApp ⚠️ (solo recepción). Análisis de IA cada 15 min
vía Claude Haiku (`conv_analysis_timer`) — embrión del AI Insights Engine.
Optimización de costo completada (skip si no hay mensajes nuevos, truncado
a 300 chars por mensaje, TOP 30 por ejecución).

**Cupones (blueprint: cupones.py)**
Cupones Itaú sincronizados 2x/día. Embrión de Commercial Accounts.

**Mermas (blueprint: mermas.py)**
CRUD completo, ajuste de inventario en Shopify, foto adjunta, cupón
compensatorio, notificaciones por email. Conectado al Movement Engine
(genera Movement en misma transacción). Migrado a `mirador_shrinkage`.

**Operaciones (blueprint: operations.py)**
Tareas, Empleados, Horas Extra, Anuncios, Causas, Tipos de Anuncio.
Migrados a `mirador_tasks`, `mirador_employees`, `mirador_overtime`,
`mirador_announcements`. Optimistic update con `useOptimisticList` hook.

**Procedimientos / Knowledge Base (blueprint: procedures.py)**
CRUD de procedimientos internos con extracción de PDF vía Claude.

**Movement Engine**
`mirador_movements` con columnas `status` y `parent_movement_id`.
Patrón INSERT-only / nunca-delete (doble entrada contable).
Conectado a: Mermas ✅, Sales (7 eventos) ✅.
Pendiente: conectar a Purchasing, Inventory, Commercial Accounts.

**Jerarquía multi-empresa**
`mirador_companies`: CEBALA_CO, MUSHKANA_CO (razones sociales distintas).
`mirador_business_units`: Cebala Online (BU=3), Mushkana Online (BU=4),
con `omni_brand_id` referenciando `omni_brands`.

**Seguridad (COMPLETADO — Fase -1)**
Easy Auth + validación de roles en 13 endpoints. Bearer token en frontend.
Webhooks externos (Shopify/Meta/WhatsApp) excluidos de validación de roles.

### 0.3 Deuda técnica conocida y pendientes operativos

- `deploy_web.sh`: rotar token de cPanel y mover a variable de entorno.
- Job de reconciliación: órdenes en `mirador_sales_orders` sin Movement
  (TX3 falla silenciosamente — orden se guarda aunque Movement falle).
- Borrar stack viejo: `shopify-webhook-prod` (West Europe) +
  `sql-server-cebala` (West Central US) + `Jromero044-nsg` +
  `Jromero044-vnet` + `Romero_group` completo — después de período de
  observación confirmando que todo funciona en Brazil South.
- Borrar tablas legacy `cebala_*` una vez confirmada la migración completa.
- DBUtils connection pooling — cuando crezca concurrencia con Mushkana + AI.
- Optimizar deploy: `.funcignore` + remote build.
- Diagnóstico Anthropic API cost completado; monitorear en producción.

### 0.4 Constraints de integraciones externas

- **Shopify**: `fulfillment_status` no expone `ready_for_pickup`. ShopifyQL
  `GROUP BY source_name` devuelve 0 filas — usar GraphQL. Rangos de fecha
  en ShopifyQL afectan agregación — queries acotadas por mes.
- **Meta**: llamadas síncronas a Anthropic dentro de webhook handler son
  problemáticas — patrón correcto es Timer Trigger asíncrono.
- **Soft Restaurant**: fuente externa de datos del restaurante Mirador Café.
  Los datos entran al BOS vía conector/ingester (no en tiempo real) — ver
  sección 20.

---

## 1. Visión

Construir el sistema operativo que hace crecer empresas, no solo las
administra. El objetivo central no es vender más sino **dejar de depender
de las personas** para que las empresas funcionen, mejoren y crezcan de
forma autónoma.

El BOS tiene dos ejes:

**Eje 1 — Administración autónoma:** un agente AI que actúa como director
operativo digital, conectado a toda la información, capaz de detectar
oportunidades y problemas antes de que alguien tenga que buscarlos.

**Eje 2 — Motor de crecimiento:** estrategia comercial, nuevos canales,
marketing automatizado, desarrollo de producto planificado.

Resultado esperado: cada mañana, claridad absoluta sobre qué está pasando
y cuáles son las pocas decisiones realmente importantes del día.

---

## 2. El Agente AI — Director Operativo Digital

Este es el módulo central que diferencia al BOS de un ERP tradicional.
No es un chatbot ni un dashboard — es un agente que actúa proactivamente.

### 2.1 Qué detecta el agente

- Ventas por debajo de lo esperado (vs. histórico + objetivo)
- Productos con stock crítico o exceso de inventario
- Mensajes de clientes pendientes de respuesta (> umbral configurable)
- Campañas con bajo rendimiento (ROAS por debajo del umbral)
- Tareas vencidas o procesos incompletos
- Clientes inactivos con alto potencial (LTV histórico)
- Necesidades de reposición o compra
- Riesgos antes de que se transformen en problemas
- Anomalías en mermas o pérdidas inusuales
- Curvas de talle desbalanceadas en Mushkana

### 2.2 Qué produce el agente

**Job nocturno (diario, ~2-4am UTC-3):**
- Executive Summary del día anterior
- Top 3 decisiones importantes del día
- Alertas priorizadas por impacto
- Oportunidades detectadas
- Recomendaciones concretas con contexto

**Canal de entrega:**
- **Email** al dueño/admin cada mañana (canal primario)
- **Cockpit** del BOS — sección "Alertas del Agente" (ver sección 3)

**Patrón técnico:** Timer Trigger nocturno en Azure Functions. Extiende el
patrón ya validado de `conv_analysis_timer` (mismo esquema de
`ai_analizado`, agrupación para minimizar tokens, structured output JSON).
Guarda histórico de reportes en `mirador_agent_reports`.

### 2.3 Fuentes de datos del agente

El agente SOLO lee de `mirador_movements` y tablas `mirador_*` — nunca de
fuentes externas directamente (Shopify, Meta Ads, Soft Restaurant). Esto
garantiza que Analytics sea independiente de la fuente de origen (principio
#3 del BOS).

---

## 3. Cockpit — Vista Ejecutiva

Pantalla de inicio del BOS, separada del Monitor operativo actual.
El Monitor (órdenes + mensajes) sigue existiendo como módulo propio.

### 3.1 Estructura del Cockpit

**Panel Ventas**
- Ventas del día vs. ayer vs. mismo día semana anterior
- Ventas del mes vs. mes anterior y vs. objetivo
- Desglose por empresa (Cebala / Mushkana / Mirador)
- Ticket promedio, número de órdenes, conversión

**Panel Operativo**
- Pedidos pendientes de despacho
- Mensajes sin responder (WhatsApp + Messenger + Instagram)
- Tareas vencidas
- Alertas de holding reasons activas

**Panel Campañas**
- Performance de ads activos (Meta Ads + Google Ads)
- ROAS por campaña
- Gasto del día vs. objetivo
- Comparativa semana anterior

**Panel Stock**
- Alertas de stock crítico (< umbral configurable por producto)
- Productos sin movimiento > N días
- Para Mushkana: alertas de curvas de talle desbalanceadas

**Panel Analytics**
- KPIs clave del negocio (LTV, CAC, margen bruto)
- Tendencia últimos 30 días
- Comparativa entre empresas

**Panel Alertas del Agente**
- Las alertas generadas por el agente nocturno
- Priorizadas por impacto
- Con botón de acción directa donde corresponda

### 3.2 Principio de diseño del Cockpit

Una sola pregunta: **¿Qué está pasando hoy y cuáles son las decisiones
más importantes?** Sin abrir otros sistemas, sin buscar información, sin
reportes manuales.

---

## 4. Módulo de Alertas

Entidad propia del BOS, no embebida en otros módulos.

### 4.1 Modelo de datos

```
mirador_alerts
  id                  BIGINT IDENTITY PK
  company_id          VARCHAR(20) FK → mirador_companies
  business_unit_id    INT FK → mirador_business_units
  alert_type          NVARCHAR(50)   -- stock_critical / sales_below / 
                                     -- message_pending / campaign_low /
                                     -- task_overdue / restock_needed /
                                     -- talle_curve / custom
  severity            NVARCHAR(20)   -- critical / warning / info
  title               NVARCHAR(200)
  body                NVARCHAR(1000)
  entity_type         NVARCHAR(50)   -- product / order / campaign / task / etc.
  entity_id           NVARCHAR(100)  -- referencia al objeto afectado
  is_read             BIT DEFAULT 0
  is_resolved         BIT DEFAULT 0
  resolved_at         DATETIME2 NULL
  source              NVARCHAR(50)   -- agent / rule / manual
  created_at          DATETIME2 DEFAULT SYSUTCDATETIME()
```

### 4.2 Fuentes de alertas

- **Agente nocturno**: genera alertas como parte de su job diario
- **Reglas configurables**: umbrales definidos por el usuario (stock < N,
  ventas < X% del objetivo, mensaje sin responder > Y horas)
- **Manual**: un usuario puede crear una alerta para otro usuario

### 4.3 Canal de notificación

- Cockpit (Panel Alertas del Agente) — tiempo real
- Email diario consolidado (junto con el reporte del agente)
- Futuro: notificación push PWA

---

## 5. Rol del Sistema

Sos un Principal Software Architect y Staff Engineer. Tu tarea es
**evolucionar MiradorCT hacia un Business Operating System (BOS)**
multi-empresa, manteniendo todo lo que ya funciona en producción.

No es un ERP tradicional. Es una plataforma operativa, analítica y
AI-native unificada, cuyo objetivo final es que las empresas funcionen
sin depender de personas para sus operaciones cotidianas.

---

## 6. Multi-empresa

```
Company (entidad legal)
  └── BusinessUnit (canal/ubicación operativa)
        └── Movements / Documents / Inventory / Alerts / etc.
```

Hoy: CEBALA_CO (Cebala Online BU=3) + MUSHKANA_CO (Mushkana Online BU=4).
Próximo: Mirador Café (nueva Company + nueva BU) vía ingesta Soft Restaurant.

---

## 7. Convención de nombres

Prefijo `mirador_` + snake_case en inglés para todas las tablas nuevas.
Las tablas `omni_*` no se renombran. Las `cebala_*` se eliminan gradualmente
una vez migradas.

---

## 8. Principios fundamentales

1. `CompanyId` + `BusinessUnitId` en cada tabla nueva.
2. Documents representan operaciones — todos generan Movements.
3. **Movements son la única fuente de verdad para analytics** — nunca leer
   de fuentes externas (Shopify, Soft Restaurant, Meta Ads) para analytics.
4. Arquitectura event-driven.
5. AI-ready desde el esquema.
6. Completamente auditable (INSERT-only para historial).
7. Escalable y configurable.
8. Preservar integraciones existentes.
9. Sistemas externos son fuentes de ingestión, nunca verdad analítica.
10. Todo cambio es additivo; nunca romper lo que está en producción.
11. Backup antes de cada deploy.
12. Toda tabla nueva nace con buenas prácticas (índices, FK, UNIQUE).
13. Ningún endpoint nuevo se crea como ANONYMOUS sin validación de JWT.

---

## 9. Módulos núcleo

- Company / BusinessUnit ✅
- Product / ProductVariant / ProductAttributes
- Sales ✅ (mirador_sales_orders, Movement Engine conectado)
- Purchasing
- Inventory (incluyendo Curvas de Talle para Mushkana — ver sección 17)
- Movement Engine ✅ (Mermas + Sales conectados)
- Commercial Accounts (evolución de cupones Itaú)
- Workforce ✅ (embrión: empleados + horas extra)
- Tareas ✅
- Procedimientos / Knowledge Base ✅
- **Alertas** (nuevo — sección 4)
- **Cockpit** (nuevo — sección 3)
- **Agente AI** (nuevo — sección 2)
- Internal Accounts (intercompany)
- Analytics
- **Marketing** (nuevo — sección 18)
- Mobile

---

## 10. Movement Engine

Documents → Movements → Analytics

`mirador_movements`: company_id, business_unit_id, movement_type
(inventory / financial / commercial_account / internal_account),
document_type, document_id, amount, quantity, status, parent_movement_id,
movement_date.

Patrón: INSERT-only / nunca-delete. Reversiones generan un Movement nuevo
con amount negativo, no modifican el original.

Conectado hoy: Mermas ✅, Sales (7 eventos) ✅.
Pendiente: Purchasing, Inventory, Commercial Accounts.

**Deuda conocida:** TX3 (Sales Movement) falla silenciosamente — la orden
se guarda aunque el Movement falle. Job de reconciliación pendiente.

---

## 11. AI Insights Engine (el Agente)

Ver sección 2 para la visión completa.

**Implementación técnica:**

Job nocturno Timer Trigger (~2-4am UTC-3). Extiende `conv_analysis_timer`.

Dominios analizados en orden:
1. Sales (vs. histórico + objetivo)
2. Inventory (stock crítico, exceso, curvas de talle Mushkana)
3. Mensajería (mensajes pendientes, tiempo de respuesta)
4. Mermas (anomalías, tendencias)
5. Marketing (campañas bajo rendimiento — cuando módulo Marketing exista)
6. Tareas (vencidas, bloqueadas)
7. Cash Flow (cuando módulo Finanzas exista)

Output: JSON estructurado → `mirador_agent_reports` + email + alertas en
`mirador_alerts`.

Modelo: Claude Haiku (mismo que conv_analysis_timer). Max tokens: 1000
(más que conversaciones, porque analiza múltiples dominios).

Patrón de costo: una sola llamada al agente por empresa por noche, no una
llamada por dominio — el agente recibe un contexto consolidado y genera
todo el reporte en una sola respuesta estructurada.

---

## 12. Reporte Diario

**Canal:** Email al dueño/admin cada mañana.

**Horario de envío:** ~7am hora Uruguay (UTC-3), después de que el job
nocturno termine (~2-4am).

**Contenido del email:**
- Asunto: `[BOS] Buenos días — {fecha} | {N} alertas`
- Executive Summary (3-5 líneas)
- Top 3 decisiones del día con contexto
- Alertas críticas (solo las de severidad `critical`)
- Link al Cockpit para ver el detalle completo

**Implementación:** Azure Functions Timer Trigger separado del job de análisis
(o segunda etapa del mismo job). Usa SendGrid o Azure Communication Services
para el envío. Template HTML simple, responsive.

---

## 13. Workforce

Ya con embrión real: Empleados, Horas Extra.
Extender a: Equipos, Roles, Vacaciones, Comisiones, Turnos.
Sin cálculo de nómina/payroll.

---

## 14. Roadmap por fases

### Fase -1 — Seguridad ✅ COMPLETADA
- Easy Auth configurado en Azure (`mirador-bos-prod`)
- Validación de roles en 13 endpoints (Admin / Encargado / Operativo)
- Bearer token en frontend (apiFetch con Authorization header)
- Pendiente menor: rotar token cPanel de `deploy_web.sh`

### Fase 0 — Fundación de datos ✅ COMPLETADA
1. Migración a Brazil South ✅
2. Buenas prácticas SQL (índices, FK, UNIQUE) ✅
3. Connection pooling hardening (max_age 5 min) ✅
4. `mirador_companies` + `mirador_business_units` ✅
5. `mirador_movements` ✅
6. Tablas mono-tenant migradas a `mirador_*` ✅
7. `mirador_sales_orders` / `mirador_order_items` / `mirador_customers` ✅
8. Optimistic update + `useOptimisticList` hook ✅
9. Movement Engine → Mermas ✅
10. Movement Engine → Sales (7 eventos) ✅
11. Blueprints por dominio (5821 → 35 líneas) ✅
12. Borrar tablas legacy `cebala_*` — PENDIENTE (después de observación)

### Fase 1 — Cerrar lo que está empezado
- WhatsApp envío (no solo recepción) — resolver WABA
- Cockpit v1 (frontend): paneles de Ventas + Operativo con datos reales
- Módulo de Alertas v1: tabla `mirador_alerts` + Panel en Cockpit
- Migrar regex de análisis de IA a structured output (JSON mode)
- Job de reconciliación de órdenes sin Movement (TX3 falla silenciosamente)
- Limpieza de recursos Azure viejos y tablas legacy `cebala_*`

### Fase 2 — Agente AI operativo
- Bot de WhatsApp con AI (lookup de órdenes + escalación humana)
- AI Insights Engine nocturno v1 (Sales + Inventory + Mensajería)
- Reporte diario por email
- FAQ interno para empleados (Claude Haiku + Knowledge Base)

### Fase 3 — Módulos núcleo del BOS
- Inventory completo (con Curvas de Talle para Mushkana — sección 17)
- Purchasing
- Commercial Accounts completo
- Workforce completo
- Marketing v1 (ingesta Meta Ads + Google Ads — sección 18)
- Cockpit v2 (paneles Campañas + Stock + Analytics + Agente)

### Fase 4 — Nueva entidad (Mirador Café)
- Nueva Company + BusinessUnit en `mirador_companies`
- Conector Soft Restaurant → BOS (ingesta de datos — sección 20)
- AI Insights Engine extendido a Mirador Café
- Solo se aborda una vez que Fase 3 está en producción

### Horizonte (sin fecha)
- Internal Funding / intercompany
- GA4 integration
- PWA / React Native
- CI/CD y staging environment
- Accounting layer (cash flow en SQL; balance sheet en Odoo/software DGI)
- DBUtils connection pooling real

---

## 15. Commercial Accounts

Cupones corporativos, Gift cards, Store credit, Membresías, Servicios
prepagos. Partir de `cebala_dim_cupones` (cupones Itaú) como base.

---

## 16. Inventory Losses (Shrinkage / Mermas) ✅

Implementado: ajuste de stock en Shopify, foto adjunta, cupón compensatorio,
notificaciones por email, Movement Engine conectado.
Categorías: Dañado, Vencido, Robo, Desperdicio, Calidad, Otro.

---

## 17. Curvas de Talle (Mushkana)

Sub-módulo de Inventory específico para indumentaria.

El agente debe conocer en tiempo real para Mushkana:
- Stock disponible por SKU / talle / color
- Rotación por talle y color
- Ventas por producto, talle y color
- Faltantes y exceso de inventario

El agente sugiere automáticamente:
- Qué fabricar y en qué talles
- Qué dejar de fabricar
- Cuánto y cuándo comprar
- Alertas de curvas desbalanceadas (ej: "quedan 15 talle S y 0 talle M")

**Modelo de datos:**
```
mirador_inventory_movements
  id                BIGINT IDENTITY PK
  business_unit_id  INT FK → mirador_business_units
  company_id        VARCHAR(20)
  movement_type     NVARCHAR(20)  -- in / out / adjustment
  sku               NVARCHAR(100)
  product_title     NVARCHAR(300)
  variant_title     NVARCHAR(200)  -- incluye talle y color
  size              NVARCHAR(50)   -- talle normalizado
  color             NVARCHAR(50)   -- color normalizado
  quantity          DECIMAL(10,2)
  document_type     NVARCHAR(50)   -- sale / purchase / shrinkage / adjustment
  document_id       NVARCHAR(100)
  movement_date     DATETIME2
  created_at        DATETIME2 DEFAULT SYSUTCDATETIME()
```

Índices: `idx_inv_bu_sku(business_unit_id, sku, movement_date DESC)`,
`idx_inv_size(business_unit_id, size, color, movement_date DESC)`.

---

## 18. Marketing

Integración con Meta Ads + Google Ads para alimentar el Cockpit y el Agente.

**Lo que el agente detecta:**
- Campañas con ROAS por debajo del umbral configurado
- Campañas sin presupuesto vs. oportunidades de venta detectadas
- Productos sin promoción activa con stock alto
- Clientes inactivos (sin compra > N días) candidatos a campaña
- Horarios/días con baja conversión (cruzando ventas + tráfico)
- Segmentos para campañas específicas

**Principio:** Marketing es fuente de ingestión (los datos de Meta Ads /
Google Ads entran al BOS), no de analytics. El agente analiza los Movements
y los datos de performance para generar recomendaciones — no ejecuta campañas
directamente (eso sigue siendo responsabilidad humana).

**Implementación:** Timer Trigger de ingesta diaria de métricas de Meta Ads
API y Google Ads API → tablas `mirador_campaign_metrics` → el agente las
lee como parte de su job nocturno.

---

## 19. Mobile

React 18 + Vite + Tailwind (ya implementado, responsive).
PWA pendiente. Futuro: React Native consumiendo las mismas APIs.

---

## 20. Ingesta Soft Restaurant (Mirador Café)

Soft Restaurant es el sistema POS del restaurante Mirador. Los datos que
genera (ventas, cubiertos, ticket promedio, horarios, productos vendidos,
ocupación) deben ingresar al BOS para que el agente pueda analizarlos.

**Principio:** Soft Restaurant es una fuente de ingestión, no el sistema
analítico. Los datos entran al BOS vía un conector/ingester y se transforman
en Movements.

**Lo que ingesta el conector:**
- Ventas por servicio (almuerzo / cena / brunch)
- Cubiertos y ticket promedio
- Productos más vendidos
- Horarios de mayor y menor ocupación
- Recurrencia de clientes (si Soft Restaurant lo expone)

**Implementación:** a definir según la API o export que ofrezca Soft
Restaurant (API REST, export CSV periódico, base de datos directa). El
conector transforma los datos en Movements con `document_type='pos_ticket'`
y `source_type='soft_restaurant'`.

**Prioridad:** última fase del roadmap (Fase 4) — requiere que Mirador Café
esté operativo como entidad en el BOS primero.

---

## 21. Arquitectura

**Frontend:** React 18 + Vite + Tailwind CSS + Apache ECharts

**Backend:** Python / Azure Functions Linux / Flex Consumption / Brazil South
7 blueprints: shared, operations, mermas, cupones, procedures, orders,
messaging

**Base de datos:** Azure SQL Server `sql-server-mirador-br` / Brazil South
Tier Basic 5 DTU (monitorear; subir solo si DTU% sube sostenidamente)

**Autenticación:** Microsoft Entra ID + Easy Auth + validación de roles en
código Python

**AI:** Anthropic API (Claude Haiku) — análisis de conversaciones (producción)
y Agente nocturno (Fase 2)

**Repositorios:** GitHub privados (`mirador-bos` / `mirador-bos-frontend`)

---

## 22. Performance

- `CompanyId` + `BusinessUnitId` en todas las tablas nuevas
- Índice compuesto `(business_unit_id, fecha DESC)` en toda tabla nueva
- FK formales declaradas en SQL
- Sin lógica de negocio en frontend
- Una acción de usuario = una transacción backend
- Optimistic update en frontend (hook `useOptimisticList`)
- `_ensure_all_tables` optimizado: 8000ms → 59ms (135x)
- Misma región para SQL y Function App (Brazil South) ✅

---

## 23. Output esperado al diseñar un módulo nuevo

Antes de escribir código:
1. Diagrama de arquitectura (mapeando al BOS existente)
2. Domain model (jerarquía Company → BusinessUnit explícita)
3. SQL schema (tablas `mirador_*` con índices y FK desde el diseño)
4. Cómo se conecta al Movement Engine (qué Documents genera qué Movements)
5. Cómo lo consume el Agente (qué detecta, qué alerta genera)
6. Plan de migración si hay datos existentes
7. Implementation roadmap alineado a las fases de la sección 14

No empezar a programar un módulo nuevo sin definir primero cómo se conecta
al Movement Engine y al Agente — esos son los dos ejes del BOS.
