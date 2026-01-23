"""
Employees API endpoints - получение списка сотрудников кто проходит турникет
Данные берутся из кеша platonus_employees (синхронизация раз в неделю)
"""

from typing import Optional
from fastapi import APIRouter, Query, Depends, HTTPException
from sqlalchemy import select, func, or_, text
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date, datetime, time, timedelta
from collections import defaultdict

from app.schemas import (
    EmployeeBase,
    EmployeeListResponse,
    EmployeeAttendanceSummary,
    EmployeeAttendanceListResponse,
    EmployeeAttendanceRecord,
    LateEmployeeSummary,
    LateEmployeesResponse,
    PlatonusFaculty,
    PlatonusFacultyListResponse,
    PlatonusSubdivision,
    PlatonusSubdivisionListResponse,
    TopLateEmployee,
    DivisionLateStats,
    DailyLateStats,
    LateTimeDistribution,
    LateStatisticsResponse,
)
from app.models import PlatonusEmployee, AttendanceRecord
from app.api.dependencies import get_db
from app.services.platonus_sync import PlatonusSyncService

router = APIRouter(prefix="/employees", tags=["Employees"])


@router.get(
    "",
    response_model=EmployeeListResponse,
    summary="Получить список сотрудников",
    description="""
    Получить список сотрудников которые проходят турникет.

    **Источник данных:**
    - Список IIN из HikCentral (attendance_records, person_type != 'student')
    - Данные обогащены из Platonus (должность, кафедра, факультет)
    - Данные кешируются в таблице platonus_employees
    - Синхронизация: раз в неделю

    **Фильтры:**
    - `position_type`: Фильтр по типу должности (Преподаватель/Руководитель/Специалист/и т.д.)
    - `faculty_id`: Фильтр по ID факультета (для преподавателей)
    - `subdivision_id`: Фильтр по ID подразделения (для административного персонала)
    - `search`: Поиск по ФИО или IIN

    **Пагинация:**
    - `page`: Номер страницы (default: 1, min: 1)
    - `page_size`: Размер страницы (default: 20, min: 10, max: 100)

    **Сортировка:**
    - `sort_by`: Поле для сортировки (lastname, firstname, position_type)
    - `sort_order`: Порядок сортировки (asc, desc)

    **Включает:**
    - ИИН
    - ФИО
    - Должность и тип должности
    - Кафедра и факультет (для преподавателей)
    - Структурное подразделение (для административного персонала)
    - Контакты (email, телефон)
    """,
)
async def get_employees(
    position_type: Optional[str] = Query(None, description="Тип должности"),
    faculty_id: Optional[int] = Query(None, description="ID факультета"),
    subdivision_id: Optional[int] = Query(None, description="ID подразделения"),
    search: Optional[str] = Query(None, description="Поиск по ФИО или IIN"),
    page: int = Query(1, ge=1, description="Номер страницы"),
    page_size: int = Query(20, ge=10, le=100, description="Размер страницы"),
    sort_by: str = Query("lastname", description="Поле для сортировки (lastname, firstname, position_type)"),
    sort_order: str = Query("asc", description="Порядок: asc или desc"),
    db: AsyncSession = Depends(get_db),
):
    """
    Получить список сотрудников из кеша
    """

    # Построить базовый запрос для подсчета
    count_query = select(func.count()).select_from(PlatonusEmployee)

    # Построить запрос для данных
    query = select(PlatonusEmployee)

    # Фильтры
    if position_type:
        query = query.where(PlatonusEmployee.position_type == position_type)
        count_query = count_query.where(PlatonusEmployee.position_type == position_type)

    if faculty_id is not None:
        query = query.where(PlatonusEmployee.faculty_id == faculty_id)
        count_query = count_query.where(PlatonusEmployee.faculty_id == faculty_id)

    if subdivision_id is not None:
        query = query.where(PlatonusEmployee.subdivision_id == subdivision_id)
        count_query = count_query.where(PlatonusEmployee.subdivision_id == subdivision_id)

    if search:
        search_pattern = f"%{search}%"
        search_filter = or_(
            PlatonusEmployee.firstname.ilike(search_pattern),
            PlatonusEmployee.lastname.ilike(search_pattern),
            PlatonusEmployee.patronymic.ilike(search_pattern),
            PlatonusEmployee.iin.ilike(search_pattern),
        )
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)

    # Подсчитать общее количество
    total_count = await db.scalar(count_query)
    total_count = total_count or 0

    # Сортировка
    sort_column = PlatonusEmployee.lastname
    if sort_by == "firstname":
        sort_column = PlatonusEmployee.firstname
    elif sort_by == "position_type":
        sort_column = PlatonusEmployee.position_type

    if sort_order.lower() == "desc":
        query = query.order_by(sort_column.desc(), PlatonusEmployee.lastname, PlatonusEmployee.firstname)
    else:
        query = query.order_by(sort_column, PlatonusEmployee.lastname, PlatonusEmployee.firstname)

    # Пагинация
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    # Выполнить запрос
    result = await db.execute(query)
    employees_db = result.scalars().all()

    # Преобразовать в схемы
    employees = [
        EmployeeBase(
            tutor_id=emp.tutor_id,
            iin=emp.iin,
            firstname=emp.firstname,
            lastname=emp.lastname,
            patronymic=emp.patronymic,
            position=emp.position,
            position_type=emp.position_type,
            cafedra=emp.cafedra_name,
            faculty=emp.faculty_name,
            faculty_id=emp.faculty_id,
            subdivision=emp.subdivision_name,
            subdivision_id=emp.subdivision_id,
            email=emp.email,
            phone=emp.phone,
        )
        for emp in employees_db
    ]

    # Вычислить количество страниц
    total_pages = (total_count + page_size - 1) // page_size

    return EmployeeListResponse(
        total=total_count,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        items=employees,
    )


