# WIP / Materia Prima — Documentación técnica

Módulo de tracking de materia prima e insumos en proceso ("work in progress"),
montado sobre la misma infraestructura del BOS (Azure Functions Python,
Azure SQL `shopify_db`). Código fuente: [`blueprints/wip.py`](../blueprints/wip.py).
Este documento es la referencia técnica completa; para contexto de producto
ver la sección "WIP / Materia Prima" en
[`BOS_Master_Prompt_v11.md`](../BOS_Master_Prompt_v11.md).

## 1. Qué resuelve

Mushkana importa blanks (remeras, buzos) desde China y los manda a bordar/
estampar al vendor **Tipy**; Cebala importa maderas desde China y las manda a
distintos artesanos/talleres. En ambos casos el producto terminado termina
siendo un SKU de Shopify, pero todo lo anterior — materia prima, tránsito,
importación, procesamiento externo — no vivía en ningún sistema. Este módulo
lo trackea de punta a punta, con costeo real (compra + flete + seguro +
aduana + servicios) prorrateado por lote.

## 2. Flujo completo

```
Orden de Compra (OC)                              wip_purchase_orders
   │  confirm → nace stock en ubicación "China"    (lote interino = po_number)
   │
   ├── Despacho (embarque parcial, N por OC)       wip_despachos
   │     │  ship    → China → En Tránsito
   │     │  arrive  → En Tránsito → Depósito Fiscal
   │     │  gastos  → flete/seguro, se guardan sin capitalizar (applied=0)
   │     │
   │     └── Importación (parcial, N por despacho) wip_importaciones
   │           │  confirm → genera LOTE FINAL "{po_number}/{importacion_number}"
   │           │            prorratea gastos de despacho + propios al ledger
   │           │            Depósito Fiscal → destino (Moova/Mirador/etc.)
   │           └  reverse  → bloqueado si el lote ya fue consumido aguas abajo
   │
   └── (todos los despachos/importaciones de esa OC)

Orden de Servicio (OS)                             wip_service_orders
   │  confirm  → reserva stock, lo mueve a la ubicación 'processor' del vendor
   │  start/unprocess → transición de estado pura (confirmed ↔ in_process)
   │  receive → libera la reserva, mueve stock del vendor al destino elegido
   └  unreceive → bloqueado si el lote ya fue consumido por una transformación

Transformación                                     wip_transformations
   │  confirm → consume inputs de wip_stock, calcula unit_cost_final,
   │            ajusta INVENTARIO REAL de Shopify (REST inventory_levels/adjust)
   └  reverse → siempre reversible, revierte Shopify + stock + ledger
```

**Todas las acciones "forward" tienen su reversa simétrica** (`unconfirm`,
`unship`, `unarrive`, `reverse`, `unprocess`, `unreceive`): crean un
`wip_movement` inverso (nunca modifican el original), revierten `wip_stock`
en la misma transacción, y fallan con `400` si hay dependencias aguas abajo
que lo impiden (ej. no podés reversar una importación si su lote ya fue
consumido por una OS o transformación).

## 3. Auth

Igual que el resto del BOS: `dual_auth(req, ROL)` en cada handler. Patrón de
niveles:

| Acción | Rol |
|---|---|
| `GET` (listas y detalle) | `OPERATIVO` |
| Crear (OC, despacho, importación, OS, transformación, maestros) | `ADMIN` (maestros) / `ENCARGADO` (documentos) |
| Confirmar (`confirm`, `ship`, `arrive`, `start`, `receive`) | `ENCARGADO` |
| Reversar (`unconfirm`, `unship`, `unarrive`, `reverse`, `unprocess`, `unreceive`) | `ADMIN` |

Reversar siempre pide un rol más alto que la acción que reversa — mismo
criterio asimétrico que `purchasing.py` (`confirm_goods_receipt` = ENCARGADO,
`reverse_goods_receipt` = ADMIN).

## 4. Endpoints

Base URL: `https://mirador-bos-prod.azurewebsites.net/api`. Todos aceptan
`OPTIONS` para CORS preflight y responden `{"ok": bool, ...}`.

### 4.1 Maestros

