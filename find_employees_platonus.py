"""
Поиск и анализ таблиц с сотрудниками в Platonus
Ищем преподавателей, учителей, сотрудников
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


def explore_employees():
    """Исследовать таблицы с сотрудниками"""
    print("=" * 80)
    print("🔍 ПОИСК СОТРУДНИКОВ В PLATONUS")
    print("=" * 80)

    try:
        with SSHTunnelForwarder(
            (SSH_HOST, SSH_PORT),
            ssh_username=SSH_USER,
            ssh_password=SSH_PASSWORD,
            remote_bind_address=(DB_HOST, DB_PORT),
            local_bind_address=('127.0.0.1', 0)
        ) as tunnel:

            print(f"\n✅ SSH туннель создан (порт: {tunnel.local_bind_port})\n")

            db_url = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@127.0.0.1:{tunnel.local_bind_port}/{DB_NAME}?charset=utf8mb4"
            engine = create_engine(db_url, echo=False)

            with engine.connect() as conn:
                # ===== ШАГ 1: НАЙТИ ТАБЛИЦЫ С СОТРУДНИКАМИ =====
                print("=" * 80)
                print("📋 ПОИСК ТАБЛИЦ")
                print("=" * 80)

                result = conn.execute(text("SHOW TABLES;"))
                all_tables = [row[0] for row in result]

                # Ключевые слова для поиска
                keywords = ['tutor', 'teacher', 'employee', 'staff', 'personnel',
                           'преподаватель', 'учитель', 'сотрудник']

                employee_tables = {}
                for keyword in keywords:
                    matching = [t for t in all_tables if keyword.lower() in t.lower()]
                    if matching:
                        employee_tables[keyword] = matching

                print("\nНайденные таблицы по ключевым словам:\n")
                for keyword, tables in employee_tables.items():
                    if tables:
                        print(f"📁 '{keyword}' ({len(tables)} таблиц):")
                        for table in tables[:10]:  # Первые 10
                            print(f"   - {table}")
                        if len(tables) > 10:
                            print(f"   ... и еще {len(tables) - 10}")
                        print()

                # ===== ШАГ 2: ПРОВЕРКА ТАБЛИЦЫ TUTORS =====
                if 'tutors' in all_tables:
                    print("=" * 80)
                    print("👨‍🏫 ТАБЛИЦА: tutors")
                    print("=" * 80)

                    # Структура
                    result = conn.execute(text("DESCRIBE tutors;"))
                    columns = list(result)
                    print(f"\nКолонок: {len(columns)}\n")

                    for col in columns:
                        print(f"   {col[0]:30} {col[1]:20} NULL:{col[2]:3} Key:{col[3]:3}")

                    # Количество
                    result = conn.execute(text("SELECT COUNT(*) FROM tutors;"))
                    count = result.scalar()
                    print(f"\n📊 Всего записей: {count}")

                    # Проверка есть ли IIN
                    iin_fields = [col[0] for col in columns if 'iin' in col[0].lower() or 'inn' in col[0].lower()]
                    if iin_fields:
                        print(f"\n✅ Найдены поля IIN: {iin_fields}")
                    else:
                        print("\n⚠️  Поле IIN не найдено в таблице tutors")
                        print("   Возможные поля для связи:")
                        for col in columns[:15]:
                            print(f"   - {col[0]}")

                    # Пример записи
                    print("\n📄 Пример записи (первые 15 полей):")
                    result = conn.execute(text("SELECT * FROM tutors LIMIT 1;"))
                    row = result.fetchone()
                    if row:
                        keys = list(result.keys())
                        for idx, key in enumerate(keys[:15]):
                            value = row[idx]
                            if isinstance(value, str) and len(value) > 50:
                                value = value[:50] + "..."
                            print(f"   {key:30} = {value}")

                # ===== ШАГ 3: ПРОВЕРКА СВЯЗИ TUTORS С USERS =====
                if 'tutors' in all_tables:
                    print("\n" + "=" * 80)
                    print("🔗 СВЯЗЬ tutors → users")
                    print("=" * 80)

                    # Проверим есть ли в tutors поле связи с users
                    result = conn.execute(text("DESCRIBE tutors;"))
                    tutor_columns = {col[0]: col[1] for col in result}

                    # Ищем ID поля
                    id_fields = [col for col in tutor_columns.keys() if 'id' in col.lower()]
                    print(f"\nПоля с ID в tutors: {id_fields}\n")

                    # Попробуем JOIN с users по возможным полям
                    if 'TutorID' in tutor_columns or 'tutorid' in tutor_columns:
                        tutor_id_field = 'TutorID' if 'TutorID' in tutor_columns else 'tutorid'

                        print(f"Пробуем связать tutors.{tutor_id_field} с users...\n")

                        # Проверка через users.id или другое поле
                        result = conn.execute(text("""
                            SELECT
                                t.*,
                                u.iin,
                                u.firstname,
                                u.lastname
                            FROM tutors t
                            LEFT JOIN users u ON t.TutorID = u.id
                            WHERE u.iin IS NOT NULL
                            LIMIT 5;
                        """))

                        rows = list(result)
                        if rows:
                            print(f"✅ Найдено связей tutors → users: {len(rows)}\n")
                            print("Примеры:")
                            keys = list(result.keys())
                            for row in rows:
                                print(f"\n   Tutor: {row[1] if len(row) > 1 else 'N/A'}")
                                # Найдем IIN
                                iin_idx = keys.index('iin') if 'iin' in keys else None
                                if iin_idx:
                                    print(f"   IIN: {row[iin_idx]}")
                                # ФИО
                                fn_idx = keys.index('firstname') if 'firstname' in keys else None
                                ln_idx = keys.index('lastname') if 'lastname' in keys else None
                                if fn_idx and ln_idx:
                                    print(f"   ФИО: {row[fn_idx]} {row[ln_idx]}")
                        else:
                            print("⚠️  Связь не найдена, пробуем другие варианты...")

                # ===== ШАГ 4: ИССЛЕДОВАНИЕ USERS =====
                print("\n" + "=" * 80)
                print("👤 АНАЛИЗ ТАБЛИЦЫ users")
                print("=" * 80)

                # Найти все уникальные типы в users (если есть поле type/role)
                result = conn.execute(text("DESCRIBE users;"))
                user_columns = [col[0] for col in result]

                print(f"\nВсего колонок в users: {len(user_columns)}\n")
                print("Поля users (первые 30):")
                for col in user_columns[:30]:
                    print(f"   - {col}")

                # Поиск полей связанных с типом/ролью
                type_fields = [col for col in user_columns if any(word in col.lower()
                              for word in ['type', 'role', 'kind', 'category', 'тип'])]

                if type_fields:
                    print(f"\n✅ Найдены поля типа/роли: {type_fields}")

                    # Проверим уникальные значения
                    for field in type_fields[:3]:  # Первые 3 поля
                        print(f"\n📊 Уникальные значения {field}:")
                        result = conn.execute(text(f"""
                            SELECT {field}, COUNT(*) as count
                            FROM users
                            WHERE {field} IS NOT NULL
                            GROUP BY {field}
                            ORDER BY count DESC
                            LIMIT 10;
                        """))
                        for row in result:
                            print(f"   {row[0]}: {row[1]} записей")

                # ===== ШАГ 5: ПОИСК СОТРУДНИКОВ С IIN =====
                print("\n" + "=" * 80)
                print("🎯 ПОЛЬЗОВАТЕЛИ С IIN (не студенты)")
                print("=" * 80)

                # Получить users с IIN, которые НЕ студенты
                result = conn.execute(text("""
                    SELECT
                        u.id,
                        u.iin,
                        u.firstname,
                        u.lastname,
                        u.patronymic
                    FROM users u
                    WHERE u.iin IS NOT NULL
                    AND u.iin != ''
                    AND u.id NOT IN (
                        SELECT DISTINCT StudentID FROM students WHERE iinplt IS NOT NULL
                    )
                    LIMIT 20;
                """))

                non_student_users = list(result)
                print(f"\nНайдено пользователей с IIN (не студенты): {len(non_student_users)}\n")

                if non_student_users:
                    print("Примеры (первые 10):")
                    for idx, row in enumerate(non_student_users[:10], 1):
                        print(f"\n   {idx}. ID: {row[0]}")
                        print(f"      IIN: {row[1]}")
                        print(f"      ФИО: {row[2]} {row[3]} {row[4] if row[4] else ''}")

                # Общая статистика
                result = conn.execute(text("""
                    SELECT COUNT(*) FROM users
                    WHERE iin IS NOT NULL AND iin != ''
                    AND id NOT IN (SELECT DISTINCT StudentID FROM students WHERE iinplt IS NOT NULL);
                """))
                total_non_students = result.scalar()
                print(f"\n📊 Всего пользователей с IIN (не студенты): {total_non_students}")

                # ===== ШАГ 6: ПРОВЕРКА EMPLOYEE TABLES =====
                print("\n" + "=" * 80)
                print("💼 ПРОВЕРКА ТАБЛИЦ EMPLOYEE")
                print("=" * 80)

                # Проверим основные таблицы employee
                employee_main_tables = [t for t in all_tables if t.startswith('employee') and not t.endswith('_')]

                for table in employee_main_tables[:5]:
                    print(f"\n📋 Таблица: {table}")

                    try:
                        # Структура
                        result = conn.execute(text(f"DESCRIBE {table};"))
                        columns = list(result)

                        # Количество
                        result = conn.execute(text(f"SELECT COUNT(*) FROM {table};"))
                        count = result.scalar()

                        print(f"   Колонок: {len(columns)}, Записей: {count}")

                        # Проверка IIN
                        iin_cols = [col[0] for col in columns if 'iin' in col[0].lower()]
                        if iin_cols:
                            print(f"   ✅ Есть IIN: {iin_cols}")

                        # Показать ключевые поля
                        print("   Поля:")
                        for col in columns[:10]:
                            print(f"      - {col[0]} ({col[1]})")

                    except Exception as e:
                        print(f"   ⚠️  Ошибка: {e}")

                print("\n" + "=" * 80)
                print("✅ АНАЛИЗ ЗАВЕРШЕН")
                print("=" * 80)

    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True


if __name__ == "__main__":
    try:
        success = explore_employees()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Прервано пользователем")
        sys.exit(0)
