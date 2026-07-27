-- ============================================================
-- coceo_tables.sql — Tablas del módulo Coceo
-- Server: sql-server-mirador-br.database.windows.net
-- DB: shopify_db
-- Driver de ejecución: pymssql (NUNCA pyodbc)
-- Idempotente: seguro correr más de una vez (IF NOT EXISTS en
-- cada tabla, índice e INSERT inicial). Sin GO — pensado para
-- ejecutarse tal cual vía pymssql, statement por statement.
-- ============================================================


-- ============================================================
-- 1. coceo_entries
-- ============================================================
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'mirador_coceo_entries')
BEGIN
    CREATE TABLE dbo.mirador_coceo_entries (
        id         INT IDENTITY(1,1) PRIMARY KEY,
        created_at DATETIME2      DEFAULT GETUTCDATE(),
        type       NVARCHAR(50)   NOT NULL,  -- idea|reflection|insight|learning|risk|operational_learning
        content    NVARCHAR(MAX)  NOT NULL,
        summary    NVARCHAR(300)  NULL,
        brand      NVARCHAR(50)   NOT NULL DEFAULT 'mushkana',
        tags       NVARCHAR(500)  NULL,       -- JSON array
        priority   TINYINT        DEFAULT 3   -- 1=alta 2=media 3=baja
    );
END

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID('dbo.mirador_coceo_entries') AND name = 'idx_coceo_entries_created_at')
    CREATE INDEX idx_coceo_entries_created_at ON dbo.mirador_coceo_entries (created_at DESC);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID('dbo.mirador_coceo_entries') AND name = 'idx_coceo_entries_brand_created_at')
    CREATE INDEX idx_coceo_entries_brand_created_at ON dbo.mirador_coceo_entries (brand, created_at DESC);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID('dbo.mirador_coceo_entries') AND name = 'idx_coceo_entries_type')
    CREATE INDEX idx_coceo_entries_type ON dbo.mirador_coceo_entries (type);


-- ============================================================
-- 2. coceo_meetings
-- ============================================================
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'mirador_coceo_meetings')
BEGIN
    CREATE TABLE dbo.mirador_coceo_meetings (
        id           INT IDENTITY(1,1) PRIMARY KEY,
        created_at   DATETIME2      DEFAULT GETUTCDATE(),
        date         DATE           NOT NULL,
        attendees    NVARCHAR(500)  NOT NULL,  -- JSON array
        agenda       NVARCHAR(1000) NULL,
        summary      NVARCHAR(300)  NOT NULL,
        decisions    NVARCHAR(MAX)  NULL,       -- JSON array
        action_items NVARCHAR(MAX)  NULL,       -- JSON array [{owner,task,due}]
        brand        NVARCHAR(50)   NOT NULL DEFAULT 'mushkana'
    );
END

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID('dbo.mirador_coceo_meetings') AND name = 'idx_coceo_meetings_date')
    CREATE INDEX idx_coceo_meetings_date ON dbo.mirador_coceo_meetings (date DESC);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID('dbo.mirador_coceo_meetings') AND name = 'idx_coceo_meetings_brand_date')
    CREATE INDEX idx_coceo_meetings_brand_date ON dbo.mirador_coceo_meetings (brand, date DESC);


-- ============================================================
-- 3. coceo_projects
-- ============================================================
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'mirador_coceo_projects')
BEGIN
    CREATE TABLE dbo.mirador_coceo_projects (
        id          INT IDENTITY(1,1) PRIMARY KEY,
        created_at  DATETIME2      DEFAULT GETUTCDATE(),
        title       NVARCHAR(200)  NOT NULL,
        status      NVARCHAR(20)   NOT NULL DEFAULT 'active',  -- active|paused|completed|cancelled
        brand       NVARCHAR(50)   NOT NULL DEFAULT 'mushkana',
        start_date  DATE           NULL,
        target_date DATE           NULL,
        summary     NVARCHAR(300)  NULL,
        last_update NVARCHAR(MAX)  NULL   -- JSON con updates cronológicos
    );
END

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID('dbo.mirador_coceo_projects') AND name = 'idx_coceo_projects_brand_status')
    CREATE INDEX idx_coceo_projects_brand_status ON dbo.mirador_coceo_projects (brand, status);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID('dbo.mirador_coceo_projects') AND name = 'idx_coceo_projects_target_date')
    CREATE INDEX idx_coceo_projects_target_date ON dbo.mirador_coceo_projects (target_date);


-- ============================================================
-- 4. coceo_decisions
-- ============================================================
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'mirador_coceo_decisions')
BEGIN
    CREATE TABLE dbo.mirador_coceo_decisions (
        id         INT IDENTITY(1,1) PRIMARY KEY,
        created_at DATETIME2      DEFAULT GETUTCDATE(),
        date       DATE           NOT NULL,
        title      NVARCHAR(200)  NOT NULL,
        decision   NVARCHAR(MAX)  NOT NULL,
        rationale  NVARCHAR(MAX)  NULL,
        status     NVARCHAR(20)   DEFAULT 'open',  -- open|executing|done|reversed
        next_step  NVARCHAR(500)  NULL,
        due_date   DATE           NULL,
        brand      NVARCHAR(50)   NOT NULL DEFAULT 'mushkana'
    );
END

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID('dbo.mirador_coceo_decisions') AND name = 'idx_coceo_decisions_brand_status')
    CREATE INDEX idx_coceo_decisions_brand_status ON dbo.mirador_coceo_decisions (brand, status);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID('dbo.mirador_coceo_decisions') AND name = 'idx_coceo_decisions_due_date')
    CREATE INDEX idx_coceo_decisions_due_date ON dbo.mirador_coceo_decisions (due_date);