| Endpoint | Método | Descripción |
|---|---|---|
| `/wip/items` | GET, POST | Catálogo de materia prima (`code` único) |
| `/wip/items/{item_id}` | PUT | Editar ítem |
| `/wip/locations` | GET, POST | Ubicaciones (China, Tránsito, Depósito Fiscal, Moova, Mirador, vendors `processor`) |
| `/wip/locations/{location_id}` | PUT | Editar ubicación |
| `/wip/services` | GET, POST | Catálogo de servicios (bordado, estampado, etc.), con `unit_cost` |
| `/wip/services/{service_id}` | PUT | Editar servicio |
| `/wip/bom` | GET, POST | BOM (receta) por SKU Shopify |
| `/wip/bom/{bom_id}` | GET | Detalle con líneas |
| `/wip/bom/{bom_id}/lines` | POST | Agregar línea (material o servicio) |
| `/wip/bom/{bom_id}/lines/{line_id}` | PUT, DELETE | Editar/eliminar línea |

### 4.2 Orden de Compra

| Endpoint | Método | Rol | Descripción |
|---|---|---|---|
| `/wip/purchase-orders` | GET, POST | OPERATIVO / ADMIN | Lista / crea OC (`po_number` autogenerado al crear, formato `OC-MP-{BRAND}-0001`) |
| `/wip/purchase-orders/{po_id}` | GET, PUT | OPERATIVO / ADMIN | Detalle (con `can_unconfirm`) / edita header+items (solo draft) |
| `/wip/purchase-orders/{po_id}/confirm` | POST | ENCARGADO | Nace stock en ubicación `supplier` (China) de la marca |
| `/wip/purchase-orders/{po_id}/unconfirm` | POST | ADMIN | Revierte — bloqueado si hay despachos ya embarcados |

### 4.3 Despachos

| Endpoint | Método | Rol | Descripción |
|---|---|---|---|
| `/wip/purchase-orders/{po_id}/despachos` | GET, POST | OPERATIVO / ENCARGADO | Lista / crea despacho (`DSP-{BRAND}-0001`) — requiere OC `confirmed` |
| `/wip/despachos/{despacho_id}` | GET | OPERATIVO | Detalle: items, gastos, importaciones, `can_unship`/`can_unarrive` |
| `/wip/despachos/{despacho_id}/gastos` | POST | ENCARGADO | Registra flete/seguro (`applied=0`, se capitaliza en la importación) |
| `/wip/despachos/{despacho_id}/ship` | POST | ENCARGADO | China → En Tránsito |
| `/wip/despachos/{despacho_id}/unship` | POST | ADMIN | Revierte — bloqueado si ya hay importaciones creadas |
| `/wip/despachos/{despacho_id}/arrive` | POST | ENCARGADO | En Tránsito → Depósito Fiscal |
| `/wip/despachos/{despacho_id}/unarrive` | POST | ADMIN | Revierte — bloqueado si ya hay importaciones creadas |

### 4.4 Importaciones

| Endpoint | Método | Rol | Descripción |
|---|---|---|---|
| `/wip/despachos/{despacho_id}/importaciones` | GET, POST | OPERATIVO / ENCARGADO | Lista / crea (parcial permitido) — requiere despacho `en_deposito_fiscal` o `parcialmente_importado` |
| `/wip/importaciones/{importacion_id}` | GET | OPERATIVO | Detalle: items, gastos, `can_reverse` |
| `/wip/importaciones/{importacion_id}/gastos` | POST | ENCARGADO | Gasto propio (aduana, IVA, honorarios, almacenaje) |
| `/wip/importaciones/{importacion_id}/confirm` | POST | ENCARGADO | Genera lote final, capitaliza costos (ver sección 5), mueve Depósito Fiscal → destino |
| `/wip/importaciones/{importacion_id}/reverse` | POST | ADMIN | Revierte ledger+stock — bloqueado si el lote ya fue consumido por una OS/transformación |
| `/wip/stock` | GET | OPERATIVO | Posición de stock (filtros `brand`, `location_id`, `lote`, `category`) |
| `/wip/lote/cost?lote=` | GET | OPERATIVO | Desglose del ledger + `avg_unit_cost` de un lote (query param porque el lote tiene `/` en el nombre) |