@router.post(
    "/sync",
    summary="Синхронизировать данные сотрудников",
    description="""
    Запустить синхронизацию данных сотрудников из Platonus.

    **Процесс:**
    1. Получить всех уникальных пользователей с IIN из HikCentral (не студентов)
    2. Для каждого IIN получить данные из Platonus (должность, кафедра, факультет)
    3. Сохранить/обновить в таблице platonus_employees

    **Примечание:** Обычно запускается автоматически раз в неделю
    """,
)
async def sync_employees(db: AsyncSession = Depends(get_db)):
    """
    Синхронизировать данные сотрудников из Platonus
    """
    service = PlatonusSyncService(db)
    result = await service.sync_employees()
    return result


@router.get(
    "/sync/stats",
    summary="Статистика синхронизации",
    description="""
    Получить статистику последней синхронизации.

    **Включает:**
    - Всего сотрудников в кеше
    - Дата последней синхронизации
    - Распределение по типам должностей
    - Распределение по факультетам
    """,
)
async def get_sync_stats(db: AsyncSession = Depends(get_db)):
    """
    Получить статистику синхронизации
    """
    service = PlatonusSyncService(db)
    stats = await service.get_sync_stats()
    return stats


@router.get(
    "/attendance",
    response_model=EmployeeAttendanceListResponse,
    summary="Посещаемость сотрудников за день",
    description="""
    Получить данные о посещаемости сотрудников за определенный день.

    **Источник данных:**
    - История проходов из attendance_records (турникеты)
    - Данные сотрудников из platonus_employees (должность, факультет, подразделение)

    **Фильтры:**
    - `date`: Дата (YYYY-MM-DD), по умолчанию сегодня
    - `faculty_id`: ID факультета (для преподавателей)
    - `subdivision_id`: ID подразделения (для административного персонала)
    - `position_type`: Тип должности (Преподаватель/Административный персонал/и т.д.)
    - `search`: Поиск по ФИО или IIN

    **Пагинация:**
    - `page`: Номер страницы (default: 1, min: 1)
    - `page_size`: Размер страницы (default: 20, min: 10, max: 100)

    **Возвращает:**
    - Список сотрудников с их проходами за день
    - Первый вход и последний выход
    - Все проходы с временем и направлением
    """,
)
async def get_employees_attendance(
    date_param: Optional[str] = Query(None, alias="date", description="Дата (YYYY-MM-DD)"),
    faculty_id: Optional[int] = Query(None, description="ID факультета"),
    subdivision_id: Optional[int] = Query(None, description="ID подразделения"),
    position_type: Optional[str] = Query(None, description="Тип должности"),
    search: Optional[str] = Query(None, description="Поиск по ФИО или IIN"),
    page: int = Query(1, ge=1, description="Номер страницы"),
    page_size: int = Query(20, ge=10, le=100, description="Размер страницы"),
    db: AsyncSession = Depends(get_db),
):
    """
    Получить посещаемость сотрудников за день
    """

    # Определить дату
    if date_param:
        try:
            target_date = datetime.strptime(date_param, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Неверный формат даты. Используйте YYYY-MM-DD")
    else:
        target_date = date.today()

    date_str = target_date.strftime("%Y-%m-%d")

    # Шаг 1: Получить уникальные IIN'ы сотрудников с проходами в этот день
    iin_query = select(AttendanceRecord.iin).where(
        AttendanceRecord.access_date == date_str
    ).distinct()

    iin_result = await db.execute(iin_query)
    iins_with_attendance = [row[0] for row in iin_result.all()]

    if not iins_with_attendance:
        return EmployeeAttendanceListResponse(
            date=date_str,
            total=0,
            page=page,
            page_size=page_size,
            total_pages=0,
            items=[],
        )

    # Шаг 2: Запрос для подсчета сотрудников с проходами + фильтры
    count_query = select(func.count()).select_from(PlatonusEmployee).where(
        PlatonusEmployee.iin.in_(iins_with_attendance)
    )

    # Шаг 3: Запрос для получения сотрудников с проходами + фильтры
    query = select(PlatonusEmployee).where(
        PlatonusEmployee.iin.in_(iins_with_attendance)
    )

    # Применить фильтры к обоим запросам
    if faculty_id is not None:
        query = query.where(PlatonusEmployee.faculty_id == faculty_id)
        count_query = count_query.where(PlatonusEmployee.faculty_id == faculty_id)

    if subdivision_id is not None:
        query = query.where(PlatonusEmployee.subdivision_id == subdivision_id)
        count_query = count_query.where(PlatonusEmployee.subdivision_id == subdivision_id)

    if position_type:
        query = query.where(PlatonusEmployee.position_type == position_type)
        count_query = count_query.where(PlatonusEmployee.position_type == position_type)

    if search:
        search_pattern = f"%{search}%"
        search_filter = or_(
            PlatonusEmployee.firstname.ilike(search_pattern),
            PlatonusEmployee.lastname.ilike(search_pattern),
            PlatonusEmployee.patronymic.ilike(search_pattern),
            PlatonusEmployee.iin.ilike(search_pattern),
        )
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)

    # Подсчитать total
    total_count = await db.scalar(count_query)
    total_count = total_count or 0

    # Сортировка и пагинация
    query = query.order_by(PlatonusEmployee.lastname, PlatonusEmployee.firstname)
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    # Получить сотрудников для текущей страницы
    result = await db.execute(query)
    employees = result.scalars().all()

    # Если нет сотрудников на этой странице
    if not employees:
        total_pages = (total_count + page_size - 1) // page_size
        return EmployeeAttendanceListResponse(
            date=date_str,
            total=total_count,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            items=[],
        )

    # Получить IIN'ы сотрудников на текущей странице
    employee_iins = [emp.iin for emp in employees]

    # Получить attendance только для сотрудников текущей страницы
    attendance_query = select(AttendanceRecord).where(
        AttendanceRecord.iin.in_(employee_iins),
        AttendanceRecord.access_date == date_str
    ).order_by(AttendanceRecord.iin, AttendanceRecord.access_datetime)

    attendance_result = await db.execute(attendance_query)
    all_attendance_records = attendance_result.scalars().all()

    # Сгруппировать записи по IIN
    attendance_by_iin = {}
    for record in all_attendance_records:
        if record.iin not in attendance_by_iin:
            attendance_by_iin[record.iin] = []
        attendance_by_iin[record.iin].append(record)

    # Для каждого сотрудника создать сводку
    employees_attendance = []

    for emp in employees:
        attendance_records = attendance_by_iin.get(emp.iin, [])

        # Найти первый вход и последний выход
        first_entry = None
        last_exit = None

        for record in attendance_records:
            if record.direction == "Вход" and first_entry is None:
                first_entry = record.access_time
            if record.direction == "Выход":
                last_exit = record.access_time

        # Преобразовать записи в схемы
        passes = [
            EmployeeAttendanceRecord(
                id=rec.id,
                access_datetime=rec.access_datetime,
                access_time=rec.access_time,
                direction=rec.direction,
                device_name=rec.device_name,
            )
            for rec in attendance_records
        ]

        # Создать сводку
        employee_summary = EmployeeAttendanceSummary(
            iin=emp.iin,
            firstname=emp.firstname,
            lastname=emp.lastname,
            patronymic=emp.patronymic,
            position=emp.position,
            position_type=emp.position_type,
            cafedra=emp.cafedra_name,
            faculty=emp.faculty_name,
            faculty_id=emp.faculty_id,
            subdivision=emp.subdivision_name,
            subdivision_id=emp.subdivision_id,
            total_passes=len(attendance_records),
            first_entry=first_entry,
            last_exit=last_exit,
            passes=passes,
        )

        employees_attendance.append(employee_summary)

    # Вычислить количество страниц
    total_pages = (total_count + page_size - 1) // page_size

    return EmployeeAttendanceListResponse(
        date=date_str,
        total=total_count,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        items=employees_attendance,
    )


