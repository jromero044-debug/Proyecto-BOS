-- ============================================================
-- coceo_usuarios.sql — Tabla de mapeo email → marca del módulo Coceo
-- Server: sql-server-mirador-br.database.windows.net
-- DB: shopify_db
-- Idempotente: seguro correr más de una vez.
--
-- blueprints/coceo.py resuelve la marca (brand) de cada request a partir
-- del header X-Coceo-Email contra esta tabla — no confía en un header de
-- marca que el propio cliente pudiera setear libremente. Ver COCEO_API.md
-- sección "Autenticación" para el detalle completo.
-- ============================================================

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'mirador_coceo_usuarios')
BEGIN
    CREATE TABLE dbo.mirador_coceo_usuarios (
        email      NVARCHAR(200) NOT NULL PRIMARY KEY,
        brand      NVARCHAR(50)  NOT NULL,
        nombre     NVARCHAR(200) NULL,
        activo     BIT           DEFAULT 1,
        created_at DATETIME2     DEFAULT GETUTCDATE()
    );
END

-- Alta de usuario de ejemplo — reemplazar por el email y la marca reales.
-- IF NOT EXISTS (SELECT 1 FROM dbo.mirador_coceo_usuarios WHERE email = 'ceo@ejemplo.com')
--     INSERT INTO dbo.mirador_coceo_usuarios (email, brand, nombre)
--     VALUES ('ceo@ejemplo.com', 'cebala', 'CEO Cebala');
