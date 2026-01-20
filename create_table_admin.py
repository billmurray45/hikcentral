"""
Скрипт для создания таблицы platonus_employees в PostgreSQL
Используйте пользователя с правами CREATE TABLE
"""

import asyncio
import asyncpg
import sys

async def create_table(user: str, password: str):
    """Создать таблицу platonus_employees"""

    # Подключение к БД
    conn = await asyncpg.connect(
        host='172.16.65.214',
        port=5432,
        user=user,
        password=password,
        database='hikvision_sync'
    )

    try:
        print(f"✅ Подключено к базе данных (пользователь: {user})")

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

            # Дать права пользователю hr_readonly на чтение
            print("\n🔒 Выдача прав на чтение для hr_readonly...")
            await conn.execute("GRANT SELECT ON platonus_employees TO hr_readonly;")
            print("✅ Права выданы")

        else:
            print("⚠️  Таблица не найдена после создания")

    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        raise
    finally:
        await conn.close()
        print("\n🔒 Соединение закрыто")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Использование: python create_table_admin.py <username> <password>")
        print("\nПримеры:")
        print("  python create_table_admin.py postgres mypassword")
        print("  python create_table_admin.py hikcentral_user mypassword")
        sys.exit(1)

    user = sys.argv[1]
    password = sys.argv[2]
    asyncio.run(create_table(user, password))
