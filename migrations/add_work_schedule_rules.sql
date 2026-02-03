-- ============================================================================
-- Миграция: Добавление таблицы правил рабочего времени
-- Дата: 2026-02-03
-- Описание: Создание таблицы work_schedule_rules для хранения правил
--           начала рабочего дня для разных должностей
-- ============================================================================

-- ============================================================================
-- 1. Создание таблицы work_schedule_rules
-- ============================================================================

CREATE TABLE IF NOT EXISTS work_schedule_rules (
    id SERIAL PRIMARY KEY,

    -- Условие применения правила (одно из двух должно быть заполнено)
    position_type VARCHAR(100),           -- Тип должности (Преподаватель, Административный персонал и т.д.)
    position VARCHAR(255),                -- Конкретная должность (Охранник, Профессор и т.д.)

    -- Дополнительные фильтры (опционально)
    faculty_id INTEGER,                   -- ID факультета (NULL = для всех)
    subdivision_id INTEGER,               -- ID подразделения (NULL = для всех)

    -- Рабочее время
    start_time TIME NOT NULL,             -- Время начала работы (порог опоздания)
    end_time TIME,                        -- Время окончания работы (опционально)

    -- Дни недели (опционально, NULL = все дни)
    apply_days VARCHAR(50),               -- JSON массив: ["Monday", "Tuesday", ...] или NULL для всех дней

    -- Период действия правила (опционально)
    valid_from DATE,                      -- Дата начала действия (NULL = всегда)
    valid_to DATE,                        -- Дата окончания действия (NULL = бессрочно)

    -- Приоритет и статус
    priority INTEGER DEFAULT 0,           -- Приоритет (больше = выше, для разрешения конфликтов)
    is_active BOOLEAN DEFAULT TRUE,       -- Активно ли правило

    -- Метаданные
    description TEXT,                     -- Описание правила
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    created_by VARCHAR(100),              -- Кто создал правило

    -- Ограничения
    CONSTRAINT check_has_condition CHECK (
        position_type IS NOT NULL OR position IS NOT NULL
    ),
    CONSTRAINT check_valid_dates CHECK (
        valid_from IS NULL OR valid_to IS NULL OR valid_from <= valid_to
    )
);

-- Комментарии к таблице и колонкам
COMMENT ON TABLE work_schedule_rules IS 'Правила рабочего времени для разных должностей';
COMMENT ON COLUMN work_schedule_rules.position_type IS 'Тип должности (применяется ко всем с этим типом)';
COMMENT ON COLUMN work_schedule_rules.position IS 'Конкретная должность (точное или частичное совпадение)';
COMMENT ON COLUMN work_schedule_rules.start_time IS 'Время начала работы (порог для определения опоздания)';
COMMENT ON COLUMN work_schedule_rules.end_time IS 'Время окончания работы (опционально)';
COMMENT ON COLUMN work_schedule_rules.priority IS 'Приоритет правила (больше = выше приоритет при конфликтах)';
COMMENT ON COLUMN work_schedule_rules.apply_days IS 'Дни недели когда правило действует (JSON массив или NULL для всех дней)';

-- ============================================================================
-- 2. Создание индексов для быстрого поиска
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_work_schedule_position_type
ON work_schedule_rules(position_type)
WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_work_schedule_position
ON work_schedule_rules(position)
WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_work_schedule_faculty
ON work_schedule_rules(faculty_id)
WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_work_schedule_subdivision
ON work_schedule_rules(subdivision_id)
WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_work_schedule_priority
ON work_schedule_rules(priority DESC, id)
WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_work_schedule_active
ON work_schedule_rules(is_active, priority DESC);

-- ============================================================================
-- 3. Создание функции для автоматического обновления updated_at
-- ============================================================================

CREATE OR REPLACE FUNCTION update_work_schedule_rules_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- 4. Создание триггера
-- ============================================================================

DROP TRIGGER IF EXISTS trigger_update_work_schedule_rules_timestamp ON work_schedule_rules;

CREATE TRIGGER trigger_update_work_schedule_rules_timestamp
BEFORE UPDATE ON work_schedule_rules
FOR EACH ROW
EXECUTE FUNCTION update_work_schedule_rules_updated_at();

-- ============================================================================
-- 5. Вставка дефолтных правил (примеры)
-- ============================================================================

-- Правило по умолчанию для всех сотрудников
INSERT INTO work_schedule_rules
(position_type, start_time, priority, description, created_by, is_active)
VALUES
('Все сотрудники', '09:00:00', 0, 'Правило по умолчанию для всех сотрудников', 'system', TRUE)
ON CONFLICT DO NOTHING;

-- Административный персонал приходит раньше
INSERT INTO work_schedule_rules
(position_type, start_time, end_time, priority, description, created_by, is_active)
VALUES
('Административный персонал', '08:30:00', '17:30:00', 10, 'Административный персонал работает с 08:30 до 17:30', 'system', TRUE)
ON CONFLICT DO NOTHING;

-- Охранники работают в 2 смены (пример для ранней смены)
INSERT INTO work_schedule_rules
(position, start_time, end_time, priority, description, created_by, is_active)
VALUES
('Охранник', '08:00:00', '20:00:00', 20, 'Охранники - дневная смена с 08:00 до 20:00', 'system', TRUE)
ON CONFLICT DO NOTHING;

-- Преподаватели
INSERT INTO work_schedule_rules
(position_type, start_time, end_time, priority, description, created_by, is_active)
VALUES
('Преподаватель', '09:00:00', '18:00:00', 10, 'Преподаватели работают с 09:00 до 18:00', 'system', TRUE)
ON CONFLICT DO NOTHING;

-- Руководители
INSERT INTO work_schedule_rules
(position_type, start_time, end_time, priority, description, created_by, is_active)
VALUES
('Руководитель', '09:00:00', '18:00:00', 10, 'Руководители работают с 09:00 до 18:00', 'system', TRUE)
ON CONFLICT DO NOTHING;

-- Технический персонал
INSERT INTO work_schedule_rules
(position_type, start_time, end_time, priority, description, created_by, is_active)
VALUES
('Технический персонал', '08:00:00', '17:00:00', 10, 'Технический персонал работает с 08:00 до 17:00', 'system', TRUE)
ON CONFLICT DO NOTHING;

-- Специалисты
INSERT INTO work_schedule_rules
(position_type, start_time, end_time, priority, description, created_by, is_active)
VALUES
('Специалист', '08:30:00', '17:30:00', 10, 'Специалисты работают с 08:30 до 17:30', 'system', TRUE)
ON CONFLICT DO NOTHING;

-- ============================================================================
-- 6. Проверка созданных данных
-- ============================================================================

-- Вывести все активные правила
SELECT
    id,
    position_type,
    position,
    start_time,
    end_time,
    priority,
    description,
    is_active
FROM work_schedule_rules
WHERE is_active = TRUE
ORDER BY priority DESC, id;

-- ============================================================================
-- ROLLBACK (если нужно откатить миграцию)
-- ============================================================================

-- Раскомментируйте следующие строки для отката миграции:
-- DROP TRIGGER IF EXISTS trigger_update_work_schedule_rules_timestamp ON work_schedule_rules;
-- DROP FUNCTION IF EXISTS update_work_schedule_rules_updated_at();
-- DROP TABLE IF EXISTS work_schedule_rules;

-- ============================================================================
-- КОНЕЦ МИГРАЦИИ
-- ============================================================================
