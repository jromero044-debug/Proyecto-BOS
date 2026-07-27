# Coceo API — Documentación técnica

Módulo de memoria estratégica para CEOs, montado sobre la misma infraestructura
del BOS (Azure Functions Python, Azure SQL `shopify_db`). Código fuente:
[`blueprints/coceo.py`](../blueprints/coceo.py). Este documento es la
referencia técnica completa; para contexto de producto ver la sección
"Coceo — Capa de inteligencia estratégica" en
[`BOS_Master_Prompt_v11.md`](../BOS_Master_Prompt_v11.md).

## 1. Arquitectura general

```
CEO (voz/texto)
   │
   ▼
Claude (Desktop, claude.ai, Cowork)
   │  MCP tool call
   ▼
Servidor MCP  ─┬─ coceo_mcp.py         (stdio, local, un solo usuario fijo)
               └─ coceo_mcp_server.py  (HTTP/SSE remoto, Azure Container Apps,
                                        cualquier CEO con su propio email)
   │  HTTPS + X-Coceo-Key + X-Coceo-Email
   ▼
mirador-bos-prod (Azure Functions)
   │  blueprints/coceo.py
   ▼
Azure SQL — shopify_db
   ├─ mirador_coceo_entries / meetings / decisions / projects / followups
   ├─ mirador_coceo_empresa / locales / operacional
   ├─ mirador_coceo_usuarios          (mapeo email → brand)
   └─ vw_mirador_coceo_ai_context     (vista agregada, ver sección 5)
```

Dos formas de llegar al mismo backend:

- **`coceo_mcp.py`** (raíz del repo) — servidor MCP por stdio, pensado para
  correr local vía Claude Desktop (`command`/`args`/`env` en
  `claude_desktop_config.json`). Requiere Python ≥3.10 y un venv separado del
  `.venv` del Function App (que está pinneado a 3.9).
- **`coceo_mcp_server.py`** (raíz del repo) — mismo set de tools, expuesto por
  HTTP/SSE. Corre como Azure Container App independiente (scale-to-zero,
  pay-per-use), pensado para conectarse desde **Settings → Connectors** de
  Claude Desktop/claude.ai sin instalar nada local. Ver sección 6.

Ninguno de los dos server MCP habla directo con la base — ambos son clientes
HTTP de `blueprints/coceo.py`, igual que cualquier otro consumidor de la API.

## 2. Autenticación

Dos headers en cada request, dos capas independientes:

| Header | Qué valida | Falla con |
|---|---|---|
| `X-Coceo-Key` | Secreto compartido fijo (env var `COCEO_SECRET_KEY`) — prueba que quien llama es un cliente autorizado | `401 Unauthorized` |
| `X-Coceo-Email` | Email del CEO que está usando la sesión — se busca en `mirador_coceo_usuarios` para resolver la marca (`brand`) | `403 Usuario no autorizado` |

```python
def _auth(req) -> bool:
    """Sin COCEO_SECRET_KEY configurada, rechaza siempre (fail-closed)."""
    return bool(COCEO_KEY) and req.headers.get("X-Coceo-Key", "") == COCEO_KEY

def _brand(req) -> str | None:
    email = req.headers.get("X-Coceo-Email", "").lower().strip()
    if not email:
        return None
    # SELECT brand FROM mirador_coceo_usuarios WHERE email=%s AND activo=1
    return brand_or_none
```

Todos los endpoints siguen el mismo orden de chequeo:

```python
if req.method == "OPTIONS": return func.HttpResponse(status_code=204, headers=_CORS)
if not _auth(req):          return _err("Unauthorized", 401)
brand = _brand(req)
if not brand:                return _err("Usuario no autorizado", 403)
```

**Importante:** la marca (`cebala` / `mushkana`) **nunca** se manda desde el
cliente — se deriva server-side del email. Esto evita que un cliente mal
configurado (o malicioso) pida datos de una marca que no le corresponde con
solo cambiar un header. Ver sección 7 para el detalle del aislamiento
multi-brand.

## 3. Endpoints

Base URL: `https://mirador-bos-prod.azurewebsites.net/api`

Headers comunes a **todos** los endpoints (se omiten en cada sección para no
repetir):

```
X-Coceo-Key: <COCEO_SECRET_KEY>
X-Coceo-Email: <email registrado en mirador_coceo_usuarios>
Content-Type: application/json   (solo en POST/PUT)
```

Errores comunes a todos los endpoints:

