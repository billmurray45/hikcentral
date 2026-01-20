"""
Получить всех преподавателей/сотрудников из Platonus
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


def get_tutors_info():
    """Получить информацию о преподавателях"""
    print("=" * 80)
    print("👨‍🏫 ПОЛУЧЕНИЕ ДАННЫХ ПРЕПОДАВАТЕЛЕЙ/СОТРУДНИКОВ")
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
                # ===== СТАТИСТИКА =====
                print("=" * 80)
                print("📊 СТАТИСТИКА")
                print("=" * 80)

                # Всего tutors
                result = conn.execute(text("SELECT COUNT(*) FROM tutors;"))
                total = result.scalar()
                print(f"\nВсего записей в tutors: {total}")

                # С IIN
                result = conn.execute(text("""
                    SELECT COUNT(*) FROM tutors
                    WHERE iinplt IS NOT NULL AND iinplt != '';
                """))
                with_iin = result.scalar()
                print(f"С заполненным IIN: {with_iin}")
                print(f"Без IIN: {total - with_iin}")

                # ===== ТИПЫ СОТРУДНИКОВ =====
                print("\n" + "=" * 80)
                print("📋 ТИПЫ СОТРУДНИКОВ (employee_type)")
                print("=" * 80)

                result = conn.execute(text("""
                    SELECT
                        employee_type,
                        COUNT(*) as count
                    FROM tutors
                    WHERE employee_type IS NOT NULL
                    GROUP BY employee_type
                    ORDER BY count DESC;
                """))

                employee_types = list(result)
                print(f"\nНайдено типов: {len(employee_types)}\n")

                for row in employee_types:
                    print(f"   Тип {row[0]}: {row[1]} человек")

                # ===== ДОЛЖНОСТИ =====
                print("\n" + "=" * 80)
                print("💼 ДОЛЖНОСТИ (job_title)")
                print("=" * 80)

                result = conn.execute(text("""
                    SELECT
                        job_title,
                        COUNT(*) as count
                    FROM tutors
                    WHERE job_title IS NOT NULL AND job_title != ''
                    GROUP BY job_title
                    ORDER BY count DESC
                    LIMIT 20;
                """))

                job_titles = list(result)
                print(f"\nТоп-20 должностей:\n")

                for idx, row in enumerate(job_titles, 1):
                    print(f"   {idx}. {row[0]}: {row[1]} человек")

                # ===== КАФЕДРЫ =====
                print("\n" + "=" * 80)
                print("🏛️  КАФЕДРЫ (CafedraID)")
                print("=" * 80)

                result = conn.execute(text("""
                    SELECT
                        CafedraID,
                        COUNT(*) as count
                    FROM tutors
                    WHERE CafedraID IS NOT NULL
                    GROUP BY CafedraID
                    ORDER BY count DESC
                    LIMIT 15;
                """))

                cafedras = list(result)
                print(f"\nТоп-15 кафедр (по ID):\n")

                for row in cafedras:
                    print(f"   Кафедра ID {row[0]}: {row[1]} человек")

                # Проверим есть ли таблица cafedras
                result = conn.execute(text("SHOW TABLES LIKE '%cafedra%';"))
                cafedra_tables = [row[0] for row in result]

                if cafedra_tables:
                    print(f"\n📋 Найдены таблицы с кафедрами: {cafedra_tables}")

                    # Попробуем получить названия кафедр
                    if 'cafedras' in cafedra_tables:
                        print("\n" + "=" * 80)
                        print("📚 ТАБЛИЦА cafedras")
                        print("=" * 80)

                        # Структура
                        result = conn.execute(text("DESCRIBE cafedras;"))
                        columns = list(result)
                        print(f"\nКолонок: {len(columns)}\n")
                        for col in columns[:15]:
                            print(f"   {col[0]:30} {col[1]:20}")

                        # Первые 10 кафедр
                        result = conn.execute(text("SELECT * FROM cafedras LIMIT 10;"))
                        rows = list(result)
                        keys = list(result.keys()) if rows else []

                        print(f"\n📋 Первые 10 кафедр:\n")
                        for row in rows:
                            print(f"\n   ID: {row[0]}")
                            for idx, key in enumerate(keys[1:4]):  # Первые поля
                                if row[idx+1]:
                                    print(f"   {key}: {row[idx+1]}")

                # ===== ПРИМЕРЫ СОТРУДНИКОВ С IIN =====
                print("\n" + "=" * 80)
                print("👤 ПРИМЕРЫ СОТРУДНИКОВ С IIN")
                print("=" * 80)

                result = conn.execute(text("""
                    SELECT
                        TutorID,
                        iinplt,
                        firstname,
                        lastname,
                        patronymic,
                        job_title,
                        employee_type,
                        CafedraID,
                        mail,
                        mobilePhone
                    FROM tutors
                    WHERE iinplt IS NOT NULL AND iinplt != ''
                    LIMIT 10;
                """))

                tutors = list(result)
                print(f"\nПервые 10 сотрудников:\n")

                for idx, row in enumerate(tutors, 1):
                    print(f"\n{idx}. ID: {row[0]}")
                    print(f"   IIN: {row[1]}")
                    print(f"   ФИО: {row[2]} {row[3]} {row[4] if row[4] else ''}")
                    print(f"   Должность: {row[5] if row[5] else 'не указана'}")
                    print(f"   Тип: {row[6] if row[6] else 'не указан'}")
                    print(f"   Кафедра ID: {row[7] if row[7] else 'не указана'}")
                    print(f"   Email: {row[8] if row[8] else 'нет'}")
                    print(f"   Телефон: {row[9] if row[9] else 'нет'}")

                # ===== EXPORT ALL TUTORS =====
                print("\n" + "=" * 80)
                print("💾 СОХРАНЕНИЕ ВСЕХ СОТРУДНИКОВ")
                print("=" * 80)

                result = conn.execute(text("""
                    SELECT
                        TutorID,
                        iinplt,
                        firstname,
                        lastname,
                        patronymic,
                        job_title,
                        employee_type,
                        CafedraID,
                        mail,
                        mobilePhone,
                        departmentid
                    FROM tutors
                    WHERE iinplt IS NOT NULL AND iinplt != ''
                    ORDER BY TutorID;
                """))

                all_tutors = list(result)

                # Сохранить в файл
                with open('platonus_tutors_all.txt', 'w', encoding='utf-8') as f:
                    f.write("=" * 100 + "\n")
                    f.write(f"СПИСОК ВСЕХ СОТРУДНИКОВ PLATONUS (с IIN)\n")
                    f.write(f"Всего: {len(all_tutors)}\n")
                    f.write("=" * 100 + "\n\n")

                    for tutor in all_tutors:
                        f.write(f"ID: {tutor[0]}\n")
                        f.write(f"IIN: {tutor[1]}\n")
                        f.write(f"ФИО: {tutor[2]} {tutor[3]} {tutor[4] if tutor[4] else ''}\n")
                        f.write(f"Должность: {tutor[5] if tutor[5] else 'не указана'}\n")
                        f.write(f"Тип сотрудника: {tutor[6] if tutor[6] else 'не указан'}\n")
                        f.write(f"Кафедра ID: {tutor[7] if tutor[7] else 'не указана'}\n")
                        f.write(f"Email: {tutor[8] if tutor[8] else 'нет'}\n")
                        f.write(f"Телефон: {tutor[9] if tutor[9] else 'нет'}\n")
                        f.write(f"Департамент ID: {tutor[10] if tutor[10] else 'не указан'}\n")
                        f.write("-" * 100 + "\n\n")

                print(f"\n✅ Сохранено {len(all_tutors)} сотрудников в файл: platonus_tutors_all.txt")

                # ===== СТАТИСТИКА ПО ТИПАМ EMPLOYEE =====
                print("\n" + "=" * 80)
                print("📈 ДЕТАЛЬНАЯ СТАТИСТИКА ПО ТИПАМ")
                print("=" * 80)

                # Проверим есть ли таблица employee_types
                result = conn.execute(text("SHOW TABLES LIKE 'employee_types';"))
                if result.fetchone():
                    print("\n✅ Найдена таблица employee_types\n")

                    result = conn.execute(text("DESCRIBE employee_types;"))
                    columns = list(result)
                    print("Структура:")
                    for col in columns:
                        print(f"   {col[0]:30} {col[1]:20}")

                    result = conn.execute(text("SELECT * FROM employee_types;"))
                    types = list(result)

                    if types:
                        print(f"\n📋 Типы сотрудников (из справочника):\n")
                        keys = list(result.keys())
                        for row in types:
                            print(f"\n   ID: {row[0]}")
                            for idx, key in enumerate(keys[1:4]):
                                if idx + 1 < len(row) and row[idx+1]:
                                    print(f"   {key}: {row[idx+1]}")

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
        success = get_tutors_info()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Прервано пользователем")
        sys.exit(0)
