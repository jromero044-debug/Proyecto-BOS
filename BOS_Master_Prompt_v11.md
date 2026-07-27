# BOS Master Prompt — v11

> **Estado real del sistema a julio 2026.**
> Este documento describe el sistema MiradorCT BOS tal como existe en producción hoy.
> Cualquier Claude que lo lea puede entender el sistema completo y continuar el trabajo sin explorar el código.
> 
> Repositorios con CLAUDE.md para arranque inmediato:
> - Backend: `github.com/jromero044-debug/mirador-bos`
> - Frontend: `github.com/jromero044-debug/mirador-bos-frontend`

---

## 1. Contexto y Visión

**MiradorCT BOS** es el sistema operativo interno de las marcas Cebala y Mushkana (Uruguay). Cubre:
- Monitoreo de órdenes Shopify en tiempo real
- COGS y margen bruto por línea de venta
- Balance financiero (P&L, gastos, compras, proveedores, cuentas a cobrar, préstamos)
- Marketing analytics (Meta Ads, Google Ads)
- Análisis de clientes (RFM, cohorts, cross-brand)
- Mensajería omnicanal (Messenger / Instagram / WhatsApp)
- Procedimientos internos (knowledge base)
- RRHH básico (empleados, horas extras)

**Principio rector:** nunca romper funcionalidad productiva. Todo cambio es aditivo. Backup antes de cada deploy.

---

## 2. Infraestructura

| Componente | Detalle |
|-----------|---------|
| **Backend** | Azure Functions Linux, Python 3.11, plan Flex Consumption FC1, región Brazil South |
| **App name** | `mirador-bos-prod` |
| **Resource group** | `mirador-bos-rg` |
| **Base de datos** | Azure SQL Server `sql-server-mirador-br.database.windows.net`, DB `shopify_db`, Brazil South |
| **Frontend host** | cPanel, Apache, `miradorct.cebala.com.uy` |
| **Auth** | Microsoft Entra ID (Azure AD), Easy Auth en App Service |
| **Tenant / Client** | tenant `386ad91d-...`, client `35bae3c2-...` |
| **Repositorios** | github.com/jromero044-debug/mirador-bos (backend), /mirador-bos-frontend (frontend) |

---

## 3. Stack Técnico

### Backend
- **Lenguaje:** Python 3.11
- **Framework:** Azure Functions SDK v2, blueprints por dominio
- **DB driver:** `pymssql` — **NUNCA usar pyodbc** (no funciona en Azure Linux)
- **Auth SQL:** `username@server-name` (ej. `cebala@sql-server-mirador-br`)
- **Librerías clave:** `pymssql`, `requests`, `pdfplumber`, `anthropic`, `azure-functions`

### Frontend
- **Framework:** React 18 + Vite 6
- **Estilos:** Tailwind CSS 3 con tokens de diseño propios
- **Charts:** Apache ECharts 5 (`echarts-for-react`)
- **Iconos:** Tabler Icons (clases CSS `ti ti-*`, CDN)
- **Tipografías:** Inter (sans) + DM Mono (mono) — Google Fonts
- **Auth:** MSAL (`@azure/msal-browser` + `@azure/msal-react`)

---

## 4. Deploy

### Backend
```bash
cd /Users/admin/shopify-func
func azure functionapp publish mirador-bos-prod --python
```

### Frontend
```bash
cd /Users/admin/shopify-dashboard
npm run build && bash deploy_web.sh
```
`deploy_web.sh` detecta assets nuevos vs servidor y sube solo los cambios (FTP a cPanel).

### Dev local — backend
```bash
bash dev_start.sh
```
Abre el firewall de Azure SQL con la IP pública dinámica y levanta Azure Functions localmente. Cierra el firewall al hacer Ctrl+C.

---

## 5. Variables de Entorno

En producción: Azure App Settings. Localmente: `local.settings.json` (gitignored — **NUNCA commitear, NUNCA imprimir valores**).

| Variable | Propósito |
|---------|-----------|
| `SQL_SERVER` | `sql-server-mirador-br.database.windows.net` |
| `SQL_PASSWORD` | Password Azure SQL |
| `SHOPIFY_STORE` | `cebala.myshopify.com` |
| `SHOPIFY_ACCESS_TOKEN` | Token Admin API Cebala |
| `MUSHKANA_STORE` | `mushkana.myshopify.com` |
| `MUSHKANA_ACCESS_TOKEN` | Token Admin API Mushkana |
| `META_ADS_TOKEN` | Meta Graph API token |
| `META_ADS_ACCOUNT_ID` | ID cuenta Meta Ads |
| `META_PAGE_TOKEN_CEBALA` | Token página de Facebook |
| `META_IG_TOKEN_CEBALA` | Token Instagram |
| `ANTHROPIC_API_KEY` | Claude API (procedimientos PDF) |
| `AzureWebJobsStorage` | `UseDevelopmentStorage=true` en local |
| `FUNCTIONS_WORKER_RUNTIME` | `python` |

---

## 6. Arquitectura Backend

### 6.1 Punto de entrada

`function_app.py` — ~35 líneas, solo registra blueprints:
```python
app = func.FunctionApp()
app.register_functions(operations_bp)
app.register_functions(mermas_bp)
# ... etc
```

### 6.2 Blueprints (`blueprints/`)

| Archivo | Módulo |
|---------|--------|
| `shared.py` | Conexión DB, auth helpers, `_ensure_all_tables`, tablas SQL, CORS |
| `orders.py` | Webhook Shopify, órdenes de venta, clientes, actividad, stock |
| `costs.py` | COGS: costos por línea, backfill, órdenes sin costear, vista por SKU |
| `finance.py` | Balance P&L, gastos, vendors, partners, receivables, préstamos, movimientos |
| `purchasing.py` | Órdenes de compra (PO), recepciones de mercancía, anticipos |
| `customers.py` | Análisis de clientes: RFM, cohorts, LTV, cross-brand, lista paginada |
| `marketing.py` | Meta Ads (campaigns/adsets/ads), ingest diario, alertas |
| `google_ads.py` | Google Ads campaigns/keywords/daily, ingest |
| `messaging.py` | Messenger/Instagram/WhatsApp, análisis calidad (Claude Haiku) |
| `operations.py` | Monitor, holding reasons, tareas, anuncios, empleados, horas extras |
| `mermas.py` | Registro de mermas/daños con fotos |
| `procedures.py` | Knowledge base de procedimientos (PDF → Claude) |
| `cupones.py` | Integración cupones Itaú |

### 6.3 Timers programados