| Status | Causa |
|---|---|
| `401` | Falta `X-Coceo-Key` o no coincide con `COCEO_SECRET_KEY` |
| `403` | Falta `X-Coceo-Email`, o el email no existe / está inactivo en `mirador_coceo_usuarios` |
| `500` | Error de SQL u otro error interno — body: `{"error": "<detalle>"}` |

---

### `GET /coceo/context`

Contexto agregado completo — la llamada que Claude hace siempre al arrancar
una sesión. Una sola query contra `vw_mirador_coceo_ai_context` (sección 5).

**Response 200:**
```json
{
  "brand": "cebala",
  "empresa": { "id": 2, "brand": "cebala", "nombre": "Cebala", "moneda": "ARS", "...": "..." },
  "locales": [{ "id": 1, "nombre": "Depósito Central", "tipo": "deposito", "ciudad": "...", "pais": "..." }],
  "entries":   [{ "record_type": "entry",    "id": 12, "created_at": "...", "detail": "idea", "summary": "...", "tags": "[...]", "status_or_priority": "2" }],
  "meetings":  [{ "record_type": "meeting",  "id": 3,  "created_at": "...", "detail": "meeting", "summary": "..." }],
  "projects":  [{ "record_type": "project",  "id": 5,  "detail": "Título", "status_or_priority": "active", "due_date": "2026-12-31" }],
  "decisions": [{ "record_type": "decision", "id": 8,  "detail": "Título", "summary": "next_step", "status_or_priority": "open", "due_date": "..." }],
  "followups": [{ "record_type": "followup", "id": 2,  "detail": "Título", "status_or_priority": "open", "due_date": "..." }],
  "shopify": {}
}
```

`shopify` queda **siempre** `{}` hoy: el `type_map` y la vista reservan el
`record_type` `shopify_snapshot` para una futura integración, pero ninguna
fuente lo alimenta todavía — es un gancho para F2 (ver roadmap en
`BOS_Master_Prompt_v11.md`), no un dato real de F1.

### `GET /coceo/pending`

Followups abiertos, ordenados por vencimiento.

**Query params:** `limit` (int, default 20, máx 50)

**Response 200:**
```json
[
  { "id": 4, "title": "Llamar a X", "due_date": "2026-08-01", "priority": 2,
    "status": "open", "days_left": 5, "related_type": "decision", "related_id": 8 }
]
```

### `POST /coceo/entry`

Guarda una idea, reflexión, insight o aprendizaje libre del CEO.

**Body:**
| Campo | Tipo | Requerido | Descripción |
|---|---|---|---|
| `content` | string | **sí** | Texto completo de la entrada |
| `type` | string | no (default `"idea"`) | `idea` \| `reflection` \| `insight` \| `learning` \| `risk` \| `operational_learning` |
| `summary` | string | no | Si no viene, se autogenera truncando `content` a 300 chars |
| `tags` | array\<string\> | no | Se guarda como JSON |
| `priority` | int | no (default `3`) | 1=alta, 2=media, 3=baja |

**Response 201:** `{ "id": 42, "created_at": "2026-07-27T12:00:00" }`
**Errores propios:** `400 content es requerido`

### `POST /coceo/meeting`

Guarda una minuta de reunión completa.

**Body:**
| Campo | Tipo | Requerido | Descripción |
|---|---|---|---|
| `date` | string (YYYY-MM-DD) | **sí** | |
| `attendees` | array\<string\> | **sí** | |
| `summary` | string | **sí** | |
| `agenda` | string | no | |
| `decisions` | array | no | Lista de decisiones tomadas en la reunión (texto libre) |
| `action_items` | array\<{owner, task, due}\> | no | Cada item con `due` genera un followup automático (ver `_create_followups_from_actions`) |

**Response 201:** `{ "id": 7, "date": "2026-07-27" }`
**Errores propios:** `400 date/attendees/summary es requerido`

### `POST /coceo/decision`

Registra una decisión estratégica.

**Body:**
| Campo | Tipo | Requerido | Descripción |
|---|---|---|---|
| `title` | string | **sí** | |
| `decision` | string | **sí** | |
| `rationale` | string | no | |
| `next_step` | string | no | Si viene junto con `due_date`, genera un followup automático |
| `due_date` | string (YYYY-MM-DD) | no | |
| `status` | string | no (default `"open"`) | `open` \| `executing` \| `done` \| `reversed` |
| `date` | string (YYYY-MM-DD) | no | Fecha de la decisión |
| `priority` | int | no (default `2`) | Prioridad del followup auto-generado |

