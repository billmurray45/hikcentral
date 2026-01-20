-- Добавление полей для структурных подразделений
-- Для сотрудников административного персонала без кафедры

-- Добавить колонки
ALTER TABLE platonus_employees
ADD COLUMN IF NOT EXISTS subdivision_id INTEGER,
ADD COLUMN IF NOT EXISTS subdivision_name VARCHAR(256),
ADD COLUMN IF NOT EXISTS subdivision_type INTEGER;

-- Создать индекс
CREATE INDEX IF NOT EXISTS idx_platonus_employees_subdivision_id
ON platonus_employees(subdivision_id);

-- Проверить результат
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'platonus_employees'
ORDER BY ordinal_position;