-- ============================================================
-- 5. coceo_followups
-- ============================================================
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'mirador_coceo_followups')
BEGIN
    CREATE TABLE dbo.mirador_coceo_followups (
        id           INT IDENTITY(1,1) PRIMARY KEY,
        created_at   DATETIME2      DEFAULT GETUTCDATE(),
        title        NVARCHAR(200)  NOT NULL,
        due_date     DATE           NULL,
        status       NVARCHAR(20)   DEFAULT 'open',  -- open|done|cancelled
        priority     TINYINT        DEFAULT 2,
        related_id   INT            NULL,
        related_type NVARCHAR(50)   NULL,             -- meeting|decision|project
        brand        NVARCHAR(50)   NOT NULL DEFAULT 'mushkana'
    );
END

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID('dbo.mirador_coceo_followups') AND name = 'idx_coceo_followups_brand_status_due')
    CREATE INDEX idx_coceo_followups_brand_status_due ON dbo.mirador_coceo_followups (brand, status, due_date);


-- ============================================================
-- 6. coceo_empresa
-- ============================================================
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'mirador_coceo_empresa')
BEGIN
    CREATE TABLE dbo.mirador_coceo_empresa (
        id               INT IDENTITY(1,1) PRIMARY KEY,
        brand            NVARCHAR(50)   NOT NULL UNIQUE,
        nombre           NVARCHAR(200)  NOT NULL,
        descripcion      NVARCHAR(MAX)  NULL,
        canales          NVARCHAR(500)  NULL,   -- JSON array: ["shopify","instagram","local_fisico"]
        objetivos        NVARCHAR(MAX)  NULL,   -- JSON con metas del año
        temporada_actual NVARCHAR(100)  NULL,
        moneda           NVARCHAR(10)   DEFAULT 'ARS',
        updated_at       DATETIME2      DEFAULT GETUTCDATE()
    );
END
-- Nota: no se agrega un índice separado en (brand) — el UNIQUE de arriba
-- ya crea un índice único sobre esa columna, duplicarlo sería redundante.


-- ============================================================
-- 7. coceo_locales
-- ============================================================
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'mirador_coceo_locales')
BEGIN
    CREATE TABLE dbo.mirador_coceo_locales (
        id         INT IDENTITY(1,1) PRIMARY KEY,
        brand      NVARCHAR(50)   NOT NULL,
        nombre     NVARCHAR(200)  NOT NULL,
        tipo       NVARCHAR(50)   NULL,   -- deposito|local|proveedor|showroom|oficina
        ciudad     NVARCHAR(100)  NULL,
        pais       NVARCHAR(100)  NULL,
        notas      NVARCHAR(MAX)  NULL,
        activo     BIT            DEFAULT 1,
        created_at DATETIME2      DEFAULT GETUTCDATE()
    );
END

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID('dbo.mirador_coceo_locales') AND name = 'idx_coceo_locales_brand')
    CREATE INDEX idx_coceo_locales_brand ON dbo.mirador_coceo_locales (brand);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID('dbo.mirador_coceo_locales') AND name = 'idx_coceo_locales_brand_tipo')
    CREATE INDEX idx_coceo_locales_brand_tipo ON dbo.mirador_coceo_locales (brand, tipo);


-- ============================================================
-- 8. coceo_operacional
-- ============================================================
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'mirador_coceo_operacional')
BEGIN
    CREATE TABLE dbo.mirador_coceo_operacional (
        id         INT IDENTITY(1,1) PRIMARY KEY,
        created_at DATETIME2      DEFAULT GETUTCDATE(),
        local_id   INT            NULL,   -- FK lógica a coceo_locales(id) — sin constraint formal
        author_id  INT            NULL,   -- FK lógica a empleados BOS — sin constraint formal
        type       NVARCHAR(50)   NULL,   -- learning|process|incident|improvement|observation
        content    NVARCHAR(MAX)  NOT NULL,
        summary    NVARCHAR(300)  NULL,
        tags       NVARCHAR(500)  NULL,   -- JSON array
        status     NVARCHAR(20)   DEFAULT 'open',  -- open|in_progress|resolved|noted
        priority   TINYINT        DEFAULT 3,
        brand      NVARCHAR(50)   NOT NULL DEFAULT 'mushkana'
    );
END

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID('dbo.mirador_coceo_operacional') AND name = 'idx_coceo_operacional_brand_local_created')
    CREATE INDEX idx_coceo_operacional_brand_local_created ON dbo.mirador_coceo_operacional (brand, local_id, created_at DESC);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID('dbo.mirador_coceo_operacional') AND name = 'idx_coceo_operacional_brand_status_priority')
    CREATE INDEX idx_coceo_operacional_brand_status_priority ON dbo.mirador_coceo_operacional (brand, status, priority);


-- ============================================================
-- Datos iniciales
-- ============================================================
IF NOT EXISTS (SELECT 1 FROM dbo.mirador_coceo_empresa WHERE brand = 'mushkana')
    INSERT INTO dbo.mirador_coceo_empresa (brand, nombre) VALUES ('mushkana', 'Mushkana');

IF NOT EXISTS (SELECT 1 FROM dbo.mirador_coceo_empresa WHERE brand = 'cebala')
    INSERT INTO dbo.mirador_coceo_empresa (brand, nombre) VALUES ('cebala', 'Cebala');