**Response 201:** `{ "id": 15 }`
**Errores propios:** `400 title y decision son requeridos`

### `POST /coceo/project`

Crea un proyecto nuevo, o lo actualiza si viene `id`.

**Body (creación):**
| Campo | Tipo | Requerido | Descripción |
|---|---|---|---|
| `title` | string | **sí** (sin `id`) | |
| `status` | string | no (default `"active"`) | `active` \| `paused` \| `completed` \| `cancelled` |
| `start_date` / `target_date` | string (YYYY-MM-DD) | no | |
| `summary` | string | no | |

**Body (actualización — requiere `id`):** `summary`, `status`, `target_date`,
`last_update` (se sobreescriben; `id` + `brand` identifican la fila).

**Response 201 (nuevo):** `{ "id": 9, "is_new": true }`
**Response 200 (update):** `{ "id": 9, "is_new": false }`
**Errores propios:** `400 title es requerido`

### `GET /coceo/empresa`

Perfil de la empresa/marca resuelta por email.

**Response 200:** fila completa de `mirador_coceo_empresa` (ver sección 4).
**Errores propios:** `404 Empresa no encontrada`

### `PUT /coceo/empresa`

Actualiza el perfil (o lo crea si no existe — `MERGE`).

**Body:** `nombre`, `descripcion`, `canales` (array), `objetivos` (objeto),
`temporada_actual`, `moneda` — todos opcionales, solo se pisan los que vienen
(`COALESCE` contra el valor actual).

**Response 200:** `{ "brand": "cebala", "updated": true }`

### `GET /coceo/locales`

Lista los locales activos (`activo = 1`) de la marca, ordenados por
`tipo, nombre`.

**Response 200:** `[{ "id": 1, "nombre": "...", "tipo": "deposito", "ciudad": "...", "pais": "...", "notas": "..." }]`

### `POST /coceo/locales`

Crea un local.

**Body:**
| Campo | Tipo | Requerido | Descripción |
|---|---|---|---|
| `nombre` | string | **sí** | |
| `tipo` | string | no (default `"deposito"`) | `deposito` \| `local` \| `proveedor` \| `showroom` \| `oficina` |
| `ciudad` / `pais` / `notas` | string | no | |

**Response 201:** `{ "id": 3 }`
**Errores propios:** `400 nombre es requerido`

### `GET /coceo/operacional`

Lista aprendizajes/observaciones operativas, con filtros opcionales.

**Query params:** `local_id` (int), `type` (string), `status` (default
`"open"`, usar `"all"` para no filtrar), `limit` (default 30, máx 100)

**Response 200:** `[{ "id": 1, "created_at": "...", "type": "learning", "summary": "...", "tags": "[...]", "status": "open", "priority": 3, "local_id": 1, "local_nombre": "..." }]`

### `POST /coceo/operacional`

Registra un aprendizaje/observación operativa de un local.

**Body:**
| Campo | Tipo | Requerido | Descripción |
|---|---|---|---|
| `content` | string | **sí** | |
| `local_id` | int | no | FK lógica a `mirador_coceo_locales.id` (sin constraint formal) |
| `type` | string | no (default `"learning"`) | `learning` \| `process` \| `incident` \| `improvement` \| `observation` |
| `summary` | string | no | Autogenerado si no viene |
| `tags` | array\<string\> | no | |
| `status` | string | no (default `"open"`) | `open` \| `in_progress` \| `resolved` \| `noted` |
| `priority` | int | no (default `3`) | |
| `author_id` | int | no | FK lógica a empleados BOS (sin constraint formal) |

**Response 201:** `{ "id": 21, "created_at": "..." }`
**Errores propios:** `400 content es requerido`

## 4. Tablas SQL

Scripts de creación: [`sql/coceo_tables.sql`](../sql/coceo_tables.sql) y
[`sql/coceo_usuarios.sql`](../sql/coceo_usuarios.sql). Todas con prefijo
`mirador_coceo_*` en `shopify_db`. Ninguna tiene foreign keys formales —
las relaciones (`local_id`, `related_id`, etc.) son lógicas, validadas solo
en el código de `blueprints/coceo.py`.

