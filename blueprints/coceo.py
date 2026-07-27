"""
blueprints/coceo.py — Módulo Coceo (notas, decisiones, reuniones, seguimiento del CEO)
Autenticación propia vía header X-Coceo-Key (no Easy Auth) — pensado para ser
consumido por un asistente/agente externo, no por el dashboard de React.

Endpoints:
  GET  /coceo/context       — contexto agregado para IA (vía vw_mirador_coceo_ai_context)
  GET  /coceo/pending       — followups abiertos
  POST /coceo/entry         — idea/reflexión/insight/aprendizaje
  POST /coceo/meeting       — minuta de reunión
  POST /coceo/decision      — decisión estratégica
  POST /coceo/project       — crea o actualiza iniciativa
  GET  /coceo/empresa       — perfil de marca
  PUT  /coceo/empresa       — actualiza/crea perfil de marca
  GET  /coceo/locales       — locales activos
  POST /coceo/locales       — crea local
  GET  /coceo/operacional   — lista aprendizajes operativos
  POST /coceo/operacional   — registra aprendizaje operativo
"""
import os
import json
import logging

import azure.functions as func

from .shared import get_conn, _CORS as _SHARED_CORS

bp = func.Blueprint()
logger = logging.getLogger(__name__)

# ── Config ──────────────────────────────────────────────────────────────────
# Nota: COCEO_SECRET_KEY debe agregarse a local.settings.json y a las App
# Settings de Azure ANTES de deployar esto — si falta, el import de este
# módulo tira KeyError y se cae toda la Function App (todos los blueprints).
COCEO_KEY = os.environ.get("COCEO_SECRET_KEY", "")

_CORS = {
    **_SHARED_CORS,
    "Access-Control-Allow-Methods": "GET, POST, PUT, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, X-Coceo-Key",
}


# ── Helpers ─────────────────────────────────────────────────────────────────
def _ok(data, status=200):
    return func.HttpResponse(
        json.dumps(data, default=str),
        status_code=status,
        mimetype="application/json",
        headers=_CORS,
    )


def _err(msg, status=400):
    return func.HttpResponse(
        json.dumps({"error": msg}),
        status_code=status,
        mimetype="application/json",
        headers=_CORS,
    )


def _auth(req: func.HttpRequest) -> bool:
    """Valida X-Coceo-Key. Retorna True si OK. Si COCEO_SECRET_KEY no está
    configurada, siempre rechaza (fail-closed, no fail-open)."""
    if not COCEO_KEY:
        return False
    return req.headers.get("X-Coceo-Key", "") == COCEO_KEY


def _brand(req: func.HttpRequest) -> str:
    """Brand viene del header X-Coceo-Brand. Default mushkana."""
    return req.headers.get("X-Coceo-Brand", "mushkana").lower()


def _rows(cur) -> list:
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _summary_or_truncate(body: dict, content: str) -> str:
    """Usa el summary provisto; si no vino, trunca content si es muy largo,
    si no lo usa entero. (Paréntesis explícitos — sin ellos el `or`/ternario
    de Python se agrupa mal y descarta el summary provisto cuando content
    es corto.)"""
    return body.get("summary") or (content[:297] + "..." if len(content) > 300 else content)


# ════════════════════════════════════════════════════════════════════════════
# LECTURA DE CONTEXTO
# ════════════════════════════════════════════════════════════════════════════

