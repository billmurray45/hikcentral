"""
Тестовый скрипт для подключения к Platonus через SSH туннель
ОБНОВЛЕНО: Использует MySQL вместо PostgreSQL
"""

import sys
from sshtunnel import SSHTunnelForwarder
from sqlalchemy import create_engine, text, inspect

# SSH параметры
SSH_HOST = "77.245.103.155"
SSH_PORT = 7244
SSH_USER = "platonus_yu"
SSH_PASSWORD = "rCcSwNZe"

# MySQL параметры (через SSH туннель)
DB_HOST = "localhost"  # localhost на удаленном сервере
DB_PORT = 6080  # Нестандартный порт Platonus
DB_NAME = "nitro"
DB_USER = "platonsel"
DB_PASSWORD = "KJh6H823hd8"


def test_ssh_tunnel_sync():
    """
    Синхронное подключение через SSH туннель к MySQL
    """
    print("=" * 80)
    print("🔐 ТЕСТ ПОДКЛЮЧЕНИЯ К PLATONUS MYSQL ЧЕРЕЗ SSH ТУННЕЛЬ")
    print("=" * 80)

    print(f"\n📡 SSH Server: {SSH_HOST}:{SSH_PORT}")
    print(f"👤 SSH User: {SSH_USER}")
    print(f"🗄️  Database: {DB_NAME}")
    print(f"👤 DB User: {DB_USER}")

    try:
        print("\n🔌 Создание SSH туннеля...")

        # Создать SSH туннель
        with SSHTunnelForwarder(
            (SSH_HOST, SSH_PORT),
            ssh_username=SSH_USER,
            ssh_password=SSH_PASSWORD,
            remote_bind_address=(DB_HOST, DB_PORT),
            local_bind_address=('127.0.0.1', 0)  # Автоматический выбор локального порта
        ) as tunnel:

            print(f"✅ SSH туннель создан!")
            print(f"   Локальный порт: {tunnel.local_bind_port}")

            # Подключиться к MySQL через туннель
            print("\n🔌 Подключение к MySQL...")

            db_url = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@127.0.0.1:{tunnel.local_bind_port}/{DB_NAME}?charset=utf8mb4"
            engine = create_engine(db_url, echo=False)

            with engine.connect() as connection:
                print("✅ Подключение к БД успешно!\n")

                # Тест 1: Версия MySQL
                print("=" * 80)
                print("📊 ИНФОРМАЦИЯ О БД")
                print("=" * 80)
                result = connection.execute(text("SELECT VERSION();"))
                version = result.scalar()
                print(f"MySQL версия: {version}\n")

                # Получить имя текущей базы данных
                result = connection.execute(text("SELECT DATABASE();"))
                current_db = result.scalar()
                print(f"Текущая база: {current_db}\n")

                # Тест 2: Список таблиц
                print("=" * 80)
                print("📋 СПИСОК ТАБЛИЦ")
                print("=" * 80)

                # Получить все таблицы из текущей БД
                result = connection.execute(text("SHOW TABLES;"))
                tables = [row[0] for row in result]

                print(f"Таблиц в базе '{DB_NAME}': {len(tables)}")

                if tables:
                    print("\nПервые 30 таблиц:")
                    for idx, table in enumerate(tables[:30], 1):
                        print(f"  {idx}. {table}")

                    if len(tables) > 30:
                        print(f"  ... и еще {len(tables) - 30} таблиц")
                else:
                    print("  Таблицы не найдены")

                # Тест 3: Поиск таблиц со студентами и пользователями
                print("\n" + "=" * 80)
                print("🔍 ПОИСК КЛЮЧЕВЫХ ТАБЛИЦ")
                print("=" * 80)

                keywords = ['student', 'user', 'person', 'employee', 'teacher', 'faculty', 'department', 'staff', 'stud', 'emp']
                found_tables = []

                for keyword in keywords:
                    matching = [t for t in tables if keyword.lower() in t.lower()]
                    if matching:
                        found_tables.extend(matching)
                        print(f"\n📁 Таблицы с '{keyword}':")
                        for table in matching:
                            print(f"   - {table}")

                # Тест 4: Проверка наличия поля IIN
                print("\n" + "=" * 80)
                print("🔑 ПОИСК ТАБЛИЦ С ПОЛЕМ IIN")
                print("=" * 80)

                tables_with_iin = []
                print(f"Проверка {min(100, len(tables))} таблиц...\n")

                for table in tables[:100]:  # Проверим первые 100 таблиц
                    try:
                        # Получить структуру таблицы
                        result = connection.execute(text(f"DESCRIBE `{table}`;"))
                        columns = [row[0].lower() for row in result]

                        if 'iin' in columns or 'inn' in columns:
                            tables_with_iin.append(table)
                            # Показать структуру таблицы с IIN
                            result = connection.execute(text(f"DESCRIBE `{table}`;"))
                            column_info = list(result)
                            print(f"   ✓ {table}:")
                            for col in column_info:
                                if col[0].lower() in ['iin', 'inn']:
                                    print(f"      - {col[0]} ({col[1]})")
                    except Exception as e:
                        continue

                if not tables_with_iin:
                    print("   Поле IIN не найдено в первых 100 таблицах")

                # Тест 5: Исследование найденных таблиц
                print("\n" + "=" * 80)
                print("📈 ИССЛЕДОВАНИЕ КЛЮЧЕВЫХ ТАБЛИЦ")
                print("=" * 80)

                # Найти самые вероятные таблицы со студентами
                priority_tables = [t for t in tables if 'student' in t.lower() or 'stud' in t.lower()]

                if not priority_tables:
                    priority_tables = tables_with_iin[:3] if tables_with_iin else []

                for table in priority_tables[:5]:  # Проверим до 5 таблиц
                    print(f"\n{'='*80}")
                    print(f"📊 Таблица: {table}")
                    print('='*80)

                    try:
                        # Количество записей
                        result = connection.execute(text(f"SELECT COUNT(*) FROM `{table}`;"))
                        count = result.scalar()
                        print(f"Записей: {count}")

                        # Структура таблицы
                        result = connection.execute(text(f"DESCRIBE `{table}`;"))
                        columns = list(result)
                        print(f"\nКолонки ({len(columns)}):")
                        for col in columns[:20]:
                            print(f"   - {col[0]}: {col[1]} {col[2]} {col[3]}")

                        if len(columns) > 20:
                            print(f"   ... и еще {len(columns) - 20} колонок")

                        # Показать пример записи
                        if count > 0:
                            print(f"\nПример записи:")
                            result = connection.execute(text(f"SELECT * FROM `{table}` LIMIT 1;"))
                            row = result.fetchone()
                            if row:
                                col_names = result.keys()
                                for idx, col_name in enumerate(col_names[:15]):
                                    value = row[idx]
                                    # Обрезать длинные значения
                                    if isinstance(value, str) and len(value) > 50:
                                        value = value[:50] + "..."
                                    print(f"   {col_name}: {value}")

                    except Exception as e:
                        print(f"   ⚠️  Ошибка при чтении таблицы: {e}")

                # Тест 6: Поиск связей IIN
                if tables_with_iin:
                    print("\n" + "=" * 80)
                    print("🔗 АНАЛИЗ ПОЛЕЙ IIN")
                    print("=" * 80)

                    for table in tables_with_iin[:5]:
                        try:
                            # Получить статистику IIN
                            result = connection.execute(text(f"""
                                SELECT
                                    COUNT(*) as total,
                                    COUNT(DISTINCT iin) as unique_iin,
                                    SUM(CASE WHEN iin IS NULL OR iin = '' THEN 1 ELSE 0 END) as null_iin
                                FROM `{table}`
                                WHERE EXISTS (SELECT 1 FROM information_schema.columns
                                              WHERE table_schema = '{DB_NAME}'
                                              AND table_name = '{table}'
                                              AND column_name = 'iin');
                            """))
                            stats = result.fetchone()
                            if stats:
                                print(f"\n   {table}:")
                                print(f"      Всего записей: {stats[0]}")
                                print(f"      Уникальных IIN: {stats[1]}")
                                print(f"      Пустых IIN: {stats[2]}")
                        except:
                            pass

                print("\n" + "=" * 80)
                print("✅ ТЕСТИРОВАНИЕ ЗАВЕРШЕНО УСПЕШНО!")
                print("=" * 80)

    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        print(f"Тип ошибки: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        return False

    return True


def main():
    """Главная функция"""
    try:
        success = test_ssh_tunnel_sync()

        if success:
            print("\n✅ Все тесты пройдены успешно!")
            print("\n📝 Следующие шаги:")
            print("   1. Изучить структуру найденных таблиц")
            print("   2. Определить маппинг полей для интеграции")
            print("   3. Определить таблицы со студентами, преподавателями, сотрудниками")
            print("   4. Создать модели SQLAlchemy для MySQL")
            sys.exit(0)
        else:
            print("\n❌ Тесты провалились")
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n\n⚠️  Прервано пользователем")
        sys.exit(0)


if __name__ == "__main__":
    main()