| Timer | Horario | Propósito |
|-------|---------|-----------|
| `daily_reconcile` | 3:00 UTC | Reconcilia órdenes Shopify últimas 48h |
| `cogs_reconcile` | 3:30 UTC | Asigna costos a órdenes sin costear (últimos 90d) |
| `loan_auto_debit` | 7:00 UTC | Procesa cuotas de préstamos vencidas |
| `meta_ads_ingest` | 8:00 y 20:00 UTC | Ingesta Meta Ads (adsets + ads) |
| `google_ads_daily_ingest` | 9:00 UTC | Ingesta Google Ads |
| `conv_analysis_timer` | cada 15 min | Análisis IA de conversaciones (Claude Haiku) |
| `keep_warm` | cada 4h | Mantiene conexión DB activa |

---

## 7. Patrones de Código Críticos

### 7.1 Conexión DB

```python
from blueprints.shared import get_conn, _ensure_all_tables

_ensure_all_tables()   # sin argumentos — crea tablas si no existen
conn = get_conn()      # thread-local, auto-reconnect, max_age 5min
cur  = conn.cursor()
# ...
conn.commit()
cur.close()
```

`get_conn()` usa `threading.local()` con health check. Si la conexión tiene más de 5 minutos o falla el ping, crea una nueva. Auto-rollback en error.

### 7.2 Patrón de autenticación — CRÍTICO

```python
from blueprints.shared import require_roles, forbidden, ADMIN, ENCARGADO, OPERATIVO

# ✅ CORRECTO — require_roles retorna bool (True = autorizado)
if not _IS_LOCAL and not require_roles(req, ENCARGADO):
    return forbidden()

# ❌ INCORRECTO — retorna True cuando está autorizado → Azure explota con 500
err = require_roles(req, ENCARGADO)
if err:
    return err
```

**Roles disponibles:**
```python
ADMIN     = {"Admin_write"}
ENCARGADO = {"Admin_write", "Encargado_write"}
OPERATIVO = {"Admin_write", "Encargado_write", "Operativo_write"}
```

**Detección local:**
```python
_IS_LOCAL = os.environ.get("AzureWebJobsStorage", "") == "UseDevelopmentStorage=true"
```
En local, `require_roles` no se llama — todo pasa sin auth.

### 7.3 Easy Auth

Azure App Service valida el JWT e inyecta `X-MS-CLIENT-PRINCIPAL` (base64 JSON):
```json
{"claims": [{"typ": "roles", "val": "Admin_write"}, {"typ": "name", "val": "Juan"}]}
```
Sin token (curl sin auth) → `X-MS-CLIENT-PRINCIPAL` ausente → `require_roles` retorna `False` → la solicitud pasa solo si el endpoint no requiere rol. Proteger endpoints sensibles apropiadamente.

### 7.4 Helpers de respuesta

```python
def _ok(data, status=200):
    return func.HttpResponse(json.dumps(data, default=str),
                             mimetype="application/json", headers=_CORS, status_code=status)

def _err(msg, status=400):
    return func.HttpResponse(json.dumps({"ok": False, "error": msg}),
                             mimetype="application/json", headers=_CORS, status_code=status)

def _rows(cur):
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]
```

### 7.5 CORS

```python
_CORS = {
    "Access-Control-Allow-Origin":  "*",
    "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
    "Access-Control-Max-Age":       "86400",
}
```
Todos los endpoints usan `headers=_CORS`. Incluir `methods=["GET", "OPTIONS"]` y manejar OPTIONS:
```python
if req.method == "OPTIONS":
    return _ok({})
```

### 7.6 SQL — Convenciones

- Parámetros siempre con `%s` (pymssql) — NUNCA f-strings con valores de usuario
- `SELECT SCOPE_IDENTITY()` después de cada INSERT para obtener ID insertado
- f-strings solo para fragmentos SQL seguros (slugs hardcodeados, HAVING/WHERE condicionales)

### 7.7 Filtro de marca (brand filter)

```python
def _slug_filter(shop_param):
    s = (shop_param or "").lower()
    if "cebala"   in s: return " AND bu.slug LIKE 'cebala%'"
    if "mushkana" in s: return " AND bu.slug LIKE 'mushkana%'"
    return ""
```
Retorna solo 3 strings fijos → sin SQL injection. Requiere `JOIN mirador_business_units bu ON bu.id = so.business_unit_id`.

### 7.8 Exchange Rate

Cache en memoria por día. Fuentes en orden: fxratesapi → open.er-api → fallback 40.0.

### 7.9 Webhook Safety — Multi-transacción

Para el webhook de Shopify: TX1 (raw payload idempotent) → TX2 (upsert mirador schema) → TX3 (movements) → TX4 (asignación de costos, no fatal). Si TX2 falla → 500. TX3/4 → warning, orden ya comiteada.

---

## 8. Endpoints API — Referencia Completa

### 8.1 Monitor y Órdenes

| Endpoint | Método | Rol | Descripción |
|---------|--------|-----|-------------|
| `shopify_order_webhook` | POST | ANON | Procesa eventos Shopify (create/update/fulfill/cancel/refund) |
| `dashboard_orders` | GET | ANON | Órdenes sin cumplir últimas 45d + métricas |
| `holding_reasons` | GET | ANON | Lista de motivos de hold |
| `holding_reasons` | POST | ENCARGADO | Crear motivo de hold |
| `holding_reasons` | DELETE | ENCARGADO | Desactivar motivo |
| `set_holding_reason` | POST | ANON | Asignar motivo a orden |
| `add_order_note` | POST | ANON | Agregar nota timestampeada a orden Shopify |
| `orders_search` | GET | ANON | Buscar órdenes por producto/SKU |
| `activity` | GET | ANON | Tendencias de ventas (período, granularidad, tienda) |
| `dashboard_stock` | GET | ANON | Stock de SKUs en órdenes pendientes |

### 8.2 Clientes

| Endpoint | Método | Rol | Descripción |
|---------|--------|-----|-------------|
| `customers/summary` | GET | ANON | KPIs: total, nuevos, recurrentes, ticket promedio |
| `customers/rfm` | GET | ANON | Segmentación RFM: champions/loyal/new/at_risk/lost |
| `customers/cohorts` | GET | ANON | Retención por cohortes mensuales (12 meses) |
| `customers/cross_brand` | GET | ANON | Overlap Cebala↔Mushkana + top cross-brand |
| `customers/orders` | GET | ANON | Historial de órdenes por email |
| `customers/list` | GET | ANON | Lista paginada con filtros de segmento |
| `customers/search` | GET | ANON | Búsqueda de cliente por nombre/email/tel |
| `customers` | POST | ANON | Crear cliente |

### 8.3 Ventas Manuales