@bp.route(route="coceo/context", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def coceo_context(req: func.HttpRequest) -> func.HttpResponse:
    """
    Contexto completo para Claude — una sola query vía vista.
    Devuelve: entries, meetings, projects, decisions, followups, shopify, empresa.
    """
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=_CORS)
    if not _auth(req):
        return _err("Unauthorized", 401)

    brand = _brand(req)
    try:
        conn = get_conn()
        cur  = conn.cursor()

        cur.execute(
            "SELECT * FROM vw_mirador_coceo_ai_context WHERE brand = %s ORDER BY created_at DESC",
            (brand,)
        )
        vista_rows = _rows(cur)

        cur.execute("SELECT * FROM mirador_coceo_empresa WHERE brand = %s", (brand,))
        empresa_rows = _rows(cur)
        empresa = empresa_rows[0] if empresa_rows else None

        cur.execute(
            "SELECT id, nombre, tipo, ciudad, pais FROM mirador_coceo_locales WHERE brand = %s AND activo = 1",
            (brand,)
        )
        locales = _rows(cur)
        cur.close()
    except Exception as e:
        logging.error(f"❌ coceo_context: {e}")
        return _err(str(e), 500)

    ctx = {
        "brand": brand,
        "empresa": empresa,
        "locales": locales,
        "entries": [],
        "meetings": [],
        "projects": [],
        "decisions": [],
        "followups": [],
        "shopify": {},
    }
    type_map = {
        "entry":            "entries",
        "meeting":          "meetings",
        "project":          "projects",
        "decision":         "decisions",
        "followup":         "followups",
        "shopify_snapshot": "shopify",
    }
    for row in vista_rows:
        rt  = row.get("record_type", "")
        key = type_map.get(rt)
        if key == "shopify":
            ctx["shopify"] = row
        elif key:
            ctx[key].append(row)

    return _ok(ctx)


@bp.route(route="coceo/pending", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def coceo_pending(req: func.HttpRequest) -> func.HttpResponse:
    """Followups abiertos ordenados por due_date ASC."""
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=_CORS)
    if not _auth(req):
        return _err("Unauthorized", 401)

    brand = _brand(req)
    limit = min(int(req.params.get("limit", 20)), 50)

    try:
        conn = get_conn()
        cur  = conn.cursor()
        cur.execute(
            """
            SELECT TOP (%s)
                id, title, due_date, priority, status,
                DATEDIFF(DAY, GETUTCDATE(), due_date) AS days_left,
                related_type, related_id
            FROM mirador_coceo_followups
            WHERE brand = %s AND status = 'open'
            ORDER BY due_date ASC
            """,
            (limit, brand)
        )
        result = _rows(cur)
        cur.close()
        return _ok(result)
    except Exception as e:
        logging.error(f"❌ coceo_pending: {e}")
        return _err(str(e), 500)


# ════════════════════════════════════════════════════════════════════════════
# ESCRITURA — ENTRADAS DEL CEO
# ════════════════════════════════════════════════════════════════════════════

@bp.route(route="coceo/entry", methods=["POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def coceo_entry(req: func.HttpRequest) -> func.HttpResponse:
    """Guarda pensamiento, idea, reflexión, insight u operational_learning."""
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=_CORS)
    if not _auth(req):
        return _err("Unauthorized", 401)

    try:
        b = req.get_json()
    except Exception:
        return _err("JSON inválido")

    if not b.get("content"):
        return _err("content es requerido")

    brand   = _brand(req)
    content = b["content"]
    summary = _summary_or_truncate(b, content)

    try:
        conn = get_conn()
        cur  = conn.cursor()
        cur.execute(
            """
            INSERT INTO mirador_coceo_entries (type, content, summary, brand, tags, priority)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                b.get("type", "idea"),
                content,
                summary,
                brand,
                json.dumps(b.get("tags", [])),
                b.get("priority", 3),
            )
        )
        cur.execute("SELECT SCOPE_IDENTITY()")
        new_id = int(cur.fetchone()[0])
        cur.execute("SELECT created_at FROM mirador_coceo_entries WHERE id = %s", (new_id,))
        created_at = cur.fetchone()[0]
        conn.commit()
        cur.close()
    except Exception as e:
        logging.error(f"❌ coceo_entry: {e}")
        return _err(str(e), 500)

    return _ok({"id": new_id, "created_at": created_at}, 201)


@bp.route(route="coceo/meeting", methods=["POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def coceo_meeting(req: func.HttpRequest) -> func.HttpResponse:
    """Guarda minuta de reunión completa."""
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=_CORS)
    if not _auth(req):
        return _err("Unauthorized", 401)

    try:
        b = req.get_json()
    except Exception:
        return _err("JSON inválido")

    for field in ["date", "attendees", "summary"]:
        if not b.get(field):
            return _err(f"{field} es requerido")

    brand = _brand(req)

    try:
        conn = get_conn()
        cur  = conn.cursor()
        cur.execute(
            """
            INSERT INTO mirador_coceo_meetings
                (date, attendees, agenda, summary, decisions, action_items, brand)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                b["date"],
                json.dumps(b["attendees"]),
                b.get("agenda"),
                b["summary"],
                json.dumps(b.get("decisions", [])),
                json.dumps(b.get("action_items", [])),
                brand,
            )
        )
        cur.execute("SELECT SCOPE_IDENTITY()")
        new_id = int(cur.fetchone()[0])
        conn.commit()
        cur.close()
    except Exception as e:
        logging.error(f"❌ coceo_meeting: {e}")
        return _err(str(e), 500)

    # Auto-crear followups de action_items si tienen due_date
    action_items = b.get("action_items", [])
    if action_items:
        _create_followups_from_actions(action_items, new_id, "meeting", brand)

    return _ok({"id": new_id, "date": b["date"]}, 201)


