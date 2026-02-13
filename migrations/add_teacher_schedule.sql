-- ============================================================================
-- Миграция: Добавление таблицы расписания преподавателей
-- Дата: 2026-02-13
-- Описание: Создание таблицы teacher_schedule для хранения расписания
--           преподавателей из Platonus с денормализованной структурой
-- ============================================================================

-- ============================================================================
-- 1. Создание таблицы teacher_schedule
-- ============================================================================

CREATE TABLE IF NOT EXISTS teacher_schedule (
    id SERIAL PRIMARY KEY,

    -- Идентификация преподавателя
    iin VARCHAR(12) NOT NULL,                      -- ИИН преподавателя (связь с platonus_employees)

    -- Информация о занятии
    week_day SMALLINT NOT NULL CHECK (week_day BETWEEN 1 AND 7),  -- День недели (1=Пн, 7=Вс)
    lesson_number SMALLINT NOT NULL,               -- ID из lesson_hours (для связи с Platonus)
    lesson_start TIME NOT NULL,                    -- Время начала пары
    lesson_finish TIME NOT NULL,                   -- Время окончания пары

    -- Информация о предмете и группе
    subject_name VARCHAR(500) NOT NULL,            -- Название предмета
    group_name VARCHAR(200) NOT NULL,              -- Название группы

    -- Информация об аудитории
    auditory_number VARCHAR(50),                   -- Номер аудитории
    building_number VARCHAR(50),                   -- Номер корпуса

    -- Учебный год и семестр
    study_year SMALLINT NOT NULL,                  -- Учебный год (например, 2025)
    study_term SMALLINT NOT NULL CHECK (study_term IN (1, 2)),  -- Семестр (1 или 2)

    -- Связь с Platonus (для отладки и обновлений)
    platonus_lesson_id INTEGER,                    -- ID занятия в timetable
    platonus_study_group_id INTEGER,               -- ID учебной группы в studygroups

    -- Метаданные
    synced_at TIMESTAMP DEFAULT NOW(),             -- Когда последний раз синхронизировано
    created_at TIMESTAMP DEFAULT NOW(),            -- Дата создания записи
    updated_at TIMESTAMP DEFAULT NOW(),            -- Дата последнего обновления

    -- Внешний ключ на platonus_employees
    CONSTRAINT fk_teacher_iin FOREIGN KEY (iin)
        REFERENCES platonus_employees(iin)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    -- Проверка времени
    CONSTRAINT check_lesson_time CHECK (lesson_start < lesson_finish)
);

-- Комментарии к таблице и колонкам
COMMENT ON TABLE teacher_schedule IS 'Расписание преподавателей из Platonus (денормализованная копия для быстрого доступа)';
COMMENT ON COLUMN teacher_schedule.iin IS 'ИИН преподавателя (связь с platonus_employees)';
COMMENT ON COLUMN teacher_schedule.week_day IS 'День недели: 1=Понедельник, 2=Вторник, ..., 7=Воскресенье';
COMMENT ON COLUMN teacher_schedule.lesson_number IS 'Номер пары (обычно 1-10)';
COMMENT ON COLUMN teacher_schedule.lesson_start IS 'Время начала пары (например, 09:00)';
COMMENT ON COLUMN teacher_schedule.lesson_finish IS 'Время окончания пары (например, 10:30)';
COMMENT ON COLUMN teacher_schedule.subject_name IS 'Название предмета';
COMMENT ON COLUMN teacher_schedule.group_name IS 'Название учебной группы';
COMMENT ON COLUMN teacher_schedule.auditory_number IS 'Номер аудитории';
COMMENT ON COLUMN teacher_schedule.building_number IS 'Номер корпуса';
COMMENT ON COLUMN teacher_schedule.study_year IS 'Учебный год (например, 2025 для 2025-2026 уч.года)';
COMMENT ON COLUMN teacher_schedule.study_term IS 'Семестр: 1 или 2';
COMMENT ON COLUMN teacher_schedule.platonus_lesson_id IS 'ID занятия в Platonus (timetable.lessonID)';
COMMENT ON COLUMN teacher_schedule.platonus_study_group_id IS 'ID учебной группы в Platonus (studygroups.studyGroupID)';
COMMENT ON COLUMN teacher_schedule.synced_at IS 'Дата и время последней синхронизации из Platonus';

-- ============================================================================
-- 2. Создание индексов для быстрого поиска
-- ============================================================================

-- Основной композитный индекс для быстрого поиска расписания преподавателя
CREATE INDEX IF NOT EXISTS idx_teacher_schedule_iin_day_lesson
ON teacher_schedule(iin, week_day, lesson_number);

-- Индекс для поиска всех занятий преподавателя
CREATE INDEX IF NOT EXISTS idx_teacher_schedule_iin
ON teacher_schedule(iin);

-- Индекс для поиска по учебному году и семестру
CREATE INDEX IF NOT EXISTS idx_teacher_schedule_year_term
ON teacher_schedule(study_year, study_term);

