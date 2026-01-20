"""
Расширенная диагностика подключения к Platonus
Пробует разные варианты подключения
"""

import socket
from sshtunnel import SSHTunnelForwarder
import paramiko
import psycopg2

# SSH параметры
SSH_HOST = "77.245.103.155"
SSH_PORT = 7244
SSH_USER = "platonus_yu"
SSH_PASSWORD = "rCcSwNZe"

# PostgreSQL параметры
DB_HOST = "localhost"
DB_PORT = 6080
DB_NAME = "nitro"
DB_USER = "platonsel"
DB_PASSWORD = "KJh6H823hd8"


def check_port_ssh(host, port):
    """Проверить через SSH что слушает порт"""
    print(f"\n{'='*80}")
    print(f"🔍 ПРОВЕРКА ПОРТА {port} ЧЕРЕЗ SSH")
    print('='*80)

    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(SSH_HOST, SSH_PORT, SSH_USER, SSH_PASSWORD, timeout=10)

        # Проверка что слушает порт
        commands = [
            f"netstat -tln | grep {port}",
            f"ss -tln | grep {port}",
            f"lsof -i :{port}",
            f"ps aux | grep postgres",
        ]

        for cmd in commands:
            print(f"\n📝 Команда: {cmd}")
            stdin, stdout, stderr = ssh.exec_command(cmd, timeout=5)
            output = stdout.read().decode('utf-8').strip()

            if output:
                print(f"   Результат:")
                for line in output.split('\n')[:5]:
                    print(f"      {line}")
            else:
                print(f"   Нет вывода")

        # Попробовать подключиться к БД напрямую на сервере
        print(f"\n📝 Попытка прямого подключения на сервере:")
        test_cmd = f"PGPASSWORD='{DB_PASSWORD}' psql -h {host} -p {port} -U {DB_USER} -d {DB_NAME} -c 'SELECT version();' 2>&1"
        print(f"   Команда: {test_cmd}")

        stdin, stdout, stderr = ssh.exec_command(test_cmd, timeout=10)
        output = stdout.read().decode('utf-8').strip()

        if "PostgreSQL" in output:
            print(f"   ✅ УСПЕШНО! PostgreSQL доступен:")
            print(f"      {output[:200]}")
            ssh.close()
            return True
        else:
            print(f"   ❌ Ошибка:")
            print(f"      {output[:500]}")

        ssh.close()

    except Exception as e:
        print(f"❌ Ошибка SSH: {e}")

    return False