| Endpoint | Método | Rol | Descripción |
|---------|--------|-----|-------------|
| `sales_orders` | GET | ANON | Lista órdenes de venta paginada |
| `sales_orders/{id}` | GET | ANON | Detalle de orden |
| `manual_orders` | POST | ENCARGADO | Crear orden manual |
| `manual_orders/{id}/status` | PATCH | ENCARGADO | Cambiar estado |
| `skus` | GET | ANON | Lista de SKUs por BU |

### 8.4 COGS y Costos

| Endpoint | Método | Rol | Descripción |
|---------|--------|-----|-------------|
| `costs/sku-info` | GET | ANON | Último costo + historial para un SKU |
| `costs/import` | POST | ENCARGADO | Importar costos en bulk desde CSV/PO |
| `costs/order` | GET | ANON | Costos por línea de una orden |
| `costs/assign` | POST | ENCARGADO | Asignar costos a líneas de una orden (manual) |
| `costs/uncosted-orders` | GET | ENCARGADO | Órdenes con costos estimados (is_estimated=1) |
| `costs/costed-orders` | GET | ENCARGADO | Órdenes completamente costeadas |
| `costs/products` | GET | ENCARGADO | Vista por SKU: unidades, revenue, COGS, margen |
| `costs/assign-sku` | POST | ENCARGADO | Asignar costo a todas las líneas de un SKU en el período |
| `costs/backfill-premigration` | GET | ENCARGADO | Backfill de costos pre-migración (solo una vez) |

**Lógica de asignación de costos:**
- Ítem con "envío"/"shipping" en título/SKU → cost = precio cobrado (`source='shipping_passthrough'`, is_estimated=0)
- Producto → lookup en `mirador_product_costs` WHERE sku=%s AND effective_from ≤ order_date
  - Encontrado → costo real, is_estimated=0
  - No encontrado → estimado = unit_price/2.2, is_estimated=1, `standard_cost_uyu` = unit_price/2.2

**Columna `source` en `mirador_order_line_costs`:**
- NULL → webhook/reconcile automático
- `'import'` → importado via CSV
- `'backfill'` / `'backfill_combo'` → backfill pre-migración
- `'shipping_passthrough'` → envío (costo = precio)
- `'manual'` → asignado via POST /costs/assign o /costs/assign-sku
- `'purchase_order'` → desde recepción de OC

### 8.5 Finanzas

| Endpoint | Método | Rol | Descripción |
|---------|--------|-----|-------------|
| `balance` | GET | ADMIN | Balance P&L completo |
| `exchange_rate` | GET | ANON | Tipo de cambio BCU (USD→UYU, cacheado por día) |
| `vendors` | GET/POST | ENCARGADO | Proveedores |
| `vendors/{id}` | PUT | ENCARGADO | Actualizar proveedor |
| `expenses` | GET/POST | ENCARGADO | Gastos (paginado, con resumen) |
| `expenses/{id}` | GET/PUT/DELETE | ENCARGADO | Detalle/edición/eliminación de gasto |
| `expenses/{id}/edit` | PUT | ENCARGADO | Edición completa de gasto |
| `expenses/{id}/payments` | POST | ENCARGADO | Registrar pago de gasto |
| `expenses/{id}/payments/{pid}` | DELETE | ENCARGADO | Revertir pago |
| `partners` | GET | ANON | Socios/cuentas internas |
| `partners/{id}/transactions` | GET/POST | ANON | Transacciones entre socios |
| `partners/{id}/transactions/{txId}` | PUT | ANON | Actualizar transacción |
| `receivables` | GET/POST | ANON | Cuentas por cobrar |
| `receivables/{id}` | GET | ANON | Detalle |
| `receivables/{id}/payments` | POST | ANON | Registrar cobro |
| `loans` | GET/POST | ANON | Préstamos |
| `loans/{id}` | GET | ANON | Detalle + cuotas |
| `loans/{id}/installments/{num}/pay` | POST | ANON | Pagar cuota → genera gasto |
| `movements` | GET | ANON | Movimientos financieros/inventario |
| `movements/{id}/reverse` | POST | ANON | Revertir movimiento |
| `document_flow/{type}/{id}` | GET | ANON | Árbol de flujo de documentos |

### 8.6 Compras

| Endpoint | Método | Rol | Descripción |
|---------|--------|-----|-------------|
| `purchase_orders` | GET/POST | ADMIN | Órdenes de compra (lista/crear) |
| `purchase_orders/{id}` | GET/PUT | ADMIN | Detalle/actualizar OC |
| `purchase_orders/{id}/status` | PATCH | ADMIN | Cambiar estado OC |
| `purchase_orders/{id}/advances` | POST | ADMIN | Registrar anticipo |
| `purchase_orders/{id}/advances/{advId}/reverse` | POST | ADMIN | Revertir anticipo |
| `goods_receipts` | GET/POST | ANON | Recepciones de mercancía |
| `goods_receipts/{id}/confirm` | POST | ANON | Confirmar recepción → ajusta stock Shopify |
| `goods_receipts/{id}/reverse` | POST | ANON | Revertir recepción |

### 8.7 Marketing

| Endpoint | Método | Rol | Descripción |
|---------|--------|-----|-------------|
| `meta/summary` | GET | ANON | Resumen campañas Meta Ads |
| `meta/campaigns` | GET | ANON | Campañas Meta por rango de fechas |
| `meta/campaigns/{id}/adsets` | GET | ANON | Adsets de una campaña |
| `meta/ads` | GET | ANON | Ads individuales (con detección de tipo creativo) |
| `meta/ingest` | POST | ADMIN | Trigger manual ingesta adset-level |
| `meta/ingest/ads` | POST | ADMIN | Trigger manual ingesta ad-level |
| `meta/thresholds` | GET | ANON | Umbrales de alerta (ROAS, CTR, CPM, CPA) |
| `meta/thresholds/{metric}` | PUT | ADMIN | Actualizar umbral |
| `google-ads/summary` | GET | ANON | Resumen Google Ads |
| `google-ads/campaigns` | GET | ANON | Campañas Google |
| `google-ads/keywords` | GET | ANON | Keywords |
| `google-ads/daily` | GET | ANON | Datos diarios por campaña |
| `google-ads/comparison` | GET | ANON | Comparación spend/conversions/ROAS |
| `google-ads/ingest` | POST | ADMIN | Trigger manual ingesta |
| `marketing/revenue_daily` | GET | ANON | Revenue diario por canal |

### 8.8 Mensajería y Calidad