-- Индекс для поиска занятий по дню недели
CREATE INDEX IF NOT EXISTS idx_teacher_schedule_week_day
ON teacher_schedule(week_day);

-- Индекс для отслеживания синхронизации
CREATE INDEX IF NOT EXISTS idx_teacher_schedule_synced_at
ON teacher_schedule(synced_at DESC);

-- Индекс для поиска по Platonus lesson ID (для отладки)
CREATE INDEX IF NOT EXISTS idx_teacher_schedule_platonus_lesson
ON teacher_schedule(platonus_lesson_id)
WHERE platonus_lesson_id IS NOT NULL;

-- ============================================================================
-- 3. Создание функции для автоматического обновления updated_at
-- ============================================================================

CREATE OR REPLACE FUNCTION update_teacher_schedule_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- 4. Создание триггера
-- ============================================================================

DROP TRIGGER IF EXISTS trigger_update_teacher_schedule_timestamp ON teacher_schedule;

CREATE TRIGGER trigger_update_teacher_schedule_timestamp
BEFORE UPDATE ON teacher_schedule
FOR EACH ROW
EXECUTE FUNCTION update_teacher_schedule_updated_at();

-- ============================================================================
-- 5. Создание представления для удобного просмотра расписания
-- ============================================================================

CREATE OR REPLACE VIEW v_teacher_schedule_detailed AS
SELECT
    ts.id,
    ts.iin,
    pe.firstname,
    pe.lastname,
    pe.patronymic,
    CONCAT(pe.lastname, ' ', pe.firstname, ' ', COALESCE(pe.patronymic, '')) as full_name,
    CASE ts.week_day
        WHEN 1 THEN 'Понедельник'
        WHEN 2 THEN 'Вторник'
        WHEN 3 THEN 'Среда'
        WHEN 4 THEN 'Четверг'
        WHEN 5 THEN 'Пятница'
        WHEN 6 THEN 'Суббота'
        WHEN 7 THEN 'Воскресенье'
    END as day_name_ru,
    CASE ts.week_day
        WHEN 1 THEN 'Monday'
        WHEN 2 THEN 'Tuesday'
        WHEN 3 THEN 'Wednesday'
        WHEN 4 THEN 'Thursday'
        WHEN 5 THEN 'Friday'
        WHEN 6 THEN 'Saturday'
        WHEN 7 THEN 'Sunday'
    END as day_name_en,
    ts.week_day,
    ts.lesson_number,
    ts.lesson_start,
    ts.lesson_finish,
    CONCAT(TO_CHAR(ts.lesson_start, 'HH24:MI'), '-', TO_CHAR(ts.lesson_finish, 'HH24:MI')) as time_range,
    ts.subject_name,
    ts.group_name,
    ts.auditory_number,
    ts.building_number,
    CASE
        WHEN ts.auditory_number IS NOT NULL AND ts.building_number IS NOT NULL
        THEN CONCAT(ts.building_number, '-', ts.auditory_number)
        ELSE NULL
    END as full_auditory,
    ts.study_year,
    ts.study_term,
    CONCAT(ts.study_year, '-', ts.study_year + 1, ' уч.год, ', ts.study_term, ' семестр') as academic_period,
    ts.synced_at,
    ts.created_at,
    ts.updated_at
FROM teacher_schedule ts
LEFT JOIN platonus_employees pe ON ts.iin = pe.iin;

COMMENT ON VIEW v_teacher_schedule_detailed IS 'Детальное представление расписания преподавателей с именами и форматированными данными';

-- ============================================================================
-- 6. Проверка созданных данных (после первой синхронизации)
-- ============================================================================

-- Статистика по расписанию
SELECT
    study_year,
    study_term,
    COUNT(*) as total_lessons,
    COUNT(DISTINCT iin) as total_teachers,
    COUNT(DISTINCT subject_name) as total_subjects,
    COUNT(DISTINCT group_name) as total_groups
FROM teacher_schedule
GROUP BY study_year, study_term
ORDER BY study_year DESC, study_term DESC;

-- Топ-10 преподавателей по количеству занятий
SELECT
    iin,
    COUNT(*) as lessons_count,
    COUNT(DISTINCT subject_name) as subjects_count,
    COUNT(DISTINCT group_name) as groups_count
FROM teacher_schedule
WHERE study_year = 2025 AND study_term = 2
GROUP BY iin
ORDER BY lessons_count DESC
LIMIT 10;

-- ============================================================================
-- ROLLBACK (если нужно откатить миграцию)
-- ============================================================================

-- Раскомментируйте следующие строки для отката миграции:
-- DROP VIEW IF EXISTS v_teacher_schedule_detailed;
-- DROP TRIGGER IF EXISTS trigger_update_teacher_schedule_timestamp ON teacher_schedule;
-- DROP FUNCTION IF EXISTS update_teacher_schedule_updated_at();
-- DROP TABLE IF EXISTS teacher_schedule;

-- ============================================================================
-- КОНЕЦ МИГРАЦИИ
-- ============================================================================
