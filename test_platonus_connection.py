"""
Тест подключения к БД Platonus через SSH туннель
"""

import sys
from sshtunnel import SSHTunnelForwarder
from sqlalchemy import create_engine, text

# Данные для подключения из .env
PLATONUS_SSH_HOST = "77.245.103.155"
PLATONUS_SSH_PORT = 7244
PLATONUS_SSH_USER = "platonus_yu"
PLATONUS_SSH_PASSWORD = "rCcSwNZe"

PLATONUS_DB_HOST = "localhost"
PLATONUS_DB_PORT = 6080
PLATONUS_DB_NAME = "nitro"
PLATONUS_DB_USER = "platonsel"
PLATONUS_DB_PASSWORD = "KJh6H823hd8"

print("=" * 80)
print("ТЕСТ ПОДКЛЮЧЕНИЯ К PLATONUS")
print("=" * 80)

try:
    print(f"\n1. Попытка подключения к SSH серверу {PLATONUS_SSH_HOST}:{PLATONUS_SSH_PORT}...")

    with SSHTunnelForwarder(
        (PLATONUS_SSH_HOST, PLATONUS_SSH_PORT),
        ssh_username=PLATONUS_SSH_USER,
        ssh_password=PLATONUS_SSH_PASSWORD,
        remote_bind_address=(PLATONUS_DB_HOST, PLATONUS_DB_PORT),
        local_bind_address=("127.0.0.1", 0),
    ) as tunnel:

        print(f"✅ SSH туннель успешно установлен!")
        print(f"   Локальный порт: {tunnel.local_bind_port}")

        print(f"\n2. Попытка подключения к MySQL БД {PLATONUS_DB_NAME}...")

        # Подключение к MySQL через туннель
        db_url = f"mysql+pymysql://{PLATONUS_DB_USER}:{PLATONUS_DB_PASSWORD}@127.0.0.1:{tunnel.local_bind_port}/{PLATONUS_DB_NAME}?charset=utf8mb4"
        engine = create_engine(db_url, echo=False)

        with engine.connect() as conn:
            print(f"✅ Подключение к БД успешно!")

            print(f"\n3. Выполнение тестового запроса...")

            # Проверить количество преподавателей
            result = conn.execute(text("SELECT COUNT(*) as count FROM tutors"))
            row = result.fetchone()
            tutors_count = row[0]

            print(f"✅ Запрос выполнен успешно!")
            print(f"   Всего записей в таблице tutors: {tutors_count}")

            # Проверить количество с IIN
            result = conn.execute(text("SELECT COUNT(*) as count FROM tutors WHERE iinplt IS NOT NULL AND iinplt != ''"))
            row = result.fetchone()
            with_iin = row[0]

            print(f"   Записей с IIN: {with_iin}")

            # Получить пример записи
            result = conn.execute(text("""
                SELECT t.TutorID, t.iinplt, t.firstname, t.lastname
                FROM tutors t
                WHERE t.iinplt IS NOT NULL AND t.iinplt != ''
                LIMIT 1
            """))
            row = result.fetchone()

            if row:
                print(f"\n   Пример записи:")
                print(f"   - TutorID: {row[0]}")
                print(f"   - IIN: {row[1]}")
                print(f"   - Имя: {row[2]} {row[3]}")

            print("\n" + "=" * 80)
            print("✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!")
            print("=" * 80)

except Exception as e:
    print("\n" + "=" * 80)
    print(f"❌ ОШИБКА: {e}")
    print("=" * 80)
    import traceback
    traceback.print_exc()
    sys.exit(1)