| Endpoint | Método | Rol | Descripción |
|---------|--------|-----|-------------|
| `dashboard_messages` | GET | ANON | Vista omnicanal de conversaciones |
| `conv_quality` | GET | ANON | Panel de calidad de atención |
| `conv_by_phone` | GET | ANON | Conversaciones por teléfono |
| `conv_messages` | GET | ANON | Mensajes de una conversación |
| `conv_events` | GET | ANON | Eventos desde timestamp |
| `conv_phone_check` | GET | ANON | Verificar si teléfonos tienen conversación |
| `close_conv` | POST | ANON | Cerrar conversación |
| `send_message` | POST | ANON | Enviar mensaje |
| `resolve_names` | GET | ANON | Resolver nombres de conversaciones |
| `run_conv_analysis` | GET | ANON | Trigger manual análisis IA |

### 8.9 Operaciones

| Endpoint | Método | Rol | Descripción |
|---------|--------|-----|-------------|
| `anuncios` | GET/POST | ANON/ENCARGADO | Anuncios internos |
| `anuncios/{id}` | PUT | ENCARGADO | Actualizar anuncio |
| `anuncios/{id}/read` | POST/DELETE | ANON | Marcar/desmarcar como leído |
| `anuncios/{id}/lecturas` | GET | ENCARGADO | Quién leyó el anuncio |
| `tipos_anuncio` | GET/POST/DELETE | ANON/ENCARGADO | Tipos de anuncio |
| `tipos_anuncio/{id}` | PUT | ENCARGADO | Actualizar tipo |
| `tareas` | GET/POST | ANON | Tareas |
| `tareas/{id}` | GET/PUT | ANON | Detalle/actualizar tarea |
| `tareas/{id}/comentarios` | POST | ANON | Comentar tarea |
| `empleados` | GET/POST | ANON/ADMIN | Empleados |
| `empleados/{id}` | PUT | ADMIN | Actualizar empleado |
| `horas_extras` | GET/POST | ANON/ENCARGADO | Horas extras |
| `horas_extras/{id}` | PUT/DELETE | ENCARGADO | Actualizar/eliminar HE |
| `causas_hora_extra` | GET/POST/DELETE | ANON | Causas de HE |
| `system_users` | GET | ENCARGADO | Usuarios del sistema |

### 8.10 Mermas y Procedimientos

| Endpoint | Método | Rol | Descripción |
|---------|--------|-----|-------------|
| `mermas` | GET/POST | ANON | Mermas/daños |
| `mermas/{id}` | DELETE | ANON | Eliminar merma |
| `mermas/skus` | GET | ANON | SKUs de órdenes pendientes |
| `mermas/foto` | POST | ANON | Upload foto (base64) |
| `merma_notificados` | GET/POST/DELETE | ANON | Lista de emails notificados |
| `procedures` | GET/POST | ANON | Procedimientos (knowledge base) |
| `procedures/{slug}` | GET/PUT/DELETE | ANON | CRUD por slug |
| `procedures/pdf` | POST | ANON | PDF → Claude → extrae contenido |

### 8.11 Datos Maestros y Admin

| Endpoint | Método | Rol | Descripción |
|---------|--------|-----|-------------|
| `companies` | GET | ANON | Compañías (CEBALA_CO, MUSHKANA_CO) |
| `business_units` | GET/POST | ANON/ADMIN | Unidades de negocio |
| `business_units/{id}` | PUT | ADMIN | Actualizar BU |
| `payment_methods` | GET/POST | ANON/ADMIN | Métodos de pago |
| `payment_methods/{id}` | PUT | ADMIN | Actualizar método |
| `payment_terms` | GET/POST | ANON/ADMIN | Términos de pago |
| `payment_terms/{id}` | PUT | ADMIN | Actualizar término |
| `vat_rates` | GET/POST | ANON/ADMIN | Tasas IVA |
| `vat_rates/{id}` | PUT | ADMIN | Actualizar tasa |
| `expense_types` | GET/POST | ANON/ADMIN | Tipos de gasto |
| `expense_types/{id}` | PUT | ADMIN | Actualizar tipo |
| `finance/payment_methods` | GET | ANON | Métodos de pago (finance module) |
| `finance/payment_terms` | GET | ANON | Términos de pago (finance module) |
| `webhook_logs` | GET | ADMIN | Logs de webhooks |
| `cupones_itau` | GET | ADMIN | Cupones Itaú |

---

## 9. Schema SQL — Tablas Principales

### 9.1 Órdenes y Ventas

**`mirador_customers`** — Master de clientes multi-marca
- id, business_unit_id (FK), first_name, last_name, email, phone
- source_type, source_id (Shopify customer ID), omni_customer_id
- canonical_id (dedup cross-brand: apunta al más antiguo)

**`mirador_sales_orders`** — Todas las órdenes
- id, business_unit_id, customer_id, source_type, source_id (Shopify order ID)
- source_order_number, document_date, processed_at, status
- total_amount, current_total_amount, subtotal, discount_amount, tax_amount, shipping_amount
- financial_status, fulfillment_status, shopify_tags, currency, movement_id

**`mirador_order_items`** — Líneas de orden
- id, sales_order_id, business_unit_id
- sku, product_title, variant_title
- shopify_line_item_id (UNIQUE con sales_order_id), shopify_product_id, shopify_variant_id
- quantity, unit_price, discount_amount, total_price

**`mirador_order_line_costs`** — COGS por línea
- id, order_id (Shopify order ID bigint), line_item_id (Shopify line item ID), shop_domain
- sku, variant_id, quantity
- unit_cost_uyu, total_cost_uyu
- is_estimated (0=real, 1=estimado)
- standard_cost_uyu (= unit_price/2.2, para líneas estimadas)
- source ('purchase_order'/'import'/'backfill'/'shipping_passthrough'/'manual'/NULL)
- po_id, assigned_at
- **UNIQUE:** (line_item_id, shop_domain)

**`mirador_product_costs`** — Catálogo de costos por SKU
- id, sku, variant_id, shop_domain
- cost_amount (costo unitario en UYU), vendor
- effective_from (DATE — cuándo aplica este costo)
- po_id, source ('purchase_order'/'import'/'manual'/'transfer'), created_at

**`sku_equivalencias`** — Aliases de SKU (viejo→nuevo)
- id, sku_viejo, product_title, sku_nuevo, fecha_agregado, notas

### 9.2 Compras e Inventario

**`mirador_purchase_orders`** — Órdenes de compra
- id, po_number (único por BU), business_unit_id, company_id, vendor_id, vendor_name
- payment_term_id, currency, status (draft/confirmed/received/partially_received)
- expected_date, received_date, subtotal, tax_amount, total_amount, advance_amount, received_amount
- includes_vat, notes, created_by