@router.get(
    "/attendance/late",
    response_model=LateEmployeesResponse,
    summary="Опоздавшие сотрудники",
    description="""
    Получить список опоздавших сотрудников за определенный день.

    **Источник данных:**
    - История проходов из attendance_records (турникеты)
    - Данные сотрудников из platonus_employees (должность, факультет, подразделение)

    **Параметры фильтрации:**
    - `date`: Дата (YYYY-MM-DD), по умолчанию сегодня
    - `threshold_time`: Пороговое время начала работы (HH:MM:SS), обязательный параметр
    - `faculty_id`: ID факультета (для преподавателей)
    - `subdivision_id`: ID подразделения (для административного персонала)

    **Возвращает:**
    - Список сотрудников, которые пришли после порогового времени
    - Время первого входа и количество минут опоздания для каждого
    """,
)
async def get_late_employees(
    threshold_time: str = Query(..., description="Пороговое время (HH:MM:SS)"),
    date_param: Optional[str] = Query(None, alias="date", description="Дата (YYYY-MM-DD)"),
    faculty_id: Optional[int] = Query(None, description="ID факультета"),
    subdivision_id: Optional[int] = Query(None, description="ID подразделения"),
    page: int = Query(1, ge=1, description="Номер страницы"),
    page_size: int = Query(20, ge=10, le=100, description="Размер страницы"),
    db: AsyncSession = Depends(get_db),
):
    """
    Получить список опоздавших сотрудников за день
    """

    # Определить дату
    if date_param:
        try:
            target_date = datetime.strptime(date_param, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Неверный формат даты. Используйте YYYY-MM-DD")
    else:
        target_date = date.today()

    date_str = target_date.strftime("%Y-%m-%d")

    # Парсинг порогового времени
    try:
        threshold_time_obj = datetime.strptime(threshold_time, "%H:%M:%S").time()
    except ValueError:
        try:
            # Попробовать формат HH:MM
            threshold_time_obj = datetime.strptime(threshold_time, "%H:%M").time()
            threshold_time = threshold_time_obj.strftime("%H:%M:%S")
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Неверный формат времени. Используйте HH:MM:SS или HH:MM"
            )

    # Получить всех сотрудников из Platonus с фильтрами
    query = select(PlatonusEmployee)

    # Применить фильтры
    if faculty_id is not None:
        query = query.where(PlatonusEmployee.faculty_id == faculty_id)

    if subdivision_id is not None:
        query = query.where(PlatonusEmployee.subdivision_id == subdivision_id)

    result = await db.execute(query)
    employees = result.scalars().all()

    # Если нет сотрудников - вернуть пустой результат
    if not employees:
        return LateEmployeesResponse(
            date=date_str,
            threshold_time=threshold_time,
            total_late=0,
            page=page,
            page_size=page_size,
            total_pages=0,
            items=[],
        )

    # Получить IIN'ы всех сотрудников
    employee_iins = [emp.iin for emp in employees]

    # Один запрос для получения всех записей attendance за день (только входы)
    attendance_query = (
        select(AttendanceRecord)
        .where(
            AttendanceRecord.iin.in_(employee_iins),
            AttendanceRecord.access_date == date_str,
            AttendanceRecord.direction == "Вход",
        )
        .order_by(AttendanceRecord.iin, AttendanceRecord.access_datetime)
    )

    attendance_result = await db.execute(attendance_query)
    all_attendance_records = attendance_result.scalars().all()

    # Сгруппировать записи по IIN (нам нужен только первый вход для каждого)
    first_entry_by_iin = {}
    for record in all_attendance_records:
        if record.iin not in first_entry_by_iin:
            first_entry_by_iin[record.iin] = record

    # Для каждого сотрудника проверить опоздание
    late_employees = []

    for emp in employees:
        first_entry_record = first_entry_by_iin.get(emp.iin)

        # Если нет записей о входе - пропустить сотрудника
        if not first_entry_record:
            continue

        # Получить время первого входа
        try:
            entry_time_obj = datetime.strptime(first_entry_record.access_time, "%H:%M:%S").time()
        except ValueError:
            # Если формат времени неверный - пропустить
            continue

        # Сравнить с пороговым временем
        if entry_time_obj > threshold_time_obj:
            # Вычислить минуты опоздания
            threshold_datetime = datetime.combine(target_date, threshold_time_obj)
            entry_datetime = datetime.combine(target_date, entry_time_obj)
            minutes_late = int((entry_datetime - threshold_datetime).total_seconds() / 60)

            # Создать запись об опоздавшем
            late_employee = LateEmployeeSummary(
                iin=emp.iin,
                firstname=emp.firstname,
                lastname=emp.lastname,
                patronymic=emp.patronymic,
                position=emp.position,
                position_type=emp.position_type,
                cafedra=emp.cafedra_name,
                faculty=emp.faculty_name,
                faculty_id=emp.faculty_id,
                subdivision=emp.subdivision_name,
                subdivision_id=emp.subdivision_id,
                first_entry_time=first_entry_record.access_time,
                first_entry_datetime=first_entry_record.access_datetime,
                minutes_late=minutes_late,
            )

            late_employees.append(late_employee)

    # Сортировка по минутам опоздания (от большего к меньшему)
    late_employees.sort(key=lambda x: x.minutes_late, reverse=True)

    # Пагинация в памяти
    total_late = len(late_employees)
    total_pages = (total_late + page_size - 1) // page_size if total_late > 0 else 0

    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    paginated_employees = late_employees[start_idx:end_idx]

    return LateEmployeesResponse(
        date=date_str,
        threshold_time=threshold_time,
        total_late=total_late,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        items=paginated_employees,
    )