### 4.5 Órdenes de Servicio

| Endpoint | Método | Rol | Descripción |
|---|---|---|---|
| `/wip/service-orders` | GET, POST | OPERATIVO / ENCARGADO | Lista / crea (`OS-{BRAND}-0001`) — cada línea de `items` requiere `lote` |
| `/wip/service-orders/{so_id}` | GET | OPERATIVO | Detalle: items, servicios, `can_unconfirm`/`can_unprocess`/`can_unreceive` |
| `.../confirm` | POST | ENCARGADO | Mueve stock a la ubicación `processor` del vendor, 100% reservado ahí |
| `.../unconfirm` | POST | ADMIN | Revierte, stock vuelve a `from_location_id` |
| `.../start` | POST | ENCARGADO | `confirmed` → `in_process` (transición pura) |
| `.../unprocess` | POST | ADMIN | `in_process` → `confirmed` |
| `.../receive` | POST | ENCARGADO | Libera reserva, mueve stock del vendor al `destination_location_id` elegido |
| `.../unreceive` | POST | ADMIN | Revierte — bloqueado si el lote ya fue consumido por una transformación |

### 4.6 Transformaciones

| Endpoint | Método | Rol | Descripción |
|---|---|---|---|
| `/wip/transformations` | GET, POST | OPERATIVO / ENCARGADO | Lista / crea (`TRF-{BRAND}-0001`) — `bom_id` auto-sugiere `quantity` de los inputs que matcheen |
| `/wip/transformations/{transformation_id}` | GET | OPERATIVO | Detalle: inputs, outputs, `can_reverse` (siempre `true` si confirmed) |
| `.../confirm` | POST | ENCARGADO | Consume inputs, calcula `unit_cost_final`, ajusta inventario real en Shopify |
| `.../reverse` | POST | ADMIN | Siempre reversible — revierte Shopify + stock + ledger |

### 4.7 Auditoría

| Endpoint | Método | Rol | Descripción |
|---|---|---|---|
| `/wip/movements` | GET | OPERATIVO | Log completo (filtros `brand`, `type`, `lote`, `location_id`, `date_from/to`), TOP 500 |

## 5. Lógica de negocio no obvia

**Numeración de documentos** — generada en Python con retry-on-conflict
(`_next_wip_number`), **no** con stored procedures como hace `purchasing.py`
(esas procs viven fuera del repo, son opacas). Mismo patrón que
`numero_lote` en `cupones.py`: recalcula `MAX(...)+1` en cada intento,
reintenta hasta 3 veces si choca contra el `UNIQUE`. Formato
`{PREFIJO}-{CEBA|MUSH}-0001`.

**Lote interino vs. lote final** — antes de la importación, el stock en
China/Tránsito/Depósito Fiscal se trackea con `lote = po_number` (no existe
lote real todavía). Recién `POST /wip/importaciones/{id}/confirm` genera el
lote definitivo `{po_number}/{importacion_number}` y "re-lotea" el stock
correspondiente al destino.

**Costeo prorrateado con importaciones parciales** — un despacho puede
importarse en varias tandas. Cada gasto de despacho (flete, seguro) se
prorratea por la fracción que **esa** importación representa sobre la
cantidad **total** del `despacho_item` (no sobre lo pendiente), así que la
suma de las fracciones de todas las importaciones de un mismo despacho da
exactamente 100% del gasto — sin necesidad de trackear "monto restante por
aplicar". `wip_despacho_gastos.applied` pasa a `1` recién cuando el despacho
queda 100% importado (puede seguir en `0` aunque ya se haya capitalizado una
parte).

**Reservas de Órdenes de Servicio** — al `confirm`, el stock se **mueve
físicamente** a la ubicación `location_type='processor'` del vendor (no es
solo un flag) y queda 100% reservado ahí (`wip_stock.quantity_reserved` ==
`quantity_total` en esa fila) — nada más puede consumirlo mientras está en
proceso. Al `receive`, se libera la reserva y se mueve al destino final.