**`mirador_purchase_order_items`** — Líneas de OC
- id, po_id, sku, product_title, variant_title
- shopify_product_id, shopify_variant_id, shopify_inventory_item_id, shopify_location_id
- quantity_ordered, unit_cost, line_total, expected_date

**`mirador_goods_receipts`** — Recepciones de mercancía
- id, po_id, expense_id, receipt_date, quantity_received, notes, created_by, expense_number

**`mirador_purchase_advances`** — Anticipos de OC
- id, po_id, advance_date, amount_uyu, payment_method_id, partner_id, reference

**`mirador_movements`** — Flujos financieros e inventario
- id, company_id, business_unit_id, movement_type, document_type, document_id
- amount, quantity, status, parent_movement_id, movement_date

### 9.3 Finanzas

**`mirador_vendors`** — Proveedores
- id, business_unit_id, company_id, name, legal_name, rut, email, phone
- vendor_type, payment_term_id, currency_default, is_active

**`mirador_expenses`** — Gastos
- id, business_unit_id, vendor_id, vendor_name, expense_number, expense_date, accrual_date, due_date
- amount_original, currency_original, exchange_rate, amount_uyu
- concept, cost_center, description, reference_number, includes_vat, vat_amount, affects_pl, partner_id

**`mirador_expense_payments`** — Pagos de gastos
- id, expense_id, amount, payment_date, payment_method_id, partner_id, due_date_id, reference

**`mirador_expense_due_dates`** — Fechas de vencimiento de gasto
- id, expense_id, due_date, amount, description, sort_order

**`mirador_expense_types`** — Tipos de gasto
- id, name, is_active

**`mirador_payment_methods`** — Métodos de pago
- id, name, shopify_gateway, is_active

**`mirador_payment_terms`** — Términos de pago
- id, name, days_to_pay, is_active

**`mirador_vat_rates`** — Tasas IVA
- id, rate_percent (0/10/22), description, is_active

**`mirador_partners`** — Socios / cuentas internas
- id, business_unit_id, name, entity_type, is_active

**`mirador_partner_transactions`** — Transacciones entre socios
- id, partner_id, transaction_type, amount_uyu, transaction_date, reference

**`mirador_receivables`** — Cuentas por cobrar
- id, business_unit_id, debtor_id, partner_id, amount_original, currency_original, exchange_rate, amount_uyu, due_date

**`mirador_receivable_payments`** — Cobros
- id, receivable_id, amount_uyu, payment_date, notes

**`mirador_loans`** — Préstamos
- id, business_unit_id, partner_id, principal_uyu, interest_rate_pct, currency
- start_date, maturity_date, num_installments, status, is_auto_debit

**`mirador_loan_installments`** — Cuotas de préstamo
- id, loan_id, installment_num, due_date, amount_uyu, status, generated_expense_id

### 9.4 Marketing

**`mirador_meta_campaigns`** — Campañas Meta Ads (snapshot diario)
- id, campaign_id (Meta ID), campaign_name, campaign_type, status
- budget_amount, company_id, business_unit_id, snapshot_date
- spend_usd, conversions, cost_per_result, result_type, exchange_rate_usd

**`mirador_meta_adsets`** — Adsets (diario)
- id, adset_id, adset_name, campaign_id, snapshot_date
- spend_usd, impressions, clicks, ctr, cpc, cpm, cpa_usd, conversions, result_type
- alert_level (ok/warning/critical), alert_reasons (JSON), company_id, business_unit_id

**`mirador_meta_ads`** — Ads individuales (diario, granular)
- id, ad_id, ad_name, adset_id, campaign_id, snapshot_date
- creative_type (image/carousel/video)
- spend_usd, impressions, clicks, conversions, ctr, cpc, cpm, cpa_usd
- video_p25/50/75/100_watched_actions
- alert_level, alert_reasons, company_id, business_unit_id

**`mirador_meta_thresholds`** — Umbrales de alerta
- id, metric (roas/ctr/frequency/cpm/cpa_usd), warning_value, critical_value, direction (below/above)

**`mirador_google_campaigns`** — Campañas Google Ads
- campaign_id (PK), campaign_name, campaign_type, status, budget_amount, shop_domain

**`mirador_google_daily_summary`** — Stats diarios Google Ads
- id, date, campaign_id, shop_domain
- impressions, clicks, cost_usd, conversions, conversion_value, ctr, avg_cpc, roas
- impression_share, lost_is_budget, lost_is_rank, exchange_rate_usd

**`mirador_google_keywords`** — Keywords Google Ads
- id, date, campaign_id, ad_group_id, keyword_text, match_type
- quality_score, impressions, clicks, cost_usd, conversions, ctr, avg_cpc, shop_domain

### 9.5 Operaciones

**`cebala_dim_anuncios`** — Anuncios internos
- id, titulo, comentario, tipo, fecha_creacion, fecha_vigencia_hasta
- creado_por, activo, tienda (cebala/mushkana/ambas), pinned, privado

**`cebala_dim_anuncio_lecturas`** — Tracking de lectura de anuncios
- id, anuncio_id, user_name, fecha_lectura

**`cebala_dim_anuncio_destinatarios`** — Destinatarios de anuncios
- id, anuncio_id, user_name

**`mirador_tasks`** / **`cebala_dim_tareas`** — Tareas
- id, business_unit_id, title, description, assigned_to, created_by
- due_date, urgency (amarillo/rojo), status (pendiente/en_progreso/resuelta)
- shopify_order_id, order_number

**`mirador_task_comments`** / **`cebala_fact_tarea_comentarios`** — Comentarios de tareas
- id, task_id, comment, author, created_at

**`mirador_employees`** / **`cebala_dim_empleados`** — Empleados
- id, business_unit_id, first_name, last_name, birth_date, start_date, weekly_hours, is_active

**`mirador_overtime`** / **`cebala_fact_horas_extras`** — Horas extras
- id, business_unit_id, employee_id, date, hours, cause_id, comment, registered_by

**`mirador_shrinkage`** — Mermas/daños
- id, business_unit_id, order_id, order_number, sku, product_title, variant_title
- sale_cost, comment, photo_url, type (cambio/daño/robo/etc)
- coupon_generated, coupon_code, coupon_amount, notified_to, created_by

**`mirador_webhook_logs`** — Logs de webhooks
- id, platform, event_type, source_id, business_unit
- status (ok/error/skipped), duration_ms, error_message, payload_size, received_at

**`Procedures`** — Knowledge base
- Id, Title, Slug (UNIQUE), Brand (general/cebala/mushkana), Category
- Content (NVARCHAR(MAX)), Tags, SourceType (manual/pdf), SourcePdfUrl
- IsActive, CreatedBy, UpdatedBy, CreatedAt, UpdatedAt