### `mirador_coceo_entries`
| Campo | Tipo | Descripción |
|---|---|---|
| `id` | INT IDENTITY PK | |
| `created_at` | DATETIME2 | default `GETUTCDATE()` |
| `type` | NVARCHAR(50) NOT NULL | idea\|reflection\|insight\|learning\|risk\|operational_learning |
| `content` | NVARCHAR(MAX) NOT NULL | |
| `summary` | NVARCHAR(300) | |
| `brand` | NVARCHAR(50) NOT NULL | default `mushkana` |
| `tags` | NVARCHAR(500) | JSON array |
| `priority` | TINYINT | default `3` — 1=alta 2=media 3=baja |

Índices: `idx_coceo_entries_created_at (created_at DESC)`,
`idx_coceo_entries_brand_created_at (brand, created_at DESC)`,
`idx_coceo_entries_type (type)`.

### `mirador_coceo_meetings`
| Campo | Tipo | Descripción |
|---|---|---|
| `id` | INT IDENTITY PK | |
| `created_at` | DATETIME2 | |
| `date` | DATE NOT NULL | |
| `attendees` | NVARCHAR(500) NOT NULL | JSON array |
| `agenda` | NVARCHAR(1000) | |
| `summary` | NVARCHAR(300) NOT NULL | |
| `decisions` | NVARCHAR(MAX) | JSON array |
| `action_items` | NVARCHAR(MAX) | JSON array `[{owner,task,due}]` |
| `brand` | NVARCHAR(50) NOT NULL | default `mushkana` |

Índices: `idx_coceo_meetings_date (date DESC)`,
`idx_coceo_meetings_brand_date (brand, date DESC)`.

### `mirador_coceo_projects`
| Campo | Tipo | Descripción |
|---|---|---|
| `id` | INT IDENTITY PK | |
| `created_at` | DATETIME2 | |
| `title` | NVARCHAR(200) NOT NULL | |
| `status` | NVARCHAR(20) NOT NULL | default `active` — active\|paused\|completed\|cancelled |
| `brand` | NVARCHAR(50) NOT NULL | default `mushkana` |
| `start_date` / `target_date` | DATE | |
| `summary` | NVARCHAR(300) | |
| `last_update` | NVARCHAR(MAX) | JSON con updates cronológicos |

Índices: `idx_coceo_projects_brand_status (brand, status)`,
`idx_coceo_projects_target_date (target_date)`.

### `mirador_coceo_decisions`
| Campo | Tipo | Descripción |
|---|---|---|
| `id` | INT IDENTITY PK | |
| `created_at` | DATETIME2 | |
| `date` | DATE NOT NULL | |
| `title` | NVARCHAR(200) NOT NULL | |
| `decision` | NVARCHAR(MAX) NOT NULL | |
| `rationale` | NVARCHAR(MAX) | |
| `status` | NVARCHAR(20) | default `open` — open\|executing\|done\|reversed |
| `next_step` | NVARCHAR(500) | |
| `due_date` | DATE | |
| `brand` | NVARCHAR(50) NOT NULL | default `mushkana` |

Índices: `idx_coceo_decisions_brand_status (brand, status)`,
`idx_coceo_decisions_due_date (due_date)`.

### `mirador_coceo_followups`
| Campo | Tipo | Descripción |
|---|---|---|
| `id` | INT IDENTITY PK | |
| `created_at` | DATETIME2 | |
| `title` | NVARCHAR(200) NOT NULL | |
| `due_date` | DATE | |
| `status` | NVARCHAR(20) | default `open` — open\|done\|cancelled |
| `priority` | TINYINT | default `2` |
| `related_id` | INT | FK lógica — id del meeting/decision que lo generó |
| `related_type` | NVARCHAR(50) | `meeting` \| `decision` \| `project` |
| `brand` | NVARCHAR(50) NOT NULL | default `mushkana` |

Índice: `idx_coceo_followups_brand_status_due (brand, status, due_date)`.

### `mirador_coceo_empresa`
| Campo | Tipo | Descripción |
|---|---|---|
| `id` | INT IDENTITY PK | |
| `brand` | NVARCHAR(50) NOT NULL UNIQUE | una fila por marca |
| `nombre` | NVARCHAR(200) NOT NULL | |
| `descripcion` | NVARCHAR(MAX) | |
| `canales` | NVARCHAR(500) | JSON array, ej. `["shopify","instagram","local_fisico"]` |
| `objetivos` | NVARCHAR(MAX) | JSON con metas del año |
| `temporada_actual` | NVARCHAR(100) | |
| `moneda` | NVARCHAR(10) | default `ARS` |
| `updated_at` | DATETIME2 | |

