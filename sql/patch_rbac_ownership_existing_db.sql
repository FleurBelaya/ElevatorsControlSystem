-- =============================================================================
-- Patch existing DB to match RBAC + ownership changes
-- =============================================================================
-- Применять, если в БД уже есть таблицы (lifts/sensors/events/...) и приложение
-- падает из-за отсутствия колонок owner_id и RBAC-таблиц.
--
-- 2.1 Авторизация RBAC
-- 2.2 Ownership
-- =============================================================================

BEGIN;

-- 2.1 Авторизация RBAC: users/roles/permissions
CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    email         VARCHAR(320) NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_users_email ON users (email);

CREATE TABLE IF NOT EXISTS roles (
    id   SERIAL PRIMARY KEY,
    name VARCHAR(64) NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS ix_roles_name ON roles (name);

CREATE TABLE IF NOT EXISTS permissions (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(128) NOT NULL UNIQUE,
    description TEXT
);
CREATE INDEX IF NOT EXISTS ix_permissions_name ON permissions (name);

CREATE TABLE IF NOT EXISTS user_roles (
    user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    role_id INTEGER NOT NULL REFERENCES roles (id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, role_id)
);

CREATE TABLE IF NOT EXISTS role_permissions (
    role_id       INTEGER NOT NULL REFERENCES roles (id) ON DELETE CASCADE,
    permission_id INTEGER NOT NULL REFERENCES permissions (id) ON DELETE CASCADE,
    PRIMARY KEY (role_id, permission_id)
);

-- seed ролей
INSERT INTO roles(name) VALUES
  ('administrator'),
  ('dispatcher'),
  ('technician')
ON CONFLICT (name) DO NOTHING;

-- seed permissions (минимум под текущий код)
INSERT INTO permissions(name, description) VALUES
  ('ownership:bypass', 'Видеть/изменять чужие данные'),
  ('lifts:create', NULL), ('lifts:read', NULL), ('lifts:update', NULL), ('lifts:delete', NULL),
  ('lifts:restore_state', NULL), ('lifts:simulate_emergency', NULL),
  ('sensors:create', NULL), ('sensors:read', NULL), ('sensors:update', NULL), ('sensors:delete', NULL),
  ('events:create', NULL), ('events:read', NULL), ('events:update', NULL),
  ('service_requests:create', NULL), ('service_requests:read', NULL), ('service_requests:update', NULL), ('service_requests:delete', NULL),
  ('technicians:create', NULL), ('technicians:read', NULL), ('technicians:update', NULL), ('technicians:delete', NULL),
  ('reports:create', NULL), ('reports:read', NULL), ('reports:update', NULL), ('reports:delete', NULL)
ON CONFLICT (name) DO NOTHING;

-- 2.2 Ownership: owner_id колонки (сначала nullable)
ALTER TABLE lifts            ADD COLUMN IF NOT EXISTS owner_id INTEGER;
ALTER TABLE sensors          ADD COLUMN IF NOT EXISTS owner_id INTEGER;
ALTER TABLE events           ADD COLUMN IF NOT EXISTS owner_id INTEGER;
ALTER TABLE service_requests ADD COLUMN IF NOT EXISTS owner_id INTEGER;
ALTER TABLE technicians      ADD COLUMN IF NOT EXISTS owner_id INTEGER;
ALTER TABLE reports          ADD COLUMN IF NOT EXISTS owner_id INTEGER;

-- системный владелец для существующих данных
DO $$
DECLARE
  sys_user_id INTEGER;
BEGIN
  INSERT INTO users (email, password_hash, is_active)
  VALUES ('system@local', 'disabled', FALSE)
  ON CONFLICT (email) DO UPDATE SET is_active = FALSE
  RETURNING id INTO sys_user_id;

  IF sys_user_id IS NULL THEN
    SELECT id INTO sys_user_id FROM users WHERE email = 'system@local';
  END IF;

  UPDATE lifts            SET owner_id = sys_user_id WHERE owner_id IS NULL;
  UPDATE sensors          SET owner_id = sys_user_id WHERE owner_id IS NULL;
  UPDATE events           SET owner_id = sys_user_id WHERE owner_id IS NULL;
  UPDATE service_requests SET owner_id = sys_user_id WHERE owner_id IS NULL;
  UPDATE technicians      SET owner_id = sys_user_id WHERE owner_id IS NULL;
  UPDATE reports          SET owner_id = sys_user_id WHERE owner_id IS NULL;
END $$;

-- FK + NOT NULL
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu
      ON tc.constraint_name = kcu.constraint_name AND tc.constraint_schema = kcu.constraint_schema
    JOIN information_schema.constraint_column_usage ccu
      ON ccu.constraint_name = tc.constraint_name AND ccu.constraint_schema = tc.constraint_schema
    WHERE tc.constraint_type = 'FOREIGN KEY'
      AND tc.table_schema = 'public'
      AND tc.table_name = 'lifts'
      AND kcu.column_name = 'owner_id'
      AND ccu.table_name = 'users'
  ) THEN
    ALTER TABLE lifts ADD CONSTRAINT fk_lifts_owner_id_users FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE RESTRICT;
  END IF;
  IF NOT EXISTS (
    SELECT 1
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu
      ON tc.constraint_name = kcu.constraint_name AND tc.constraint_schema = kcu.constraint_schema
    JOIN information_schema.constraint_column_usage ccu
      ON ccu.constraint_name = tc.constraint_name AND ccu.constraint_schema = tc.constraint_schema
    WHERE tc.constraint_type = 'FOREIGN KEY'
      AND tc.table_schema = 'public'
      AND tc.table_name = 'sensors'
      AND kcu.column_name = 'owner_id'
      AND ccu.table_name = 'users'
  ) THEN
    ALTER TABLE sensors ADD CONSTRAINT fk_sensors_owner_id_users FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE RESTRICT;
  END IF;
  IF NOT EXISTS (
    SELECT 1
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu
      ON tc.constraint_name = kcu.constraint_name AND tc.constraint_schema = kcu.constraint_schema
    JOIN information_schema.constraint_column_usage ccu
      ON ccu.constraint_name = tc.constraint_name AND ccu.constraint_schema = tc.constraint_schema
    WHERE tc.constraint_type = 'FOREIGN KEY'
      AND tc.table_schema = 'public'
      AND tc.table_name = 'events'
      AND kcu.column_name = 'owner_id'
      AND ccu.table_name = 'users'
  ) THEN
    ALTER TABLE events ADD CONSTRAINT fk_events_owner_id_users FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE RESTRICT;
  END IF;
  IF NOT EXISTS (
    SELECT 1
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu
      ON tc.constraint_name = kcu.constraint_name AND tc.constraint_schema = kcu.constraint_schema
    JOIN information_schema.constraint_column_usage ccu
      ON ccu.constraint_name = tc.constraint_name AND ccu.constraint_schema = tc.constraint_schema
    WHERE tc.constraint_type = 'FOREIGN KEY'
      AND tc.table_schema = 'public'
      AND tc.table_name = 'service_requests'
      AND kcu.column_name = 'owner_id'
      AND ccu.table_name = 'users'
  ) THEN
    ALTER TABLE service_requests ADD CONSTRAINT fk_service_requests_owner_id_users FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE RESTRICT;
  END IF;
  IF NOT EXISTS (
    SELECT 1
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu
      ON tc.constraint_name = kcu.constraint_name AND tc.constraint_schema = kcu.constraint_schema
    JOIN information_schema.constraint_column_usage ccu
      ON ccu.constraint_name = tc.constraint_name AND ccu.constraint_schema = tc.constraint_schema
    WHERE tc.constraint_type = 'FOREIGN KEY'
      AND tc.table_schema = 'public'
      AND tc.table_name = 'technicians'
      AND kcu.column_name = 'owner_id'
      AND ccu.table_name = 'users'
  ) THEN
    ALTER TABLE technicians ADD CONSTRAINT fk_technicians_owner_id_users FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE RESTRICT;
  END IF;
  IF NOT EXISTS (
    SELECT 1
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu
      ON tc.constraint_name = kcu.constraint_name AND tc.constraint_schema = kcu.constraint_schema
    JOIN information_schema.constraint_column_usage ccu
      ON ccu.constraint_name = tc.constraint_name AND ccu.constraint_schema = tc.constraint_schema
    WHERE tc.constraint_type = 'FOREIGN KEY'
      AND tc.table_schema = 'public'
      AND tc.table_name = 'reports'
      AND kcu.column_name = 'owner_id'
      AND ccu.table_name = 'users'
  ) THEN
    ALTER TABLE reports ADD CONSTRAINT fk_reports_owner_id_users FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE RESTRICT;
  END IF;