### 9.6 Datos de Referencia

**`mirador_companies`** — CEBALA_CO, MUSHKANA_CO

**`mirador_business_units`** — Unidades de negocio
- Pre-seeded: cebala_online (id=3), mushkana_online (id=4), cebala_pos (id=5), mushkana_pos (id=6), cebala_admin (id=7), mushkana_admin (id=8)
- slug UNIQUE (ej. 'cebala_online')
- Filtro marca: `bu.slug LIKE 'cebala%'` o `'mushkana%'`

---

## 10. Arquitectura Frontend

### 10.1 Estructura de carpetas

```
src/
  auth/           msalConfig.js (init MSAL, checkAdmin, checkEncargadoOrAdmin, getRoles)
  services/       api.js (120+ funciones, todas las llamadas al backend)
  pages/          una página por módulo (30 páginas)
  components/
    layout/       Sidebar.jsx, TopBar.jsx
    ui/           DataTable.jsx, Badge.jsx, FilterButton.jsx, KpiCard.jsx, MarkdownRenderer.jsx
    charts/       wrappers ECharts (BarChart, LineChart, MonthlyActivityChart)
    customers/    CustomerDrawer y componentes de análisis
    monitor/      HoldingModal, TiposModal, CausasModal, BusinessUnitsModal,
                  PaymentMethodsModal, PaymentTermsModal, AnuncioFormModal, etc.
    modals/       ExpenseTypesModal, VatRatesModal
  hooks/          useAutoRefresh.js, useEscapeKey.js, etc.
```

### 10.2 Routing (`src/App.jsx`)

Routing por `page=` query param. Cada ruta protegida verifica roles con MSAL.

### 10.3 Páginas implementadas

| Componente | page= | Rol mínimo | Descripción |
|-----------|-------|------------|-------------|
| LoginPage | - | - | Login Azure AD |
| NoAccessPage | - | - | Sin acceso |
| MonitorPage | monitor / (default) | cualquiera | Dashboard órdenes Cebala+Mushkana |
| CockpitPage | cockpit | Admin | KPIs ejecutivos y alertas |
| SalesOrdersPage | ordenes | cualquiera | Lista + detalle de órdenes de venta |
| NewOrderPage | nueva-orden | Encargado | Crear orden manual |
| ActivityPage | actividad | Admin | Tendencias de ventas |
| CuponesPage | cupones | Admin | Cupones Itaú |
| AnunciosPage | anuncios | cualquiera | Leer/gestionar anuncios internos |
| TareasPage | tareas | cualquiera | Tablero de tareas |
| HorasExtrasPage | horas | Encargado | Horas extras por empleado |
| MermasPage | mermas | Encargado | Mermas y daños |
| CalidadPage | calidad | cualquiera | Calidad de atención en mensajería |
| EmpleadosPage | empleados | Admin | RRHH — empleados |
| ProcedimientosPage | procedimientos | cualquiera | Knowledge base |
| ProcedimientoForm | procedimiento-form | cualquiera | Crear/editar procedimiento |
| ExpensesPage | gastos | Admin | Gestión de gastos |
| VendorsPage | vendors | Admin | Proveedores |
| PartnersPage | partners | Admin | Cuentas de socios |
| BalancePage | balance | Admin | Balance P&L con sección COGS |
| PurchaseOrdersPage | compras | Admin | Órdenes de compra |
| GoodsReceiptsPage | recepciones | Encargado | Recepciones + ajuste stock Shopify |
| ReceivablesPage | receivables | Encargado | Cuentas por cobrar |
| LoansPage | loans | Encargado | Préstamos |
| WebhookLogsPage | webhooks | Admin | Audit trail de webhooks |
| MarketingPage | marketing | Admin | Meta Ads + Google Ads |
| MovementsPage | movimientos | Admin | Movimientos financieros/inventario |
| CustomersPage | clientes | Admin | RFM, cohorts, cross-brand, lista |
| CostsPage | costos | Admin | COGS por orden: sin costear / costeadas |
| ProductCostsPage | product-costs | Admin | Vista por SKU: asignar costos en bulk |

### 10.4 Tokens de diseño Tailwind

**NUNCA hardcodear colores** — usar siempre los tokens:

```js
// ❌ Incorrecto
className="text-gray-500 bg-gray-100"

// ✅ Correcto
className="text-ink-muted bg-surface"
```

```
cebala:    DEFAULT #534AB7  light #EEEDFE   border #7F77DD
mushkana:  DEFAULT #0F6E56  light #E1F5EE   border #0F6E56

brand.green    #3B6D11   brand.green-bg    #EAF3DE
brand.amber    #854F0B   brand.amber-bg    #FAEEDA
brand.red      #A32D2D   brand.red-bg      #FCEBEB
brand.blue     #185FA5   brand.blue-bg     #E6F1FB

surface:   DEFAULT #f5f5f3  card #ffffff  hover #fafaf8
           border  #e0e0d8  border-light  #f0f0e8

ink:       DEFAULT #1a1a1a  muted #888888  faint #aaaaaa  caption #cccccc

shadows:   card  (0 1px 4px rgba(0,0,0,.06))
           modal (0 8px 40px rgba(0,0,0,.12))

fonts:     font-sans = Inter | font-mono = DM Mono | font-syne = Syne
border:    0.5px default
```

Excepción aceptable: sidebar `bg-[#1C1F26]` (único color hardcodeado del layout).

### 10.5 Componente DataTable

Tabla genérica con alineación declarativa. **Usar siempre** en lugar de `<table>` manual.

```jsx
import DataTable from '../components/ui/DataTable'

<DataTable
  columns={[
    { key: 'sku',     label: 'SKU',     align: 'left' },
    { key: 'revenue', label: 'Revenue', align: 'right',
      render: r => '$' + Math.round(r.revenue).toLocaleString('es-UY') },
  ]}
  data={rows}
  loading={loading}
  emptyMessage="Sin datos"
  getKey={r => r.id}
  // Para filas expandibles, renderRow retorna un fragment con 2 <tr>:
  renderRow={(row, i, cols) => (
    <ExpandableRow key={row.id} row={row} colSpan={cols.length} />
  )}
/>
```

Props: `columns[]` (key, label, align, render?, className?, width?), `data[]`, `loading`, `emptyMessage`, `getKey`, `renderRow`, `footer`.

### 10.6 Patrones UI frecuentes