**`unit_cost_final` de una transformación** = (costo de materiales
consumidos, a `avg_unit_cost` de cada lote + costo de servicios de la OS
vinculada, si `service_order_id` viene) / cantidad total producida. El
costo de servicios también se loguea en `wip_lote_cost_ledger`
(`cost_type='servicio'`) prorrateado por línea de input.

**Ajuste de inventario Shopify** — usa el endpoint REST legacy
`inventory_levels/adjust.json` (no GraphQL), mismo patrón que
`_adjust_shopify_inventory` en `purchasing.py`: nunca lanza excepción, la
confirmación en DB **no se revierte** si Shopify falla (el error queda en
`shopify_errors` en la respuesta, para reintentar a mano). Requiere que el
caller pase `shopify_inventory_item_id` + `shopify_location_id` directamente
en cada output (no hay resolución server-side desde `shopify_variant_id`,
igual que hace `purchasing.py` con `shopify_inventory_item_id` en los items
de goods receipts). **Importante**: Shopify rechaza el ajuste con `422` sin
detalle si el ítem tiene `inventoryItem.tracked = false` — no es un bug del
módulo, hay que usar un variant con tracking de inventario activado.

**Transformaciones siempre reversibles** — a diferencia de importaciones
(que bloquean el `reverse` si el lote ya fue consumido aguas abajo), una
transformación se puede reversar sin condición — decisión explícita del
diseño original del módulo.

## 6. Tablas SQL

24 tablas, todas con prefijo `wip_*`, agregadas a `_ensure_all_tables()` en
`blueprints/shared.py` (mismo mecanismo idempotente `if 'tabla' not in et:
CREATE TABLE ... else: ALTER TABLE ADD ...` que el resto del BOS).

| Tabla | Rol |
|---|---|
| `wip_locations` | Ubicaciones (China, Tránsito, Depósito Fiscal, Moova, Mirador, vendors `processor`) |
| `wip_items` | Catálogo de materia prima |
| `wip_services` | Catálogo de servicios (bordado, estampado, etc.) con `unit_cost` |
| `wip_bom` / `wip_bom_lines` | Receta por SKU Shopify (líneas material o servicio) |
| `wip_purchase_orders` / `wip_po_items` | OC materia prima y sus líneas |
| `wip_despachos` / `wip_despacho_items` / `wip_despacho_gastos` | Embarques, sus líneas y gastos de flete/seguro |
| `wip_importaciones` / `wip_importacion_items` / `wip_importacion_gastos` | Importaciones (parciales), sus líneas y gastos propios |
| `wip_lote_cost_ledger` | Acumulador de costos por lote — fuente de verdad de `avg_unit_cost` (`SUM(total_amount)/MAX(total_units)` agrupado por `lote,item_id`) |
| `wip_movements` / `wip_movement_items` | Libro de movimientos inmutable (auditoría), con `reverses_movement_id` para las reversas |
| `wip_stock` | Posición actual: `quantity_total`, `quantity_reserved`, `avg_unit_cost`, únicos por `(item_id, location_id, lote)` |
| `wip_reservations` | Reservas activas/liberadas/canceladas (ligadas a Órdenes de Servicio) |
| `wip_service_orders` / `wip_so_items` / `wip_so_services` | OS, sus líneas de materiales y de servicios (`agreed_unit_cost`) |
| `wip_transformations` / `wip_transformation_inputs` / `wip_transformation_outputs` | Transformación WIP → Shopify SKU, con `unit_cost_final` |

`wip_transformation_outputs` incluye `shopify_variant_id`, `shopify_sku`,
`shopify_inventory_item_id`, `shopify_location_id` (estos dos últimos
agregados vía `ALTER TABLE` — necesarios para el ajuste real de inventario,
ver sección 5).

## 7. Historial

Construido completo el 2026-07-29 en 6 fases (schema+maestros → OC →
despachos → importaciones+costeo → OS+reservas → transformaciones+Shopify),
cada una probada contra producción antes de pasar a la siguiente, incluyendo
un ajuste real de inventario en un variant de prueba (revertido). Partió de
un documento de handoff que asumía stack Flask+stored procedures; se tradujo
al stack real del BOS (Azure Functions blueprints, numeración en Python en
vez de procs opacas) documentando cada desvío explícitamente.
