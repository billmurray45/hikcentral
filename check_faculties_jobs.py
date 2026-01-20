"""
Проверить факультеты и должности в Platonus
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


def check_faculties():
    """Проверить факультеты и должности"""
    print("=" * 80)
    print("🏛️  ПРОВЕРКА ФАКУЛЬТЕТОВ И ДОЛЖНОСТЕЙ")
    print("=" * 80)

    try:
        with SSHTunnelForwarder(
            (SSH_HOST, SSH_PORT),
            ssh_username=SSH_USER,
            ssh_password=SSH_PASSWORD,
            remote_bind_address=(DB_HOST, DB_PORT),
            local_bind_address=('127.0.0.1', 0)
        ) as tunnel:

            print(f"\n✅ SSH туннель создан\n")

            db_url = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@127.0.0.1:{tunnel.local_bind_port}/{DB_NAME}?charset=utf8mb4"
            engine = create_engine(db_url, echo=False)

            with engine.connect() as conn:
                # ===== ПОИСК ТАБЛИЦЫ FACULTIES =====
                print("=" * 80)
                print("📋 ПОИСК ТАБЛИЦЫ С ФАКУЛЬТЕТАМИ")
                print("=" * 80)

                result = conn.execute(text("SHOW TABLES LIKE '%facult%';"))
                faculty_tables = [row[0] for row in result]

                print(f"\nНайдены таблицы: {faculty_tables}\n")

                # Проверим каждую таблицу
                for table in faculty_tables:
                    print(f"\n📊 Таблица: {table}")

                    # Структура
                    result = conn.execute(text(f"DESCRIBE {table};"))
                    columns = list(result)
                    print(f"   Колонок: {len(columns)}")

                    # Количество записей
                    result = conn.execute(text(f"SELECT COUNT(*) FROM {table};"))
                    count = result.scalar()
                    print(f"   Записей: {count}")

                    # Показать структуру
                    print("   Поля:")
                    for col in columns[:10]:
                        print(f"      - {col[0]} ({col[1]})")

                    # Если это выглядит как основная таблица
                    if count > 0 and count < 100:
                        print(f"\n   📋 Содержимое:")
                        result = conn.execute(text(f"SELECT * FROM {table} LIMIT 10;"))
                        rows = list(result)
                        keys = list(result.keys()) if rows else []

                        for row in rows:
                            print(f"\n      ID: {row[0]}")
                            for idx, key in enumerate(keys[1:5]):  # Первые 4 поля после ID
                                if idx + 1 < len(row) and row[idx+1]:
                                    value = row[idx+1]
                                    if isinstance(value, str) and len(value) > 60:
                                        value = value[:60] + "..."
                                    print(f"      {key}: {value}")

                # ===== ПРОВЕРКА job_title_int =====
                print("\n" + "=" * 80)
                print("💼 ПРОВЕРКА ДОЛЖНОСТЕЙ (job_title_int)")
                print("=" * 80)

                # Статистика по job_title_int
                result = conn.execute(text("""
                    SELECT
                        job_title_int,
                        COUNT(*) as count
                    FROM tutors
                    WHERE job_title_int IS NOT NULL
                    GROUP BY job_title_int
                    ORDER BY count DESC;
                """))

                job_title_ints = list(result)
                print(f"\nУникальных значений job_title_int: {len(job_title_ints)}\n")

                for row in job_title_ints[:20]:
                    print(f"   ID {row[0]}: {row[1]} человек")

                # Поиск справочника должностей
                result = conn.execute(text("SHOW TABLES LIKE '%job%';"))
                job_tables = [row[0] for row in result]

                if job_tables:
                    print(f"\n📋 Найдены таблицы с job: {job_tables}")

                # Поиск таблиц с title, position, должность
                result = conn.execute(text("SHOW TABLES LIKE '%title%';"))
                title_tables = [row[0] for row in result]

                result = conn.execute(text("SHOW TABLES LIKE '%position%';"))
                position_tables = [row[0] for row in result]

                if title_tables:
                    print(f"\n📋 Таблицы с title: {title_tables}")

                if position_tables:
                    print(f"\n📋 Таблицы с position: {position_tables}")

                # Поискать словарь должностей
                result = conn.execute(text("SHOW TABLES LIKE '%dictionary%';"))
                dict_tables = [row[0] for row in result]

                result = conn.execute(text("SHOW TABLES LIKE '%dic_%';"))
                dic_tables = [row[0] for row in result]

                if dict_tables or dic_tables:
                    all_dicts = list(set(dict_tables + dic_tables))
                    print(f"\n📋 Таблицы-справочники: {all_dicts[:20]}")

                # ===== ПРОВЕРКА СВЯЗИ TUTORS -> CAFEDRAS -> FACULTIES =====
                print("\n" + "=" * 80)
                print("🔗 СВЯЗЬ: tutors → cafedras → faculties")
                print("=" * 80)

                # Если есть таблица faculties
                if 'faculties' in faculty_tables or any('facult' in t for t in faculty_tables):
                    faculty_table = 'faculties' if 'faculties' in faculty_tables else [t for t in faculty_tables if 'facult' in t][0]

                    print(f"\nИспользуем таблицу: {faculty_table}\n")

                    # Попробуем JOIN
                    try:
                        result = conn.execute(text(f"""
                            SELECT
                                t.TutorID,
                                t.iinplt,
                                t.firstname,
                                t.lastname,
                                t.patronymic,
                                c.cafedraNameRU as cafedra,
                                f.*
                            FROM tutors t
                            LEFT JOIN cafedras c ON t.CafedraID = c.cafedraID
                            LEFT JOIN {faculty_table} f ON c.FacultyID = f.FacultyID
                            WHERE t.iinplt IS NOT NULL AND t.iinplt != ''
                            AND c.cafedraID IS NOT NULL
                            LIMIT 10;
                        """))

                        linked = list(result)
                        if linked:
                            keys = list(result.keys())
                            print(f"✅ Связь найдена! Примеры:\n")

                            for idx, row in enumerate(linked[:5], 1):
                                print(f"{idx}. {row[2]} {row[3]}")
                                print(f"   IIN: {row[1]}")
                                print(f"   Кафедра: {row[5]}")
                                # Факультет - ищем поле с названием
                                for i, key in enumerate(keys[6:]):
                                    if 'name' in key.lower() and 'ru' in key.lower():
                                        print(f"   Факультет: {row[6+i]}")
                                        break
                                print()

                    except Exception as e:
                        print(f"⚠️  Ошибка JOIN: {e}")

                print("\n" + "=" * 80)
                print("✅ ПРОВЕРКА ЗАВЕРШЕНА")
                print("=" * 80)

    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True


if __name__ == "__main__":
    try:
        success = check_faculties()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Прервано пользователем")
        sys.exit(0)