@bp.route(route="coceo/decision", methods=["POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def coceo_decision(req: func.HttpRequest) -> func.HttpResponse:
    """Registra decisión estratégica con rationale y next step."""
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=_CORS)
    if not _auth(req):
        return _err("Unauthorized", 401)

    try:
        b = req.get_json()
    except Exception:
        return _err("JSON inválido")

    if not b.get("title") or not b.get("decision"):
        return _err("title y decision son requeridos")

    brand = _brand(req)

    try:
        conn = get_conn()
        cur  = conn.cursor()
        cur.execute(
            """
            INSERT INTO mirador_coceo_decisions
                (date, title, decision, rationale, status, next_step, due_date, brand)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                b.get("date"),
                b["title"],
                b["decision"],
                b.get("rationale"),
                b.get("status", "open"),
                b.get("next_step"),
                b.get("due_date"),
                brand,
            )
        )
        cur.execute("SELECT SCOPE_IDENTITY()")
        new_id = int(cur.fetchone()[0])
        conn.commit()
        cur.close()
    except Exception as e:
        logging.error(f"❌ coceo_decision: {e}")
        return _err(str(e), 500)

    # Auto-crear followup si tiene due_date y next_step
    if b.get("due_date") and b.get("next_step"):
        _create_followup(
            title=b["next_step"],
            due_date=b["due_date"],
            related_id=new_id,
            related_type="decision",
            brand=brand,
            priority=b.get("priority", 2),
        )

    return _ok({"id": new_id}, 201)


@bp.route(route="coceo/project", methods=["POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def coceo_project(req: func.HttpRequest) -> func.HttpResponse:
    """Crea o actualiza iniciativa estratégica. Si viene id, actualiza."""
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=_CORS)
    if not _auth(req):
        return _err("Unauthorized", 401)

    try:
        b = req.get_json()
    except Exception:
        return _err("JSON inválido")

    if not b.get("title") and not b.get("id"):
        return _err("title es requerido")

    brand       = _brand(req)
    existing_id = b.get("id")

    try:
        conn = get_conn()
        cur  = conn.cursor()

        if existing_id:
            cur.execute(
                """
                UPDATE mirador_coceo_projects
                SET summary = %s, status = %s, last_update = %s, target_date = %s
                WHERE id = %s AND brand = %s
                """,
                (
                    b.get("summary"),
                    b.get("status", "active"),
                    json.dumps(b.get("last_update")),
                    b.get("target_date"),
                    existing_id,
                    brand,
                )
            )
            conn.commit()
            cur.close()
            return _ok({"id": existing_id, "is_new": False})

        cur.execute(
            """
            INSERT INTO mirador_coceo_projects
                (title, status, brand, start_date, target_date, summary)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                b["title"],
                b.get("status", "active"),
                brand,
                b.get("start_date"),
                b.get("target_date"),
                b.get("summary"),
            )
        )
        cur.execute("SELECT SCOPE_IDENTITY()")
        new_id = int(cur.fetchone()[0])
        conn.commit()
        cur.close()
    except Exception as e:
        logging.error(f"❌ coceo_project: {e}")
        return _err(str(e), 500)

    return _ok({"id": new_id, "is_new": True}, 201)


# ════════════════════════════════════════════════════════════════════════════
# EMPRESA Y LOCALES
# ════════════════════════════════════════════════════════════════════════════