```jsx
// Pill toggle
<div className="flex rounded-lg border border-surface-border overflow-hidden">
  {['Sin costo', 'Con costo'].map((v, i) => (
    <button key={i} onClick={() => setView(i)}
      className={`px-3 py-1.5 font-mono text-[11px] transition-colors ${
        view === i ? 'bg-cebala text-white' : 'bg-white text-ink-muted hover:bg-surface-hover'
      }`}>{v}</button>
  ))}
</div>

// Stat card
<div className="bg-white border border-surface-border rounded-lg shadow-card p-4">
  <p className="font-mono text-[10px] text-ink-faint uppercase tracking-wider mb-1">Label</p>
  <p className="font-mono text-[22px] font-semibold text-ink">{value}</p>
</div>

// Error inline
<div className="px-4 py-3 rounded-lg bg-red-50 border border-red-200 font-mono text-[11px] text-red-600">
  {error}
</div>
```

### 10.7 Sidebar — agregar items

```jsx
// src/components/layout/Sidebar.jsx, sección Finanzas (~línea 122)
{admin && <NavItem icon="ti-tag" label="Mi módulo" page="mi-modulo" {...shared} />}
```

### 10.8 Routing — agregar páginas

```jsx
// src/App.jsx: importar y agregar en la función que renderiza páginas
import MiPagina from './pages/MiPagina'
// ...
if (page === 'mi-modulo' && admin) return <MiPagina />
```

### 10.9 API — funciones de `src/services/api.js`

Todas las funciones usan `apiFetch` que añade `Authorization: Bearer <token>` automáticamente.

**Por módulo:**
- **Dashboard/Órdenes:** fetchDashboard, setHoldingReason, addOrderNote, fetchHoldingReasons, addHoldingReason, deleteHoldingReason
- **Actividad:** fetchActivity, fetchActivityMonthly
- **Ventas:** fetchSalesOrders, fetchSalesOrderDetail, searchCustomers, createCustomer, fetchSkus, createManualOrder, updateOrderStatus
- **Clientes:** fetchCustomersSummary, fetchCustomersRfm, fetchCustomersCohorts, fetchCustomersCrossBrand, fetchCustomersList, fetchCustomerOrders
- **Anuncios:** fetchAnuncios, createAnuncio, updateAnuncio, markAnuncioRead, unmarkAnuncioRead, fetchAnuncioLecturas, fetchTiposAnuncio, addTipoAnuncio, deleteTipoAnuncio, fetchSystemUsers
- **Tareas:** fetchTareas, fetchTarea, createTarea, updateTarea, addTareaComentario
- **Empleados:** fetchEmpleados, createEmpleado, updateEmpleado, fetchEmployees
- **Horas extras:** fetchHorasExtras, createHoraExtra, updateHoraExtra, deleteHoraExtra, fetchCausasHoraExtra, addCausaHoraExtra, deleteCausaHoraExtra
- **Mermas:** fetchMermas, createMerma, deleteMerma, fetchMermaSkus, fetchMermaNotificados, addMermaNotificado, deleteMermaNotificado, uploadMermaFoto
- **Mensajería:** fetchDashboardMessages, fetchConvQuality, fetchConvPhoneCheck, fetchConvByPhone, fetchConvMessages, resolveNames, fetchConvEvents, closeConv, sendConvMessage
- **Procedimientos:** fetchProcedures, fetchProcedure, createProcedure, updateProcedure, deleteProcedure, processProcedurePdf
- **Datos maestros:** fetchCompanies, fetchBusinessUnits, createBusinessUnit, updateBusinessUnit, fetchPaymentMethods, createPaymentMethod, updatePaymentMethod, fetchPaymentTermsList, createPaymentTerm, updatePaymentTerm, fetchFinancePaymentMethods, fetchFinancePaymentTerms, fetchVatRates, createVatRate, updateVatRate, fetchExpenseTypes, createExpenseType, updateExpenseType
- **Finanzas:** fetchVendors, createVendor, updateVendor, fetchExpenses, fetchExpenseDetail, createExpense, createExpensePayment, updateExpense, deleteExpense, deleteExpensePayment, fetchPartners, fetchPartnerTransactions, createPartnerTransaction, updatePartnerTransaction, fetchReceivables, fetchReceivableDetail, createReceivable, createReceivablePayment, fetchLoans, fetchLoanDetail, createLoan, payLoanInstallment, fetchBalance, fetchExchangeRate, fetchMovements, reverseMovement, fetchDocumentFlow
- **Compras:** fetchPurchaseOrders, fetchPurchaseOrderDetail, createPurchaseOrder, updatePurchaseOrder, updatePurchaseOrderStatus, createPurchaseAdvance, reverseAdvance, fetchGoodsReceipts, createGoodsReceipt, confirmGoodsReceipt, reverseGoodsReceipt
- **COGS:** fetchSkuCostInfo, fetchOrderCosts, importCosts, runBackfillPremigration, fetchUncostedOrders, fetchCostedOrders, assignCosts, fetchProductCosts, assignSkuCost
- **Marketing Meta:** fetchMetaSummary, fetchMetaCampaigns, fetchMetaAdsets, fetchMetaAds, fetchMetaThresholds, updateMetaThreshold, triggerMetaIngest, triggerMetaAdsIngest
- **Marketing Google:** fetchGoogleAdsSummary, fetchGoogleAdsCampaigns, fetchGoogleAdsKeywords, fetchGoogleAdsDaily, fetchGoogleAdsComparison, triggerGoogleAdsIngest, fetchMarketingRevenue
- **Admin:** fetchWebhookLogs, fetchPaymentMethods, searchOrders, fetchDashboardStock

---

## 11. COGS — Lógica Detallada

### Standard cost
Para líneas sin costo real (`is_estimated=1`), el costo estándar se calcula como:
```
standard_cost_uyu = unit_price / 2.2   (markup estándar Cebala)
```
Columna `standard_cost_uyu` existe en `mirador_order_line_costs`.

### P&L — desglose de COGS
El endpoint `GET /balance` retorna:
```json
{
  "cogs":         12500,
  "cogs_real":    9800,
  "cogs_estandar": 2700,
  "gross_margin": 37500,
  "gross_margin_pct": 75.0,
  "pct_cobertura": 78.4,
  "lineas_reales": 145,
  "lineas_estandar": 40
}
```
`pct_cobertura` = % de líneas con costo real (excluye shipping_passthrough).

### `assign-sku` — flujo
1. UPDATE `mirador_order_line_costs` SET is_estimated=0, unit_cost_uyu=X para todas las líneas del SKU en el período
2. UPSERT `mirador_product_costs` con source='manual'

---

## 12. Integraciones Externas

