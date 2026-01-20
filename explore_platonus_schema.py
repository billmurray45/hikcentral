"""
Детальное исследование схемы Platonus для интеграции с HikCentral
Ищет таблицы с IIN и изучает структуру ключевых таблиц
"""

import sys
from sshtunnel import SSHTunnelForwarder
from sqlalchemy import create_engine, text

# SSH параметры
SSH_HOST = "77.245.103.155"
SSH_PORT = 7244
SSH_USER = "platonus_yu"
SSH_PASSWORD = "rCcSwNZe"

# MySQL параметры
DB_HOST = "localhost"
DB_PORT = 6080
DB_NAME = "nitro"
DB_USER = "platonsel"
DB_PASSWORD = "KJh6H823hd8"


def explore_database():
    """Исследовать структуру БД Platonus"""
    print("=" * 80)
    print("🔍 ДЕТАЛЬНОЕ ИССЛЕДОВАНИЕ PLATONUS")
    print("=" * 80)

    try:
        with SSHTunnelForwarder(
            (SSH_HOST, SSH_PORT),
            ssh_username=SSH_USER,
            ssh_password=SSH_PASSWORD,
            remote_bind_address=(DB_HOST, DB_PORT),
            local_bind_address=('127.0.0.1', 0)
        ) as tunnel:

            print(f"\n✅ SSH туннель создан (локальный порт: {tunnel.local_bind_port})")

            db_url = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@127.0.0.1:{tunnel.local_bind_port}/{DB_NAME}?charset=utf8mb4"
            engine = create_engine(db_url, echo=False)

            with engine.connect() as conn:
                print("✅ Подключено к MySQL\n")

                # ===== ШАГ 1: ПОИСК ВСЕХ ТАБЛИЦ С IIN/INN =====
                print("=" * 80)
                print("🔑 ПОИСК ТАБЛИЦ С ПОЛЕМ IIN/INN (ВСЕ 1104 ТАБЛИЦЫ)")
                print("=" * 80)

                result = conn.execute(text("SHOW TABLES;"))
                all_tables = [row[0] for row in result]
                print(f"Всего таблиц: {len(all_tables)}\n")

                tables_with_iin = []
                print("Поиск полей IIN/INN...")

                for idx, table in enumerate(all_tables, 1):
                    if idx % 100 == 0:
                        print(f"  Проверено {idx}/{len(all_tables)} таблиц...")

                    try:
                        # Поиск через information_schema (быстрее)
                        result = conn.execute(text(f"""
                            SELECT COLUMN_NAME, DATA_TYPE, COLUMN_TYPE, IS_NULLABLE
                            FROM information_schema.COLUMNS
                            WHERE TABLE_SCHEMA = '{DB_NAME}'
                            AND TABLE_NAME = '{table}'
                            AND LOWER(COLUMN_NAME) IN ('iin', 'inn')
                        """))

                        columns = list(result)
                        if columns:
                            tables_with_iin.append({
                                'table': table,
                                'columns': columns
                            })
                    except Exception as e:
                        pass

                print(f"\n✅ Найдено таблиц с IIN/INN: {len(tables_with_iin)}\n")

                for item in tables_with_iin:
                    print(f"📊 {item['table']}:")
                    for col in item['columns']:
                        print(f"   - {col[0]}: {col[2]} (NULL: {col[3]})")

                # ===== ШАГ 2: ИССЛЕДОВАНИЕ ТАБЛИЦЫ STUDENTS =====
                print("\n" + "=" * 80)
                print("📚 ТАБЛИЦА: students")
                print("=" * 80)

                # Структура
                result = conn.execute(text("DESCRIBE students;"))
                columns = list(result)
                print(f"\nКолонок: {len(columns)}\n")

                for col in columns:
                    print(f"   {col[0]:30} {col[1]:20} NULL:{col[2]:3} Key:{col[3]:3}")

                # Количество записей
                result = conn.execute(text("SELECT COUNT(*) FROM students;"))
                count = result.scalar()
                print(f"\n📊 Всего студентов: {count}")

                # Пример записи
                print("\n📄 Пример записи (первые 20 полей):")
                result = conn.execute(text("SELECT * FROM students LIMIT 1;"))
                row = result.fetchone()
                if row:
                    keys = list(result.keys())
                    for idx, key in enumerate(keys[:20]):
                        value = row[idx]
                        if isinstance(value, str) and len(value) > 60:
                            value = value[:60] + "..."
                        print(f"   {key:30} = {value}")

                # ===== ШАГ 3: ИССЛЕДОВАНИЕ ТАБЛИЦЫ USERS =====
                print("\n" + "=" * 80)
                print("👤 ТАБЛИЦА: users")
                print("=" * 80)

                result = conn.execute(text("DESCRIBE users;"))
                columns = list(result)
                print(f"\nКолонок: {len(columns)}\n")

                for col in columns:
                    print(f"   {col[0]:30} {col[1]:20} NULL:{col[2]:3} Key:{col[3]:3}")

                result = conn.execute(text("SELECT COUNT(*) FROM users;"))
                count = result.scalar()
                print(f"\n📊 Всего пользователей: {count}")

                # Пример записи
                print("\n📄 Пример записи:")
                result = conn.execute(text("SELECT * FROM users LIMIT 1;"))
                row = result.fetchone()
                if row:
                    keys = list(result.keys())
                    for idx, key in enumerate(keys):
                        value = row[idx]
                        if isinstance(value, str) and len(value) > 60:
                            value = value[:60] + "..."
                        print(f"   {key:30} = {value}")

                # ===== ШАГ 4: ПОИСК СВЯЗЕЙ МЕЖДУ ТАБЛИЦАМИ =====
                print("\n" + "=" * 80)
                print("🔗 АНАЛИЗ СВЯЗЕЙ")
                print("=" * 80)

                # Если нашли таблицы с IIN, проверим на наличие записей
                if tables_with_iin:
                    print("\n📊 Статистика по таблицам с IIN/INN:\n")

                    for item in tables_with_iin[:10]:  # Первые 10 таблиц
                        table = item['table']
                        col_name = item['columns'][0][0]  # Имя колонки IIN/INN

                        try:
                            result = conn.execute(text(f"""
                                SELECT
                                    COUNT(*) as total,
                                    COUNT(DISTINCT {col_name}) as unique_iin,
                                    SUM(CASE WHEN {col_name} IS NULL OR {col_name} = '' THEN 1 ELSE 0 END) as null_iin
                                FROM `{table}`;
                            """))
                            stats = result.fetchone()
                            if stats and stats[0] > 0:
                                print(f"   {table}:")
                                print(f"      Всего записей: {stats[0]}")
                                print(f"      Уникальных IIN: {stats[1]}")
                                print(f"      Пустых IIN: {stats[2]}")
                                print()
                        except Exception as e:
                            print(f"   {table}: ⚠️  {e}")

                # ===== ШАГ 5: ПРОВЕРКА ФАКУЛЬТЕТОВ/КАФЕДР =====
                print("\n" + "=" * 80)
                print("🏛️  ТАБЛИЦА: departments")
                print("=" * 80)

                try:
                    result = conn.execute(text("DESCRIBE departments;"))
                    columns = list(result)
                    print(f"\nКолонок: {len(columns)}\n")

                    for col in columns:
                        print(f"   {col[0]:30} {col[1]:20}")

                    result = conn.execute(text("SELECT COUNT(*) FROM departments;"))
                    count = result.scalar()
                    print(f"\n📊 Всего подразделений: {count}")

                    # Первые 10 подразделений
                    print("\n📋 Первые 10 подразделений:")
                    result = conn.execute(text("SELECT * FROM departments LIMIT 10;"))
                    rows = list(result)
                    keys = list(result.keys()) if rows else []

                    for row in rows:
                        print(f"\n   ID: {row[0]}")
                        for idx, key in enumerate(keys[1:6]):  # Первые 5 полей после ID
                            print(f"      {key}: {row[idx+1]}")
                except Exception as e:
                    print(f"⚠️  Ошибка: {e}")

                # ===== ШАГ 6: ПРОВЕРКА STUDYGROUPS =====
                print("\n" + "=" * 80)
                print("👥 ТАБЛИЦА: studygroups")
                print("=" * 80)

                try:
                    result = conn.execute(text("DESCRIBE studygroups;"))
                    columns = list(result)
                    print(f"\nКолонок: {len(columns)}\n")

                    for col in columns[:15]:
                        print(f"   {col[0]:30} {col[1]:20}")

                    result = conn.execute(text("SELECT COUNT(*) FROM studygroups;"))
                    count = result.scalar()
                    print(f"\n📊 Всего учебных групп: {count}")
                except Exception as e:
                    print(f"⚠️  Ошибка: {e}")

                print("\n" + "=" * 80)
                print("✅ ИССЛЕДОВАНИЕ ЗАВЕРШЕНО!")
                print("=" * 80)

    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True


if __name__ == "__main__":
    try:
        success = explore_database()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Прервано пользователем")
        sys.exit(0)