@bp.route(route="coceo/empresa", methods=["GET", "PUT", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def coceo_empresa(req: func.HttpRequest) -> func.HttpResponse:
    """GET: perfil de la empresa/marca. PUT: actualiza (o crea si no existe)."""
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=_CORS)
    if not _auth(req):
        return _err("Unauthorized", 401)

    brand = _brand(req)

    if req.method == "GET":
        try:
            conn = get_conn()
            cur  = conn.cursor()
            cur.execute("SELECT * FROM mirador_coceo_empresa WHERE brand = %s", (brand,))
            rows = _rows(cur)
            cur.close()
        except Exception as e:
            logging.error(f"❌ coceo_empresa GET: {e}")
            return _err(str(e), 500)
        if not rows:
            return _err("Empresa no encontrada", 404)
        return _ok(rows[0])

    # PUT
    try:
        b = req.get_json()
    except Exception:
        return _err("JSON inválido")

    try:
        conn = get_conn()
        cur  = conn.cursor()
        cur.execute(
            """
            MERGE mirador_coceo_empresa AS target
            USING (SELECT %s AS brand) AS source ON target.brand = source.brand
            WHEN MATCHED THEN
                UPDATE SET
                    nombre           = COALESCE(%s, nombre),
                    descripcion      = COALESCE(%s, descripcion),
                    canales          = COALESCE(%s, canales),
                    objetivos        = COALESCE(%s, objetivos),
                    temporada_actual = COALESCE(%s, temporada_actual),
                    moneda           = COALESCE(%s, moneda),
                    updated_at       = GETUTCDATE()
            WHEN NOT MATCHED THEN
                INSERT (brand, nombre, descripcion, canales, objetivos, temporada_actual, moneda)
                VALUES (%s, %s, %s, %s, %s, %s, %s);
            """,
            (
                brand,
                b.get("nombre"), b.get("descripcion"),
                json.dumps(b["canales"]) if b.get("canales") else None,
                json.dumps(b["objetivos"]) if b.get("objetivos") else None,
                b.get("temporada_actual"), b.get("moneda"),
                # WHEN NOT MATCHED
                brand, b.get("nombre", brand),
                b.get("descripcion"),
                json.dumps(b.get("canales", [])),
                json.dumps(b.get("objetivos", {})),
                b.get("temporada_actual"), b.get("moneda", "ARS"),
            )
        )
        conn.commit()
        cur.close()
    except Exception as e:
        logging.error(f"❌ coceo_empresa PUT: {e}")
        return _err(str(e), 500)

    return _ok({"brand": brand, "updated": True})


@bp.route(route="coceo/locales", methods=["GET", "POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def coceo_locales(req: func.HttpRequest) -> func.HttpResponse:
    """GET: lista locales activos de la marca. POST: crea un local."""
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=_CORS)
    if not _auth(req):
        return _err("Unauthorized", 401)

    brand = _brand(req)

    if req.method == "GET":
        try:
            conn = get_conn()
            cur  = conn.cursor()
            cur.execute(
                """
                SELECT id, nombre, tipo, ciudad, pais, notas
                FROM mirador_coceo_locales
                WHERE brand = %s AND activo = 1
                ORDER BY tipo, nombre
                """,
                (brand,)
            )
            result = _rows(cur)
            cur.close()
            return _ok(result)
        except Exception as e:
            logging.error(f"❌ coceo_locales GET: {e}")
            return _err(str(e), 500)

    # POST
    try:
        b = req.get_json()
    except Exception:
        return _err("JSON inválido")

    if not b.get("nombre"):
        return _err("nombre es requerido")

    try:
        conn = get_conn()
        cur  = conn.cursor()
        cur.execute(
            """
            INSERT INTO mirador_coceo_locales (brand, nombre, tipo, ciudad, pais, notas)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                brand,
                b["nombre"],
                b.get("tipo", "deposito"),
                b.get("ciudad"),
                b.get("pais"),
                b.get("notas"),
            )
        )
        cur.execute("SELECT SCOPE_IDENTITY()")
        new_id = int(cur.fetchone()[0])
        conn.commit()
        cur.close()
    except Exception as e:
        logging.error(f"❌ coceo_locales POST: {e}")
        return _err(str(e), 500)

    return _ok({"id": new_id}, 201)


# ════════════════════════════════════════════════════════════════════════════
# OPERACIONAL
# ════════════════════════════════════════════════════════════════════════════

@bp.route(route="coceo/operacional", methods=["GET", "POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def coceo_operacional(req: func.HttpRequest) -> func.HttpResponse:
    """GET: lista aprendizajes operacionales (filtra por local_id/type/status).
    POST: registra aprendizaje u observación operativa de un local."""
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=_CORS)
    if not _auth(req):
        return _err("Unauthorized", 401)

    brand = _brand(req)

    if req.method == "GET":
        local_id = req.params.get("local_id")
        tipo     = req.params.get("type")
        status   = req.params.get("status", "open")
        limit    = min(int(req.params.get("limit", 30)), 100)

        filters = ["brand = %s"]
        params  = [brand]
        if local_id:
            filters.append("local_id = %s")
            params.append(int(local_id))
        if tipo:
            filters.append("type = %s")
            params.append(tipo)
        if status != "all":
            filters.append("status = %s")
            params.append(status)
        where = " AND ".join(filters)

        try:
            conn = get_conn()
            cur  = conn.cursor()
            cur.execute(
                f"""
                SELECT TOP (%s)
                    o.id, o.created_at, o.type, o.summary, o.tags,
                    o.status, o.priority, o.local_id, l.nombre AS local_nombre
                FROM mirador_coceo_operacional o
                LEFT JOIN mirador_coceo_locales l ON l.id = o.local_id
                WHERE {where}
                ORDER BY o.created_at DESC
                """,
                tuple([limit] + params)
            )
            result = _rows(cur)
            cur.close()
            return _ok(result)
        except Exception as e:
            logging.error(f"❌ coceo_operacional GET: {e}")
            return _err(str(e), 500)

    # POST
    try:
        b = req.get_json()
    except Exception:
        return _err("JSON inválido")

    if not b.get("content"):
        return _err("content es requerido")

    content = b["content"]
    summary = _summary_or_truncate(b, content)

    try:
        conn = get_conn()
        cur  = conn.cursor()
        cur.execute(
            """
            INSERT INTO mirador_coceo_operacional
                (local_id, author_id, type, content, summary, tags, status, priority, brand)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                b.get("local_id"),
                b.get("author_id"),
                b.get("type", "learning"),
                content,
                summary,
                json.dumps(b.get("tags", [])),
                b.get("status", "open"),
                b.get("priority", 3),
                brand,
            )
        )
        cur.execute("SELECT SCOPE_IDENTITY()")
        new_id = int(cur.fetchone()[0])
        cur.execute("SELECT created_at FROM mirador_coceo_operacional WHERE id = %s", (new_id,))
        created_at = cur.fetchone()[0]
        conn.commit()
        cur.close()
    except Exception as e:
        logging.error(f"❌ coceo_operacional POST: {e}")
        return _err(str(e), 500)

    return _ok({"id": new_id, "created_at": created_at}, 201)


# ════════════════════════════════════════════════════════════════════════════
# HELPERS INTERNOS
# ════════════════════════════════════════════════════════════════════════════

def _create_followup(title, due_date, related_id, related_type, brand, priority=2):
    """Crea un followup individual. No-fatal: solo loggea si falla."""
    try:
        conn = get_conn()
        cur  = conn.cursor()
        cur.execute(
            """
            INSERT INTO mirador_coceo_followups
                (title, due_date, status, priority, related_id, related_type, brand)
            VALUES (%s, %s, 'open', %s, %s, %s, %s)
            """,
            (title, due_date, priority, related_id, related_type, brand)
        )
        conn.commit()
        cur.close()
    except Exception as e:
        logger.warning(f"No se pudo crear followup: {e}")


def _create_followups_from_actions(action_items, related_id, related_type, brand):
    """Convierte action_items de una minuta en followups automáticos."""
    for item in action_items:
        if isinstance(item, dict) and item.get("due") and item.get("task"):
            _create_followup(
                title=item["task"],
                due_date=item["due"],
                related_id=related_id,
                related_type=related_type,
                brand=brand,
                priority=2,
            )