| Sistema | Cómo | Propósito |
|---------|------|-----------|
| **Shopify Cebala** | REST + GraphQL, token en `SHOPIFY_ACCESS_TOKEN` | Órdenes webhook, stock, notas |
| **Shopify Mushkana** | REST + GraphQL, token en `MUSHKANA_ACCESS_TOKEN` | Ídem para Mushkana |
| **Meta Graph API** | v20.0, token en `META_ADS_TOKEN` | Campaigns, adsets, ads (daily ingest) |
| **Google Ads API** | Customer API con service account | Campaigns, keywords, daily summary |
| **BCU (Banco Central UY)** | HTTP fetch, fallback a open.er-api | Tipo de cambio USD→UYU (cacheado por día) |
| **Anthropic Claude** | SDK Python, clave en `ANTHROPIC_API_KEY` | PDF→procedimiento, análisis conversaciones |

---

## 13. Seguridad

- **Secrets:** Solo en Azure App Settings o `local.settings.json` (gitignored). NUNCA en código, NUNCA en logs.
- **SQL injection:** Parámetros siempre con `%s`. Solo f-strings para fragmentos SQL con valores hardcodeados (nunca de usuario).
- **Auth:** Easy Auth valida JWT de Entra ID antes de que llegue al código Python. El código además verifica roles explícitamente con `require_roles`.
- **Webhooks Shopify:** ANONYMOUS por diseño (Shopify no puede enviar JWT). Validar HMAC-SHA256 del header `X-Shopify-Hmac-SHA256` (pendiente implementar).
- **CORS:** `*` para todos los orígenes (API interna, solo accesible con JWT de Entra ID).

---

## 14. Bugs Conocidos y Decisiones de Diseño

1. **`require_roles` retorna bool, no HttpResponse** — llamar siempre como `if not require_roles(req, ROLE): return forbidden()`. Si se hace `err = require_roles(...)` y `if err: return err`, retorna `True` al Azure host → 500.

2. **Filtro de marca en `_slug_filter`:** sin token = `require_roles` retorna False → endpoints pasan en producción (Easy Auth en modo "allow anonymous"). Esto es intencional para webhooks Shopify que no tienen JWT. Endpoints sensibles deben verificar rol explícitamente.

3. **`_ensure_all_tables()` sin argumentos:** no acepta `conn` como parámetro — usa su propia conexión interna.

4. **Thread-local connection:** no es un pool real. Con alta concurrencia puede quedarse sin conexiones. Monitorear DTU si el tráfico crece.

5. **Tipo de cambio hardcodeado:** fallback a 40.0 UYU/USD si fallan los dos APIs. Revisar periódicamente.

---

## 15. Estado Actual y Pendientes

### En producción ✅
- Monitor de órdenes Cebala + Mushkana
- COGS por línea con backfill histórico
- Balance P&L con COGS real + estándar
- CostsPage: Sin costear / Costeadas
- ProductCostsPage: vista por SKU con asignación bulk
- Marketing: Meta Ads + Google Ads con alertas
- Análisis de clientes: RFM, cohorts, cross-brand
- Compras: PO + recepciones con ajuste de inventario Shopify
- Finanzas completo: gastos, vendors, partners, receivables, préstamos
- Mensajería omnicanal con análisis IA
- Knowledge base de procedimientos (PDF → Claude)
- RRHH: empleados, horas extras

### Pendientes / En progreso
- Validación HMAC-SHA256 en webhooks Shopify
- Cockpit ejecutivo (reporte diario por email)
- Ingesta Soft Restaurant
- Curvas de talle para Mushkana
- Pool de conexiones real (DBUtils PooledDB) cuando crezca la concurrencia
- Mover token cPanel a variable de entorno `CPANEL_API_TOKEN`

---

## 16. Coceo — Capa de inteligencia estratégica

### Qué es y para qué sirve

Coceo es la capa de memoria estratégica del BOS: el lugar donde el CEO
(Cebala o Mushkana) piensa en voz alta con Claude — ideas, reuniones,
decisiones, proyectos, pendientes — y esas notas quedan persistidas y
disponibles en cualquier sesión futura, en vez de perderse en un chat que
termina. No reemplaza al dashboard operativo del BOS; es la contraparte
"ejecutiva" de ese sistema, pensada para conversación libre en vez de
formularios.

### Cómo se integra con el BOS

Corre sobre la misma infraestructura que el resto del BOS — mismo Azure
Functions app (`mirador-bos-prod`), misma base (`shopify_db`), mismo patrón
de blueprints (`blueprints/coceo.py`). No es un sistema aparte: es un
blueprint más, con su propia autenticación (`X-Coceo-Key` +
`X-Coceo-Email`, independiente de Easy Auth/roles del dashboard) porque lo
consume un agente de IA, no un usuario logueado en el navegador. El
aislamiento entre Cebala y Mushkana se resuelve server-side por email
(tabla `mirador_coceo_usuarios`), nunca por un valor que mande el cliente.

Se accede vía dos servidores MCP (`coceo_mcp.py` local por stdio,
`coceo_mcp_server.py` remoto por HTTP/SSE en Azure Container Apps) que
son, en esencia, clientes HTTP de `blueprints/coceo.py` — no tienen acceso
directo a la base.

**Documentación técnica completa** (endpoints, tablas, auth, MCP server,
multi-brand): [`docs/COCEO_API.md`](docs/COCEO_API.md).

### Roadmap — qué le falta para ver el resto del BOS

Hoy Coceo es memoria pura (lo que el CEO escribe/dicta); todavía no lee los
datos operativos que ya existen en el resto del sistema. F1 = disponible
ahora, F2 = próximo paso planeado.

| Módulo BOS      | Disponible en Coceo F1 | Disponible en Coceo F2 |
|------------------|:----------------------:|:----------------------:|
| Shopify orders   | ✗ *(placeholder sin datos — ver nota)* | ✓ |
| Gastos           | ✗                       | ✓                       |
| Inventario       | ✗                       | ✓                       |
| Marketing Meta   | ✗                       | ✓                       |
| Clientes RFM     | ✗                       | ✓                       |
| COGS             | ✗                       | ✓                       |

*Shopify orders:* `vw_mirador_coceo_ai_context` y `GET /coceo/context` ya
tienen el campo `shopify` reservado (`record_type: "shopify_snapshot"`),
pero la vista no tiene ninguna fuente que lo alimente todavía — hoy siempre
devuelve `{}`. Es el gancho listo para F2, no una feature F1 activa.

---

Documentación completa del sistema:
https://github.com/jromero044-debug/Proyecto-BOS/blob/main/BOS_Master_Prompt_v11.md
Leer antes de cualquier tarea de arquitectura.
