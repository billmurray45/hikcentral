"""
Скрипт для получения списка всех факультетов из БД
Анализирует колонку person_group и извлекает уникальные факультеты
"""

import asyncio
from collections import defaultdict
from sqlalchemy import select, func, distinct
from app.core.database import async_session
from app.models import AttendanceRecord


def extract_faculty(person_group: str) -> str | None:
    """
    Извлечь факультет из person_group

    Args:
        person_group: Иерархическая строка группы

    Returns:
        Название факультета или None

    Example:
        "Студенты YU > Факультет Инжиниринг > ..." -> "Факультет Инжиниринг"
    """
    if not person_group:
        return None

    parts = person_group.split(" > ")
    for part in parts:
        if "Факультет" in part or "факультет" in part:
            return part.strip()

    return None


async def get_all_faculties():
    """
    Получить список всех факультетов с статистикой
    """
    print("=" * 80)
    print("📊 АНАЛИЗ ФАКУЛЬТЕТОВ ИЗ БАЗЫ ДАННЫХ")
    print("=" * 80)
    print()

    async with async_session() as session:
        # Получить все уникальные person_group значения с количеством записей
        query = (
            select(AttendanceRecord.person_group, func.count(AttendanceRecord.id))
            .where(AttendanceRecord.person_group.isnot(None))
            .group_by(AttendanceRecord.person_group)
            .order_by(func.count(AttendanceRecord.id).desc())
        )

        result = await session.execute(query)
        groups_data = result.all()

        print(f"✅ Найдено уникальных person_group: {len(groups_data)}")
        print()

        # Извлечь факультеты
        faculty_stats = defaultdict(int)
        faculty_groups = defaultdict(list)
        no_faculty_count = 0
        no_faculty_groups = []

        for person_group, count in groups_data:
            faculty = extract_faculty(person_group)

            if faculty:
                faculty_stats[faculty] += count
                faculty_groups[faculty].append((person_group, count))
            else:
                no_faculty_count += count
                no_faculty_groups.append((person_group, count))

        # Вывести статистику по факультетам
        print("=" * 80)
        print("📚 СПИСОК ФАКУЛЬТЕТОВ")
        print("=" * 80)
        print()

        if faculty_stats:
            # Сортировать по количеству записей
            sorted_faculties = sorted(
                faculty_stats.items(), key=lambda x: x[1], reverse=True
            )

            for idx, (faculty, total_count) in enumerate(sorted_faculties, 1):
                print(f"{idx}. {faculty}")
                print(f"   📊 Всего записей: {total_count:,}")

                # Показать примеры person_group для этого факультета
                groups = faculty_groups[faculty][:3]  # Первые 3 примера
                print(f"   📋 Примеры групп:")
                for group, count in groups:
                    # Сократить длинную строку
                    if len(group) > 70:
                        group_short = group[:67] + "..."
                    else:
                        group_short = group
                    print(f"      • {group_short} ({count:,} записей)")

                print()

            print("=" * 80)
            print(f"📊 ИТОГО: {len(faculty_stats)} факультетов")
            print(f"📊 Всего записей с факультетом: {sum(faculty_stats.values()):,}")
            print()

        else:
            print("⚠️  Факультетов не найдено")
            print()

        # Вывести записи без факультета
        if no_faculty_groups:
            print("=" * 80)
            print("⚠️  ЗАПИСИ БЕЗ ФАКУЛЬТЕТА")
            print("=" * 80)
            print()
            print(f"Всего записей без факультета: {no_faculty_count:,}")
            print(f"Уникальных групп: {len(no_faculty_groups)}")
            print()
            print("Примеры групп без факультета (топ-10):")

            for idx, (group, count) in enumerate(no_faculty_groups[:10], 1):
                if len(group) > 70:
                    group_short = group[:67] + "..."
                else:
                    group_short = group
                print(f"{idx}. {group_short}")
                print(f"   Записей: {count:,}")

            print()

        # Общая статистика
        print("=" * 80)
        print("📈 ОБЩАЯ СТАТИСТИКА")
        print("=" * 80)
        print()

        total_records_query = select(func.count(AttendanceRecord.id))
        total_result = await session.execute(total_records_query)
        total_records = total_result.scalar()

        print(f"Всего записей в БД: {total_records:,}")
        print(f"Записей с факультетом: {sum(faculty_stats.values()):,} ({sum(faculty_stats.values()) / total_records * 100:.1f}%)")
        print(f"Записей без факультета: {no_faculty_count:,} ({no_faculty_count / total_records * 100:.1f}%)")
        print()


async def get_faculty_details():
    """
    Получить детальную статистику по каждому факультету
    """
    print("=" * 80)
    print("📊 ДЕТАЛЬНАЯ СТАТИСТИКА ПО ФАКУЛЬТЕТАМ")
    print("=" * 80)
    print()

    async with async_session() as session:
        # Получить все записи и группировать по факультетам
        query = select(AttendanceRecord).where(
            AttendanceRecord.person_group.isnot(None)
        )

        result = await session.execute(query)
        records = result.scalars().all()

        print(f"Загружено записей для анализа: {len(records):,}")
        print()

        # Группировать по факультетам
        faculty_data = defaultdict(lambda: {
            'total': 0,
            'students': 0,
            'teachers': 0,
            'employees': 0,
            'other': 0
        })

        for record in records:
            faculty = record.faculty

            if faculty:
                faculty_data[faculty]['total'] += 1

                # Подсчет по типам
                person_type = record.person_type
                if 'student' in person_type or person_type in ['bachelor', 'master']:
                    faculty_data[faculty]['students'] += 1
                elif person_type == 'teacher':
                    faculty_data[faculty]['teachers'] += 1
                elif person_type == 'employee':
                    faculty_data[faculty]['employees'] += 1
                else:
                    faculty_data[faculty]['other'] += 1

        # Вывести детальную статистику
        sorted_faculties = sorted(
            faculty_data.items(), key=lambda x: x[1]['total'], reverse=True
        )

        for idx, (faculty, stats) in enumerate(sorted_faculties, 1):
            print(f"{idx}. {faculty}")
            print(f"   📊 Всего: {stats['total']:,}")
            print(f"   👨‍🎓 Студенты: {stats['students']:,} ({stats['students'] / stats['total'] * 100:.1f}%)")
            print(f"   👨‍🏫 Преподаватели: {stats['teachers']:,} ({stats['teachers'] / stats['total'] * 100:.1f}%)")
            print(f"   👔 Сотрудники: {stats['employees']:,} ({stats['employees'] / stats['total'] * 100:.1f}%)")
            print(f"   ❓ Прочие: {stats['other']:,} ({stats['other'] / stats['total'] * 100:.1f}%)")
            print()


async def main():
    """
    Главная функция
    """
    try:
        # Базовая статистика
        await get_all_faculties()

        # Спросить пользователя о детальной статистике
        print()
        print("=" * 80)
        choice = input("Показать детальную статистику по типам пользователей? (y/N): ")
        print()

        if choice.lower() == 'y':
            await get_faculty_details()

        print("=" * 80)
        print("✅ Анализ завершен!")
        print("=" * 80)

    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
