"""
Скрипт для создания таблицы platonus_employees в PostgreSQL
"""

import asyncio
import asyncpg

async def create_table():
    """Создать таблицу platonus_employees"""

    # Подключение к БД
    conn = await asyncpg.connect(
        host='172.16.65.214',
        port=5432,
        user='hr_readonly',
        password='Bauka2745!',
        database='hikvision_sync'
    )

    try:
        print("✅ Подключено к базе данных")

        # Прочитать SQL из файла
        with open('create_platonus_employees_table.sql', 'r', encoding='utf-8') as f:
            sql = f.read()

        print("\n📝 Выполнение SQL скрипта...")

        # Выполнить SQL
        await conn.execute(sql)

        print("✅ Таблица platonus_employees успешно создана!")

        # Проверить что таблица создана
        result = await conn.fetchval("""
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_name = 'platonus_employees';
        """)

        if result > 0:
            print("✅ Проверка: таблица существует в БД")

            # Показать структуру таблицы
            columns = await conn.fetch("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'platonus_employees'
                ORDER BY ordinal_position;
            """)

            print(f"\n📋 Структура таблицы ({len(columns)} колонок):")
            for col in columns:
                print(f"   - {col['column_name']:25} {col['data_type']:20} NULL: {col['is_nullable']}")
        else:
            print("⚠️  Таблица не найдена после создания")

    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        raise
    finally:
        await conn.close()
        print("\n🔒 Соединение закрыто")

if __name__ == "__main__":
    asyncio.run(create_table())
