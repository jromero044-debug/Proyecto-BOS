-- ============================================================
-- coceo_view.sql — vista vw_mirador_coceo_ai_context
-- Server: sql-server-mirador-br.database.windows.net
-- DB: shopify_db
-- Pre-agrega entries/meetings/projects/decisions/followups recientes
-- o pendientes en una sola query. Consumida por GET /coceo/context
-- (blueprints/coceo.py) para dar contexto a Claude al inicio de sesión.
--
-- DROP VIEW y CREATE VIEW van cada uno en su propio batch (regla T-SQL:
-- CREATE VIEW debe ser el único statement del batch) — separados con GO.
-- ============================================================

DROP VIEW IF EXISTS vw_mirador_coceo_ai_context
GO

CREATE VIEW vw_mirador_coceo_ai_context AS

SELECT TOP 30
    'entry'      AS record_type,
    brand, id, created_at,
    type         AS detail,
    summary, tags,
    CAST(priority AS NVARCHAR(10)) AS status_or_priority,
    NULL         AS due_date
FROM mirador_coceo_entries
ORDER BY created_at DESC

UNION ALL

SELECT TOP 20
    'meeting'    AS record_type,
    brand, id,
    CAST(date AS DATETIME2) AS created_at,
    'meeting'    AS detail,
    summary, NULL AS tags, NULL AS status_or_priority, NULL AS due_date
FROM mirador_coceo_meetings
WHERE date >= DATEADD(DAY, -60, GETUTCDATE())
ORDER BY date DESC

UNION ALL

SELECT TOP 20
    'project'    AS record_type,
    brand, id, created_at,
    title        AS detail,
    summary, NULL AS tags,
    status       AS status_or_priority,
    target_date  AS due_date
FROM mirador_coceo_projects
WHERE status IN ('active', 'paused')
ORDER BY target_date ASC

UNION ALL

SELECT TOP 15
    'decision'   AS record_type,
    brand, id, created_at,
    title        AS detail,
    next_step    AS summary,
    NULL AS tags,
    status       AS status_or_priority,
    due_date
FROM mirador_coceo_decisions
WHERE status IN ('open', 'executing')
ORDER BY due_date ASC

UNION ALL

SELECT TOP 10
    'followup'   AS record_type,
    brand, id, created_at,
    title        AS detail,
    NULL AS summary, NULL AS tags,
    status       AS status_or_priority,
    due_date
FROM mirador_coceo_followups
WHERE status = 'open'
  AND due_date <= DATEADD(DAY, 7, GETUTCDATE())
ORDER BY due_date ASC
GO
