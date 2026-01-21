-- Добавление индексов для ускорения запросов platonus_employees

-- Индекс для поиска по IIN (часто используется для JOIN)
CREATE INDEX IF NOT EXISTS idx_platonus_employees_iin
ON platonus_employees(iin);

-- Индекс для фильтрации по faculty_id
CREATE INDEX IF NOT EXISTS idx_platonus_employees_faculty_id
ON platonus_employees(faculty_id);

-- Индекс для фильтрации по subdivision_id
CREATE INDEX IF NOT EXISTS idx_platonus_employees_subdivision_id
ON platonus_employees(subdivision_id);

-- Индекс для фильтрации по position_type
CREATE INDEX IF NOT EXISTS idx_platonus_employees_position_type
ON platonus_employees(position_type);

-- Составной индекс для сортировки по ФИО
CREATE INDEX IF NOT EXISTS idx_platonus_employees_name
ON platonus_employees(lastname, firstname);

-- Проверить созданные индексы
SELECT
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE tablename = 'platonus_employees'
ORDER BY indexname;