@router.get(
    "/attendance/late/stats",
    response_model=LateStatisticsResponse,
    summary="Статистика опозданий за период",
    description="""
    Получить детальную статистику по опоздавшим сотрудникам за период.

    **Параметры:**
    - `date_from` (обязательный): Начало периода (YYYY-MM-DD)
    - `date_to` (обязательный): Конец периода (YYYY-MM-DD)
    - `threshold_time` (обязательный): Пороговое время начала работы (HH:MM:SS)
    - `faculty_id` (опционально): Фильтр по факультету
    - `subdivision_id` (опционально): Фильтр по подразделению
    - `top_limit` (опционально): Количество сотрудников в топе (по умолчанию 10)

    **Включает:**
    1. Топ опоздавших сотрудников
    2. Статистика по факультетам/подразделениям
    3. Динамика по дням (с днём недели)
    4. Распределение по времени опоздания

    **Пример:**
    ```
    GET /api/v1/employees/attendance/late/stats?date_from=2026-01-01&date_to=2026-01-31&threshold_time=09:00:00&top_limit=20
    ```
    """,
)
async def get_late_statistics(
    date_from: str = Query(..., description="Начало периода (YYYY-MM-DD)"),
    date_to: str = Query(..., description="Конец периода (YYYY-MM-DD)"),
    threshold_time: str = Query(..., description="Пороговое время (HH:MM:SS)"),
    faculty_id: Optional[int] = Query(None, description="ID факультета"),
    subdivision_id: Optional[int] = Query(None, description="ID подразделения"),
    top_limit: int = Query(10, ge=1, le=100, description="Количество в топе"),
    db: AsyncSession = Depends(get_db),
):
    """
    Получить статистику опозданий за период
    """

    # Парсинг дат
    try:
        start_date = datetime.strptime(date_from, "%Y-%m-%d").date()
        end_date = datetime.strptime(date_to, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=400, detail="Неверный формат даты. Используйте YYYY-MM-DD"
        )

    if start_date > end_date:
        raise HTTPException(status_code=400, detail="date_from должна быть меньше или равна date_to")

    # Парсинг порогового времени
    try:
        threshold_time_obj = datetime.strptime(threshold_time, "%H:%M:%S").time()
    except ValueError:
        try:
            threshold_time_obj = datetime.strptime(threshold_time, "%H:%M").time()
            threshold_time = threshold_time_obj.strftime("%H:%M:%S")
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Неверный формат времени. Используйте HH:MM:SS или HH:MM"
            )

    # Получить всех сотрудников из Platonus с фильтрами
    query = select(PlatonusEmployee)

    if faculty_id is not None:
        query = query.where(PlatonusEmployee.faculty_id == faculty_id)

    if subdivision_id is not None:
        query = query.where(PlatonusEmployee.subdivision_id == subdivision_id)

    result = await db.execute(query)
    employees = result.scalars().all()

    if not employees:
        # Вернуть пустую статистику
        return LateStatisticsResponse(
            date_from=date_from,
            date_to=date_to,
            threshold_time=threshold_time,
            total_working_days=0,
            total_lates=0,
            unique_late_employees=0,
            top_late_employees=[],
            by_division=[],
            by_day=[],
            time_distribution=[],
        )

    # Создать map сотрудников по IIN
    employees_by_iin = {emp.iin: emp for emp in employees}
    employee_iins = list(employees_by_iin.keys())

    # Получить все дни в периоде
    working_days = []
    current_date = start_date
    while current_date <= end_date:
        working_days.append(current_date.strftime("%Y-%m-%d"))
        current_date += timedelta(days=1)

    # Получить все записи attendance за период (только входы)
    attendance_query = (
        select(AttendanceRecord)
        .where(
            AttendanceRecord.iin.in_(employee_iins),
            AttendanceRecord.access_date >= date_from,
            AttendanceRecord.access_date <= date_to,
            AttendanceRecord.direction == "Вход",
        )
        .order_by(AttendanceRecord.iin, AttendanceRecord.access_date, AttendanceRecord.access_datetime)
    )

    attendance_result = await db.execute(attendance_query)
    all_attendance_records = attendance_result.scalars().all()

    # Группировать записи по IIN и дате (нам нужен первый вход каждого дня)
    first_entries_by_iin_date = {}
    for record in all_attendance_records:
        key = (record.iin, record.access_date)
        if key not in first_entries_by_iin_date:
            first_entries_by_iin_date[key] = record

    # Собрать данные об опозданиях
    late_records = []  # список кортежей (iin, date, minutes_late, employee)

    for (iin, date_str), record in first_entries_by_iin_date.items():
        try:
            entry_time_obj = datetime.strptime(record.access_time, "%H:%M:%S").time()
        except ValueError:
            continue

        if entry_time_obj > threshold_time_obj:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            threshold_datetime = datetime.combine(target_date, threshold_time_obj)
            entry_datetime = datetime.combine(target_date, entry_time_obj)
            minutes_late = int((entry_datetime - threshold_datetime).total_seconds() / 60)

            employee = employees_by_iin.get(iin)
            if employee:
                late_records.append((iin, date_str, minutes_late, employee))

    # Если нет опозданий - вернуть пустую статистику
    if not late_records:
        return LateStatisticsResponse(
            date_from=date_from,
            date_to=date_to,
            threshold_time=threshold_time,
            total_working_days=len(working_days),
            total_lates=0,
            unique_late_employees=0,
            top_late_employees=[],
            by_division=[],
            by_day=[],
            time_distribution=[],
        )

    # ========================================
    # 1. ТОП ОПОЗДАВШИХ СОТРУДНИКОВ
    # ========================================

    late_stats_by_iin = defaultdict(lambda: {"lates": [], "employee": None})

    for iin, date_str, minutes_late, employee in late_records:
        late_stats_by_iin[iin]["lates"].append(minutes_late)
        late_stats_by_iin[iin]["employee"] = employee

    top_employees = []
    for iin, data in late_stats_by_iin.items():
        lates = data["lates"]
        emp = data["employee"]

        top_employees.append(
            TopLateEmployee(
                iin=emp.iin,
                firstname=emp.firstname,
                lastname=emp.lastname,
                patronymic=emp.patronymic,
                position=emp.position,
                position_type=emp.position_type,
                cafedra=emp.cafedra_name,
                faculty=emp.faculty_name,
                faculty_id=emp.faculty_id,
                subdivision=emp.subdivision_name,
                subdivision_id=emp.subdivision_id,
                total_lates=len(lates),
                avg_late_minutes=round(sum(lates) / len(lates), 1),
                max_late_minutes=max(lates),
                min_late_minutes=min(lates),
            )
        )

    # Сортировка по количеству опозданий, затем по среднему времени
    top_employees.sort(key=lambda x: (x.total_lates, x.avg_late_minutes), reverse=True)
    top_employees = top_employees[:top_limit]

    # ========================================
    # 2. СТАТИСТИКА ПО ПОДРАЗДЕЛЕНИЯМ/ФАКУЛЬТЕТАМ
    # ========================================

    division_stats = defaultdict(lambda: {
        "name": None,
        "type": None,
        "id": None,
        "total_employees": 0,
        "late_records": [],
        "unique_late_iins": set()
    })

    # Подсчитать общее количество сотрудников в каждом подразделении
    for emp in employees:
        if emp.faculty_id:
            key = f"faculty_{emp.faculty_id}"
            division_stats[key]["name"] = emp.faculty_name
            division_stats[key]["type"] = "faculty"
            division_stats[key]["id"] = emp.faculty_id
            division_stats[key]["total_employees"] += 1
        elif emp.subdivision_id:
            key = f"subdivision_{emp.subdivision_id}"
            division_stats[key]["name"] = emp.subdivision_name
            division_stats[key]["type"] = "subdivision"
            division_stats[key]["id"] = emp.subdivision_id
            division_stats[key]["total_employees"] += 1

    # Добавить опоздания
    for iin, date_str, minutes_late, employee in late_records:
        if employee.faculty_id:
            key = f"faculty_{employee.faculty_id}"
            division_stats[key]["late_records"].append(minutes_late)
            division_stats[key]["unique_late_iins"].add(iin)
        elif employee.subdivision_id:
            key = f"subdivision_{employee.subdivision_id}"
            division_stats[key]["late_records"].append(minutes_late)
            division_stats[key]["unique_late_iins"].add(iin)

    division_list = []
    for key, data in division_stats.items():
        if data["name"] and len(data["late_records"]) > 0:
            total_employees = data["total_employees"]
            unique_late = len(data["unique_late_iins"])
            late_percentage = round((unique_late / total_employees * 100), 1) if total_employees > 0 else 0

            division_list.append(
                DivisionLateStats(
                    name=data["name"],
                    type=data["type"],
                    id=data["id"],
                    total_employees=total_employees,
                    total_lates=len(data["late_records"]),
                    unique_late_employees=unique_late,
                    late_percentage=late_percentage,
                    avg_late_minutes=round(sum(data["late_records"]) / len(data["late_records"]), 1),
                )
            )

    # Сортировка по проценту опоздавших
    division_list.sort(key=lambda x: x.late_percentage, reverse=True)

    # ========================================
    # 3. ДИНАМИКА ПО ДНЯМ
    # ========================================

    daily_stats = defaultdict(list)

    for iin, date_str, minutes_late, employee in late_records:
        daily_stats[date_str].append(minutes_late)

    daily_list = []
    for day_str in working_days:
        if day_str in daily_stats:
            lates = daily_stats[day_str]
            day_date = datetime.strptime(day_str, "%Y-%m-%d").date()
            day_name = day_date.strftime("%A")  # Monday, Tuesday, etc.

            daily_list.append(
                DailyLateStats(
                    date=day_str,
                    day_of_week=day_name,
                    total_lates=len(lates),
                    avg_late_minutes=round(sum(lates) / len(lates), 1),
                )
            )

    # ========================================
    # 4. РАСПРЕДЕЛЕНИЕ ПО ВРЕМЕНИ ОПОЗДАНИЯ
    # ========================================

    time_ranges = {
        "1-15 минут": (1, 15),
        "15-30 минут": (15, 30),
        "30-60 минут": (30, 60),
        "60+ минут": (60, float('inf'))
    }

    time_distribution_counts = defaultdict(int)
    total_lates_count = len(late_records)

    for iin, date_str, minutes_late, employee in late_records:
        for range_name, (min_val, max_val) in time_ranges.items():
            if min_val <= minutes_late < max_val:
                time_distribution_counts[range_name] += 1
                break

    time_dist_list = []
    for range_name in ["1-15 минут", "15-30 минут", "30-60 минут", "60+ минут"]:
        count = time_distribution_counts[range_name]
        percentage = round((count / total_lates_count * 100), 1) if total_lates_count > 0 else 0

        time_dist_list.append(
            LateTimeDistribution(
                range=range_name,
                count=count,
                percentage=percentage,
            )
        )

    # ========================================
    # ФИНАЛЬНЫЙ ОТВЕТ
    # ========================================

    return LateStatisticsResponse(
        date_from=date_from,
        date_to=date_to,
        threshold_time=threshold_time,
        total_working_days=len(working_days),
        total_lates=total_lates_count,
        unique_late_employees=len(late_stats_by_iin),
        top_late_employees=top_employees,
        by_division=division_list,
        by_day=daily_list,
        time_distribution=time_dist_list,
    )