END $$;

ALTER TABLE lifts            ALTER COLUMN owner_id SET NOT NULL;
ALTER TABLE sensors          ALTER COLUMN owner_id SET NOT NULL;
ALTER TABLE events           ALTER COLUMN owner_id SET NOT NULL;
ALTER TABLE service_requests ALTER COLUMN owner_id SET NOT NULL;
ALTER TABLE technicians      ALTER COLUMN owner_id SET NOT NULL;
ALTER TABLE reports          ALTER COLUMN owner_id SET NOT NULL;

CREATE INDEX IF NOT EXISTS ix_lifts_owner_id            ON lifts(owner_id);
CREATE INDEX IF NOT EXISTS ix_sensors_owner_id          ON sensors(owner_id);
CREATE INDEX IF NOT EXISTS ix_events_owner_id           ON events(owner_id);
CREATE INDEX IF NOT EXISTS ix_service_requests_owner_id ON service_requests(owner_id);
CREATE INDEX IF NOT EXISTS ix_technicians_owner_id      ON technicians(owner_id);
CREATE INDEX IF NOT EXISTS ix_reports_owner_id          ON reports(owner_id);

-- выдаём permissions ролям (как в миграции: admin+dispatcher = всё, technician = ограниченно)
WITH r AS (SELECT id FROM roles WHERE name='administrator'), p AS (SELECT id FROM permissions)
INSERT INTO role_permissions(role_id, permission_id)
SELECT r.id, p.id FROM r, p
ON CONFLICT DO NOTHING;

WITH r AS (SELECT id FROM roles WHERE name='dispatcher'), p AS (SELECT id FROM permissions)
INSERT INTO role_permissions(role_id, permission_id)
SELECT r.id, p.id FROM r, p
ON CONFLICT DO NOTHING;

WITH r AS (SELECT id FROM roles WHERE name='technician')
INSERT INTO role_permissions(role_id, permission_id)
SELECT r.id, p.id
FROM r
JOIN permissions p ON p.name IN (
  'lifts:read',
  'sensors:read',
  'events:read',
  'service_requests:read',
  'service_requests:update',
  'reports:create',
  'reports:read'
)
ON CONFLICT DO NOTHING;

COMMIT;
