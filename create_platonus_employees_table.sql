-- Создание таблицы platonus_employees для кеширования данных сотрудников из Platonus

CREATE TABLE IF NOT EXISTS platonus_employees (
    -- Первичный ключ - IIN
    iin VARCHAR(12) PRIMARY KEY,

    -- Данные из Platonus
    tutor_id INTEGER NOT NULL,
    firstname VARCHAR(128) NOT NULL,
    lastname VARCHAR(128) NOT NULL,
    patronymic VARCHAR(128),

    -- Должность
    position VARCHAR(256),
    position_type VARCHAR(50),

    -- Структура
    cafedra_id INTEGER,
    cafedra_name VARCHAR(256),
    faculty_id INTEGER,
    faculty_name VARCHAR(256),

    -- Контакты
    email VARCHAR(512),
    phone VARCHAR(128),

    -- Служебные поля
    synced_at TIMESTAMP NOT NULL DEFAULT NOW(),
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Индексы для быстрого поиска
CREATE INDEX IF NOT EXISTS idx_platonus_employees_faculty_id ON platonus_employees(faculty_id);
CREATE INDEX IF NOT EXISTS idx_platonus_employees_position_type ON platonus_employees(position_type);
CREATE INDEX IF NOT EXISTS idx_platonus_employees_synced_at ON platonus_employees(synced_at);

-- Комментарии
COMMENT ON TABLE platonus_employees IS 'Кеш данных сотрудников из Platonus (синхронизация раз в неделю)';
COMMENT ON COLUMN platonus_employees.iin IS 'ИИН сотрудника';
COMMENT ON COLUMN platonus_employees.tutor_id IS 'ID в таблице tutors (Platonus)';
COMMENT ON COLUMN platonus_employees.position_type IS 'Тип должности (Преподаватель/Руководитель/Специалист/и т.д.)';
COMMENT ON COLUMN platonus_employees.synced_at IS 'Дата последней синхронизации';