Sin índice propio — el `UNIQUE` sobre `brand` ya crea uno.

### `mirador_coceo_locales`
| Campo | Tipo | Descripción |
|---|---|---|
| `id` | INT IDENTITY PK | |
| `brand` | NVARCHAR(50) NOT NULL | |
| `nombre` | NVARCHAR(200) NOT NULL | |
| `tipo` | NVARCHAR(50) | deposito\|local\|proveedor\|showroom\|oficina |
| `ciudad` / `pais` | NVARCHAR(100) | |
| `notas` | NVARCHAR(MAX) | |
| `activo` | BIT | default `1` |
| `created_at` | DATETIME2 | |

Índices: `idx_coceo_locales_brand (brand)`,
`idx_coceo_locales_brand_tipo (brand, tipo)`.

### `mirador_coceo_operacional`
| Campo | Tipo | Descripción |
|---|---|---|
| `id` | INT IDENTITY PK | |
| `created_at` | DATETIME2 | |
| `local_id` | INT | FK lógica → `mirador_coceo_locales.id` |
| `author_id` | INT | FK lógica → empleados BOS |
| `type` | NVARCHAR(50) | learning\|process\|incident\|improvement\|observation |
| `content` | NVARCHAR(MAX) NOT NULL | |
| `summary` | NVARCHAR(300) | |
| `tags` | NVARCHAR(500) | JSON array |
| `status` | NVARCHAR(20) | default `open` — open\|in_progress\|resolved\|noted |
| `priority` | TINYINT | default `3` |
| `brand` | NVARCHAR(50) NOT NULL | default `mushkana` |

Índices: `idx_coceo_operacional_brand_local_created (brand, local_id, created_at DESC)`,
`idx_coceo_operacional_brand_status_priority (brand, status, priority)`.

### `mirador_coceo_usuarios`
| Campo | Tipo | Descripción |
|---|---|---|
| `email` | NVARCHAR(200) NOT NULL PK | |
| `brand` | NVARCHAR(50) NOT NULL | marca a la que este email tiene acceso |
| `nombre` | NVARCHAR(200) | solo descriptivo |
| `activo` | BIT | default `1` — en `0` bloquea el acceso sin borrar la fila |
| `created_at` | DATETIME2 | |

Sin índices propios — el PK sobre `email` ya es el único lookup que hace
`_brand()`. Ver sección 8 para cómo dar de alta un usuario.

## 5. Vista `vw_mirador_coceo_ai_context`

Definición completa: [`sql/coceo_view.sql`](../sql/coceo_view.sql).

Pre-agrega en una sola query lo que `GET /coceo/context` necesita mostrarle a
Claude al arrancar sesión, con `UNION ALL` sobre 5 fuentes:

| `record_type` | Fuente | Filtro | Orden |
|---|---|---|---|
| `entry` | `mirador_coceo_entries` | TOP 30, todos | `created_at DESC` |
| `meeting` | `mirador_coceo_meetings` | TOP 20, últimos 60 días | `date DESC` |
| `project` | `mirador_coceo_projects` | TOP 20, `status IN (active, paused)` | `target_date ASC` |
| `decision` | `mirador_coceo_decisions` | TOP 15, `status IN (open, executing)` | `due_date ASC` |
| `followup` | `mirador_coceo_followups` | TOP 10, `status='open'` y vence en ≤7 días | `due_date ASC` |

Columnas homogéneas entre las 5 fuentes (`record_type, brand, id, created_at,
detail, summary, tags, status_or_priority, due_date`) para que
`coceo_context()` pueda iterar el resultado con un solo `type_map` en vez de
5 queries separadas. `GET /coceo/context` filtra por `brand` sobre el
resultado de la vista.

## 6. MCP Server

### Local (stdio) — `coceo_mcp.py`

Para un solo usuario fijo, corriendo en su propia máquina. Configuración en
`claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "coceo": {
      "command": "/ruta/al/repo/.venv-mcp/bin/python3",
      "args": ["/ruta/al/repo/coceo_mcp.py"],
      "env": {
        "COCEO_SECRET_KEY": "<la key>",
        "COCEO_EMAIL": "<tu email registrado en mirador_coceo_usuarios>"
      }
    }
  }
}
```

Requiere Python ≥3.10 en un venv separado (`.venv-mcp`) — el `.venv` del
Function App está en 3.9 por compat con Azure.