# ==========================================
# Справочники (Faculties, Subdivisions)
# ==========================================


@router.get(
    "/faculties",
    response_model=PlatonusFacultyListResponse,
    summary="Получить список факультетов",
    description="""
    Получить список всех факультетов из Platonus с количеством сотрудников.

    **Источник данных:**
    - Таблица platonus_employees (синхронизируется раз в неделю)
    - Группировка по faculty_id и faculty_name

    **Возвращает:**
    - ID факультета
    - Название факультета
    - Количество сотрудников в каждом факультете

    **Сортировка:**
    - По названию факультета (A-Z)
    """,
)
async def get_platonus_faculties(
    db: AsyncSession = Depends(get_db),
):
    """
    Получить список факультетов из Platonus
    """
    # Запрос для получения уникальных факультетов с подсчётом сотрудников
    query = (
        select(
            PlatonusEmployee.faculty_id,
            PlatonusEmployee.faculty_name,
            func.count(PlatonusEmployee.iin).label("employee_count"),
        )
        .where(
            PlatonusEmployee.faculty_id.isnot(None),
            PlatonusEmployee.faculty_name.isnot(None),
        )
        .group_by(PlatonusEmployee.faculty_id, PlatonusEmployee.faculty_name)
        .order_by(PlatonusEmployee.faculty_name)
    )

    result = await db.execute(query)
    faculties_data = result.all()

    # Преобразовать в схемы
    faculties = [
        PlatonusFaculty(
            faculty_id=row.faculty_id,
            faculty_name=row.faculty_name,
            employee_count=row.employee_count,
        )
        for row in faculties_data
    ]

    return PlatonusFacultyListResponse(
        total=len(faculties),
        items=faculties,
    )


