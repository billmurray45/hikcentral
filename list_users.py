"""
Показать список пользователей PostgreSQL и их права
"""

import asyncio
import asyncpg

async def list_users():
    """Показать пользователей и их права"""

    # Подключаемся с тем пользователем который есть
    conn = await asyncpg.connect(
        host='172.16.65.214',
        port=5432,
        user='hr_readonly',
        password='Bauka2745!',
        database='hikvision_sync'
    )

    try:
        print("=" * 80)
        print("👥 СПИСОК ПОЛЬЗОВАТЕЛЕЙ POSTGRESQL")
        print("=" * 80)

        # Получить список пользователей
        users = await conn.fetch("""
            SELECT
                usename as username,
                usesuper as is_superuser,
                usecreatedb as can_create_db,
                usecreaterole as can_create_role,
                useconnlimit as connection_limit
            FROM pg_user
            ORDER BY usename;
        """)

        if users:
            print(f"\nВсего пользователей: {len(users)}\n")
            for user in users:
                print(f"👤 {user['username']}")
                print(f"   Суперпользователь: {user['is_superuser']}")
                print(f"   Может создавать БД: {user['can_create_db']}")
                print(f"   Может создавать роли: {user['can_create_role']}")
                print(f"   Лимит подключений: {user['connection_limit']}")
                print()

        # Получить информацию о текущей БД и схемах
        print("=" * 80)
        print("📊 ИНФОРМАЦИЯ О БАЗЕ ДАННЫХ")
        print("=" * 80)

        current_db = await conn.fetchval("SELECT current_database();")
        current_user = await conn.fetchval("SELECT current_user;")

        print(f"\nТекущая БД: {current_db}")
        print(f"Текущий пользователь: {current_user}\n")

        # Проверить права на схему public
        print("=" * 80)
        print("🔐 ПРАВА НА СХЕМУ public")
        print("=" * 80)

        schema_privs = await conn.fetch("""
            SELECT
                grantee,
                privilege_type
            FROM information_schema.schema_privileges
            WHERE schema_name = 'public'
            ORDER BY grantee, privilege_type;
        """)

        if schema_privs:
            print("\nПрава пользователей на схему 'public':\n")
            current_grantee = None
            for priv in schema_privs:
                if priv['grantee'] != current_grantee:
                    if current_grantee is not None:
                        print()
                    print(f"👤 {priv['grantee']}:")
                    current_grantee = priv['grantee']
                print(f"   - {priv['privilege_type']}")

        # Владелец базы данных
        print("\n" + "=" * 80)
        print("👑 ВЛАДЕЛЕЦ БАЗЫ ДАННЫХ")
        print("=" * 80)

        owner = await conn.fetchval("""
            SELECT pg_catalog.pg_get_userbyid(d.datdba) as owner
            FROM pg_catalog.pg_database d
            WHERE d.datname = current_database();
        """)

        print(f"\nВладелец БД '{current_db}': {owner}")
        print(f"\n💡 Используйте пользователя '{owner}' для создания таблиц")

    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(list_users())