**Nota:** Claude Desktop **no** conecta servidores remotos (HTTP/SSE) desde
este archivo — `mcpServers` con `command`/`args`/`env` es solo para
servidores locales por stdio. Para remoto, ver la siguiente sección.

### Remoto (HTTP/SSE) — `coceo_mcp_server.py`

Corre como Azure Container App independiente (`coceo-mcp`, resource group
`mirador-bos-rg`), scale-to-zero. Se conecta desde **Settings → Connectors →
Add custom connector** en Claude Desktop/claude.ai — esa UI solo acepta una
URL pelada (sin campo de headers custom, solo OAuth Client ID/Secret
opcional), así que la auth viaja embebida en la URL:

```
https://coceo-mcp.<env>.<region>.azurecontainerapps.io/sse?key=<MCP_API_KEY>&email=<tu-email>
```

Dos capas de auth independientes (`MCP_API_KEY` protege el transporte MCP en
sí; `X-Coceo-Key`/`X-Coceo-Email` son la auth de la API COCEO, generados
server-side a partir del email):

1. **`MCP_API_KEY`** — exige `?key=` (o header `X-MCP-Key` / `Authorization:
   Bearer` para clientes que sí soporten headers, ej. `curl`) en el `GET /sse`
   inicial. Sin esto, cualquiera en internet podría abrir la conexión.
2. **`X-Coceo-Email`** (header o `?email=`) — se captura una vez al conectar
   y queda vigente para toda la sesión vía `contextvar`; ninguna tool pide
   `email` como argumento — el modelo no tiene que recordarlo ni preguntarlo.

Variables de entorno del Container App:

```
COCEO_SECRET_KEY   # la misma que usa blueprints/coceo.py
COCEO_BASE_URL     # https://mirador-bos-prod.azurewebsites.net/api
MCP_API_KEY        # generada con secrets.token_urlsafe(32), independiente de COCEO_SECRET_KEY
```

Deploy (build remoto vía ACR Tasks, sin necesitar Docker local):

```bash
az acr build --registry <acr-name> --resource-group mirador-bos-rg \
  --image coceo-mcp:latest .

az containerapp update --name coceo-mcp --resource-group mirador-bos-rg \
  --image <acr-name>.azurecr.io/coceo-mcp:latest --revision-suffix vN
```

**Sticky sessions:** habilitado en el ingress (`az containerapp ingress
sticky-sessions set --affinity sticky`) — necesario porque cada conexión SSE
vive en una réplica específica; sin afinidad, un scale-out a 2+ réplicas
puede enrutar el `POST /messages/` de una sesión a una réplica que no la
conoce, devolviendo `404`.

## 7. Multi-brand

Aislamiento por marca en dos niveles:

1. **Autorización** — `_brand(req)` resuelve la marca desde
   `mirador_coceo_usuarios` por email; un usuario nunca puede pedir/escribir
   datos de una marca que no le corresponde, porque el propio backend decide
   la marca, no el cliente.
2. **Datos** — todas las tablas `mirador_coceo_*` (salvo `usuarios`) tienen
   columna `brand`, y **todas** las queries filtran por ella. Dos CEOs
   distintos, cada uno con su email, ven universos de datos completamente
   separados aunque compartan el mismo servidor MCP remoto y la misma
   `COCEO_SECRET_KEY`.

No hay ningún endpoint que permita leer/escribir "todas las marcas" — el
scope de cada request queda fijado apenas se resuelve el email.

## 8. Cómo agregar un usuario nuevo

```sql
INSERT INTO mirador_coceo_usuarios (email, brand, nombre)
VALUES ('nuevo.ceo@ejemplo.com', 'cebala', 'Nombre descriptivo');
```

- `email` — se compara en minúsculas y sin espacios (`_brand()` hace
  `.lower().strip()` antes de buscar); no hace falta normalizarlo a mano al
  insertar, pero es buena práctica hacerlo igual.
- `brand` — debe ser un valor que las tablas `mirador_coceo_*` reconozcan
  (hoy: `cebala` o `mushkana`).
- Para revocar acceso sin borrar historial: `UPDATE mirador_coceo_usuarios
  SET activo = 0 WHERE email = '...'` — `_brand()` filtra `activo = 1`.

Después de insertar, ese email ya puede usarse en `X-Coceo-Email` (API
directa), `COCEO_EMAIL` (MCP local) o `?email=` (MCP remoto) sin ningún otro
cambio de código ni de deploy.