@router.get(
    "/subdivisions",
    response_model=PlatonusSubdivisionListResponse,
    summary="Получить список структурных подразделений",
    description="""
    Получить список всех структурных подразделений из Platonus с количеством сотрудников.

    **Источник данных:**
    - Таблица platonus_employees (синхронизируется раз в неделю)
    - Группировка по subdivision_id и subdivision_name

    **Возвращает:**
    - ID подразделения
    - Название подразделения
    - Тип подразделения (если есть)
    - Количество сотрудников в каждом подразделении

    **Сортировка:**
    - По названию подразделения (A-Z)

    **Пагинация:**
    - page: номер страницы (по умолчанию 1)
    - page_size: размер страницы (по умолчанию 20, мин 10, макс 100)
    """,
)
async def get_platonus_subdivisions(
    page: int = Query(1, ge=1, description="Номер страницы"),
    page_size: int = Query(20, ge=10, le=100, description="Размер страницы"),
    db: AsyncSession = Depends(get_db),
):
    """
    Получить список структурных подразделений из Platonus с пагинацией
    """
    # Подзапрос для группировки и подсчёта
    subquery = (
        select(
            PlatonusEmployee.subdivision_id,
            PlatonusEmployee.subdivision_name,
            PlatonusEmployee.subdivision_type,
            func.count(PlatonusEmployee.iin).label("employee_count"),
        )
        .where(
            PlatonusEmployee.subdivision_id.isnot(None),
            PlatonusEmployee.subdivision_name.isnot(None),
        )
        .group_by(
            PlatonusEmployee.subdivision_id,
            PlatonusEmployee.subdivision_name,
            PlatonusEmployee.subdivision_type,
        )
        .subquery()
    )

    # Запрос для подсчёта общего количества подразделений
    count_query = select(func.count()).select_from(subquery)
    total_count = await db.scalar(count_query)

    # Запрос для получения подразделений с пагинацией
    offset = (page - 1) * page_size
    query = (
        select(
            subquery.c.subdivision_id,
            subquery.c.subdivision_name,
            subquery.c.subdivision_type,
            subquery.c.employee_count,
        )
        .order_by(subquery.c.subdivision_name)
        .offset(offset)
        .limit(page_size)
    )

    result = await db.execute(query)
    subdivisions_data = result.all()

    # Преобразовать в схемы
    subdivisions = [
        PlatonusSubdivision(
            subdivision_id=row.subdivision_id,
            subdivision_name=row.subdivision_name,
            subdivision_type=row.subdivision_type,
            employee_count=row.employee_count,
        )
        for row in subdivisions_data
    ]

    # Вычислить количество страниц
    total_pages = (total_count + page_size - 1) // page_size

    return PlatonusSubdivisionListResponse(
        total=total_count,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        items=subdivisions,
    )
