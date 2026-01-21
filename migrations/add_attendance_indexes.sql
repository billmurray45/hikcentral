-- Добавление индексов для ускорения запросов attendance

-- Составной индекс для быстрого поиска по IIN и дате
CREATE INDEX IF NOT EXISTS idx_attendance_iin_date
ON attendance_records(iin, access_date);

-- Составной индекс для поиска по IIN, дате и направлению (для опоздавших)
CREATE INDEX IF NOT EXISTS idx_attendance_iin_date_direction
ON attendance_records(iin, access_date, direction);

-- Индекс для фильтрации по дате (если уже нет)
CREATE INDEX IF NOT EXISTS idx_attendance_access_date
ON attendance_records(access_date);

-- Индекс для сортировки по времени
CREATE INDEX IF NOT EXISTS idx_attendance_datetime
ON attendance_records(access_datetime);

-- Индекс для фильтрации по направлению
CREATE INDEX IF NOT EXISTS idx_attendance_direction
ON attendance_records(direction);

-- Проверить созданные индексы
SELECT
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE tablename = 'attendance_records'
ORDER BY indexname;