def test_ssh_tunnel_raw():
    """Тест SSH туннеля с сырым подключением"""
    print(f"\n{'='*80}")
    print("🔌 ТЕСТ SSH ТУННЕЛЯ С ПРЯМЫМ ПОДКЛЮЧЕНИЕМ")
    print('='*80)

    try:
        print(f"\n📡 Создание SSH туннеля...")
        print(f"   SSH: {SSH_USER}@{SSH_HOST}:{SSH_PORT}")
        print(f"   Туннель: {DB_HOST}:{DB_PORT}")

        with SSHTunnelForwarder(
            (SSH_HOST, SSH_PORT),
            ssh_username=SSH_USER,
            ssh_password=SSH_PASSWORD,
            remote_bind_address=(DB_HOST, DB_PORT),
            local_bind_address=('127.0.0.1', 0)
        ) as tunnel:

            local_port = tunnel.local_bind_port
            print(f"✅ SSH туннель создан!")
            print(f"   Локальный порт: {local_port}")

            # Проверка подключения через сокет
            print(f"\n🔌 Проверка соединения через сокет...")
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                result = sock.connect_ex(('127.0.0.1', local_port))

                if result == 0:
                    print(f"   ✅ Порт {local_port} доступен")

                    # Попробовать отправить данные
                    print(f"\n📡 Попытка handshake...")
                    sock.send(b'\x00\x00\x00\x08\x04\xd2\x16\x2f')
                    response = sock.recv(1024)
                    print(f"   Ответ (первые 10 байт): {response[:10]}")

                else:
                    print(f"   ❌ Порт {local_port} недоступен (код: {result})")

                sock.close()

            except Exception as e:
                print(f"   ❌ Ошибка сокета: {e}")

            # Попробовать разные варианты подключения psycopg2
            print(f"\n{'='*80}")
            print("🔌 ПОПЫТКИ ПОДКЛЮЧЕНИЯ PSYCOPG2")
            print('='*80)

            connection_strings = [
                # Вариант 1: Без SSL
                {
                    'host': '127.0.0.1',
                    'port': local_port,
                    'dbname': DB_NAME,
                    'user': DB_USER,
                    'password': DB_PASSWORD,
                    'sslmode': 'disable',
                    'connect_timeout': 10
                },
                # Вариант 2: С SSL prefer
                {
                    'host': '127.0.0.1',
                    'port': local_port,
                    'dbname': DB_NAME,
                    'user': DB_USER,
                    'password': DB_PASSWORD,
                    'sslmode': 'prefer',
                    'connect_timeout': 10
                },
                # Вариант 3: Только имя хоста
                {
                    'host': '127.0.0.1',
                    'port': local_port,
                    'database': DB_NAME,
                    'user': DB_USER,
                    'password': DB_PASSWORD,
                    'connect_timeout': 10
                },
            ]

            for idx, conn_params in enumerate(connection_strings, 1):
                print(f"\n🔸 Вариант {idx}: {conn_params}")

                try:
                    conn = psycopg2.connect(**conn_params)
                    print(f"   ✅ ПОДКЛЮЧЕНИЕ УСПЕШНО!")

                    # Выполнить тестовый запрос
                    cursor = conn.cursor()
                    cursor.execute("SELECT version();")
                    version = cursor.fetchone()[0]
                    print(f"   📊 PostgreSQL версия:")
                    print(f"      {version}")

                    # Получить список таблиц
                    cursor.execute("""
                        SELECT schemaname, tablename
                        FROM pg_tables
                        WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
                        LIMIT 10;
                    """)
                    tables = cursor.fetchall()

                    print(f"\n   📋 Первые 10 таблиц:")
                    for schema, table in tables:
                        print(f"      - {schema}.{table}")

                    cursor.close()
                    conn.close()

                    print(f"\n{'='*80}")
                    print("✅ ПОДКЛЮЧЕНИЕ УСПЕШНО!")
                    print('='*80)
                    print(f"\n✅ Рабочие параметры подключения:")
                    for key, value in conn_params.items():
                        if key != 'password':
                            print(f"   {key}: {value}")

                    return True

                except psycopg2.OperationalError as e:
                    print(f"   ❌ OperationalError: {str(e)[:200]}")
                except psycopg2.Error as e:
                    print(f"   ❌ PostgreSQL Error: {str(e)[:200]}")
                except Exception as e:
                    print(f"   ❌ Unexpected Error: {type(e).__name__}: {str(e)[:200]}")

            print(f"\n{'='*80}")
            print("❌ ВСЕ ВАРИАНТЫ ПОДКЛЮЧЕНИЯ НЕ УДАЛИСЬ")
            print('='*80)

    except Exception as e:
        print(f"\n❌ Ошибка SSH туннеля: {e}")
        import traceback
        traceback.print_exc()

    return False


def main():
    """Главная функция"""
    print("=" * 80)
    print("🔍 РАСШИРЕННАЯ ДИАГНОСТИКА ПОДКЛЮЧЕНИЯ К PLATONUS")
    print("=" * 80)

    # Шаг 1: Проверка через SSH что слушает порт
    port_ok = check_port_ssh(DB_HOST, DB_PORT)

    # Шаг 2: Попытка подключения через туннель
    if port_ok or True:  # Всё равно пытаемся
        tunnel_ok = test_ssh_tunnel_raw()

        if tunnel_ok:
            print("\n✅ Диагностика завершена успешно!")
            print("\n📝 Следующие шаги:")
            print("   1. Используйте найденные параметры подключения")
            print("   2. Добавьте их в .env файл")
            print("   3. Создайте модели и начните интеграцию")
        else:
            print("\n❌ Не удалось установить подключение")
            print("\n💡 Возможные причины:")
            print("   1. PostgreSQL не слушает на указанном порту")
            print("   2. Неправильные креденшлы")
            print("   3. Настройки pg_hba.conf блокируют подключение")
            print("   4. Firewall блокирует соединение")
            print("\n📝 Рекомендации:")
            print("   1. Проверьте вывод команд выше")
            print("   2. Свяжитесь с администратором БД Platonus")
            print("   3. Проверьте pg_hba.conf на сервере")


if __name__ == "__main__":
    main()
