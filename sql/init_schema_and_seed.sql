-- =============================================================================
-- PostgreSQL: схема + демо-данные для системы контроля лифтов
-- Соответствует моделям приложения (строковые статусы как в domain/enums.py)
-- =============================================================================
-- Перед первым запуском создайте БД, например:
--   CREATE DATABASE elevator_control OWNER your_user ENCODING 'UTF8';
-- Затем выполните этот файл от имени пользователя с правом CREATE на эту БД:
--   psql -U your_user -d elevator_control -f init_schema_and_seed.sql
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- Очистка (раскомментируйте, если нужно пересоздать таблицы с нуля)
-- ---------------------------------------------------------------------------
-- DROP TABLE IF EXISTS reports CASCADE;
-- DROP TABLE IF EXISTS service_requests CASCADE;
-- DROP TABLE IF EXISTS events CASCADE;
-- DROP TABLE IF EXISTS sensors CASCADE;
-- DROP TABLE IF EXISTS lifts CASCADE;
-- DROP TABLE IF EXISTS technicians CASCADE;

-- ---------------------------------------------------------------------------
-- Таблицы (порядок: сначала независимые, затем с внешними ключами)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS lifts (
    id              SERIAL PRIMARY KEY,
    model           VARCHAR(128) NOT NULL,
    status          VARCHAR(32)  NOT NULL,
    location        VARCHAR(256) NOT NULL,
    is_emergency    BOOLEAN      NOT NULL DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS ix_lifts_status ON lifts (status);

-- status: free | busy
CREATE TABLE IF NOT EXISTS technicians (
    id      SERIAL PRIMARY KEY,
    name    VARCHAR(128) NOT NULL,
    status  VARCHAR(32) NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_technicians_status ON technicians (status);

CREATE TABLE IF NOT EXISTS sensors (
    id               SERIAL PRIMARY KEY,
    lift_id          INTEGER NOT NULL REFERENCES lifts (id) ON DELETE CASCADE,
    sensor_type      VARCHAR(64) NOT NULL,
    current_value    DOUBLE PRECISION NOT NULL,
    threshold_norm   DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_sensors_lift_id ON sensors (lift_id);

-- event_type: warning | critical
-- status: new | in_progress | resolved
CREATE TABLE IF NOT EXISTS events (
    id           SERIAL PRIMARY KEY,
    lift_id      INTEGER NOT NULL REFERENCES lifts (id) ON DELETE CASCADE,
    event_type   VARCHAR(32) NOT NULL,
    description  TEXT NOT NULL,
    status       VARCHAR(32) NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_events_lift_id ON events (lift_id);
CREATE INDEX IF NOT EXISTS ix_events_event_type ON events (event_type);
CREATE INDEX IF NOT EXISTS ix_events_status ON events (status);

-- status: pending | assigned | in_progress | completed | cancelled
CREATE TABLE IF NOT EXISTS service_requests (
    id             SERIAL PRIMARY KEY,
    lift_id        INTEGER NOT NULL REFERENCES lifts (id) ON DELETE CASCADE,
    reason         TEXT NOT NULL,
    status         VARCHAR(32) NOT NULL,
    technician_id  INTEGER REFERENCES technicians (id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS ix_service_requests_lift_id ON service_requests (lift_id);
CREATE INDEX IF NOT EXISTS ix_service_requests_status ON service_requests (status);
CREATE INDEX IF NOT EXISTS ix_service_requests_technician_id ON service_requests (technician_id);

-- final_lift_status: active | stopped | maintenance
CREATE TABLE IF NOT EXISTS reports (
    id                   SERIAL PRIMARY KEY,
    service_request_id   INTEGER NOT NULL REFERENCES service_requests (id) ON DELETE CASCADE,
    work_description     TEXT NOT NULL,
    final_lift_status    VARCHAR(32) NOT NULL,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_reports_service_request_id ON reports (service_request_id);

-- ---------------------------------------------------------------------------
-- Демо-данные (осмысленный сценарий: два лифта, техники, датчики, заявки)
-- Значения статусов строго как в Python Enum (нижний регистр, snake_case)
-- ---------------------------------------------------------------------------

INSERT INTO lifts (id, model, status, location, is_emergency) VALUES
    (1, 'KONE MonoSpace', 'active',      'Корпус А, подъезд 1', FALSE),
    (2, 'OTIS Gen2',      'stopped',     'Корпус Б, подъезд 2', TRUE),
    (3, 'Schindler 3300', 'maintenance', 'Склад, испытательный стенд', FALSE)
ON CONFLICT (id) DO UPDATE SET
    model = EXCLUDED.model,
    status = EXCLUDED.status,
    location = EXCLUDED.location,
    is_emergency = EXCLUDED.is_emergency;

INSERT INTO technicians (id, name, status) VALUES
    (1, 'Иванов Иван Иванович',       'free'),
    (2, 'Пётр Петрович Смирнов',    'busy'),
    (3, 'Алексей Кузнецов',         'free')
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    status = EXCLUDED.status;

-- Датчики: показания ниже порога — фоновая симуляция будет плавно менять current_value
INSERT INTO sensors (id, lift_id, sensor_type, current_value, threshold_norm) VALUES
    (1, 1, 'temperature', 26.0, 40.0),
    (2, 1, 'door',         0.0,  1.0),
    (3, 1, 'overload',     0.4,  1.0),
    (4, 2, 'temperature', 48.0, 40.0),
    (5, 2, 'overload',     0.95, 1.0),
    (6, 3, 'temperature', 22.0, 35.0)
ON CONFLICT (id) DO UPDATE SET
    lift_id = EXCLUDED.lift_id,
    sensor_type = EXCLUDED.sensor_type,
    current_value = EXCLUDED.current_value,
    threshold_norm = EXCLUDED.threshold_norm;

INSERT INTO events (id, lift_id, event_type, description, status) VALUES
    (1, 1, 'warning',
        'Предупреждение по датчику «temperature»: отклонение от нормы (ручная запись демо).',
        'new'),
    (2, 2, 'critical',
        'Критическое отклонение: температура/нагрузка — аварийная остановка (демо).',
        'in_progress')
ON CONFLICT (id) DO UPDATE SET
    lift_id = EXCLUDED.lift_id,
    event_type = EXCLUDED.event_type,
    description = EXCLUDED.description,
    status = EXCLUDED.status;

INSERT INTO service_requests (id, lift_id, reason, status, technician_id) VALUES
    (1, 2,
        'Автоматическая заявка: критическое состояние лифта OTIS Gen2 (демо-данные).',
        'in_progress', 2),
    (2, 1,
        'Плановый осмотр после предупреждения по температуре.',
        'pending', NULL),
    (3, 3,
        'Текущее техобслуживание на стенде (заявка закрыта отчётом ниже).',
        'completed', 1)
ON CONFLICT (id) DO UPDATE SET
    lift_id = EXCLUDED.lift_id,
    reason = EXCLUDED.reason,
    status = EXCLUDED.status,
    technician_id = EXCLUDED.technician_id;

-- Согласованность: занят только техник с активной заявкой in_progress (id 2); остальные free
UPDATE technicians SET status = 'free' WHERE id IN (1, 3);
UPDATE technicians SET status = 'busy' WHERE id = 2;

INSERT INTO reports (id, service_request_id, work_description, final_lift_status, created_at) VALUES
    (1, 3,
        'Проведена ревизия тормоза, смазка направляющих. Испытания пройдены.',
        'maintenance',
        NOW() - INTERVAL '2 days')
ON CONFLICT (id) DO UPDATE SET
    service_request_id = EXCLUDED.service_request_id,
    work_description = EXCLUDED.work_description,
    final_lift_status = EXCLUDED.final_lift_status,
    created_at = EXCLUDED.created_at;

-- ---------------------------------------------------------------------------
-- Синхронизация последовательностей SERIAL после явных id в INSERT
-- ---------------------------------------------------------------------------
SELECT setval(pg_get_serial_sequence('lifts', 'id'),              COALESCE((SELECT MAX(id) FROM lifts), 1));
SELECT setval(pg_get_serial_sequence('technicians', 'id'),      COALESCE((SELECT MAX(id) FROM technicians), 1));
SELECT setval(pg_get_serial_sequence('sensors', 'id'),          COALESCE((SELECT MAX(id) FROM sensors), 1));
SELECT setval(pg_get_serial_sequence('events', 'id'),           COALESCE((SELECT MAX(id) FROM events), 1));
SELECT setval(pg_get_serial_sequence('service_requests', 'id'), COALESCE((SELECT MAX(id) FROM service_requests), 1));
SELECT setval(pg_get_serial_sequence('reports', 'id'),          COALESCE((SELECT MAX(id) FROM reports), 1));

COMMIT;

-- Проверка количества строк:
-- SELECT 'lifts' AS t, COUNT(*) FROM lifts
-- UNION ALL SELECT 'technicians', COUNT(*) FROM technicians
-- UNION ALL SELECT 'sensors', COUNT(*) FROM sensors
-- UNION ALL SELECT 'events', COUNT(*) FROM events
-- UNION ALL SELECT 'service_requests', COUNT(*) FROM service_requests
-- UNION ALL SELECT 'reports', COUNT(*) FROM reports;
