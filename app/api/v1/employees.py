"""
Employees API endpoints - получение списка сотрудников кто проходит турникет
Данные берутся из кеша platonus_employees (синхронизация раз в неделю)
"""

from typing import Optional
from fastapi import APIRouter, Query, Depends, HTTPException
from sqlalchemy import select, func, or_, text
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date, datetime, time

from app.schemas import (
    EmployeeBase,
    EmployeeListResponse,
    EmployeeAttendanceSummary,
    EmployeeAttendanceListResponse,
    EmployeeAttendanceRecord,
    LateEmployeeSummary,
    LateEmployeesResponse,
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

    **Параметры:**
    - `position_type`: Фильтр по типу должности (Преподаватель/Руководитель/Специалист/и т.д.)
    - `faculty_id`: Фильтр по ID факультета (для преподавателей)
    - `subdivision_id`: Фильтр по ID подразделения (для административного персонала)
    - `search`: Поиск по ФИО или IIN

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
    db: AsyncSession = Depends(get_db),
):
    """
    Получить список сотрудников из кеша
    """

    # Построить запрос
    query = select(PlatonusEmployee)

    # Фильтры
    if position_type:
        query = query.where(PlatonusEmployee.position_type == position_type)

    if faculty_id is not None:
        query = query.where(PlatonusEmployee.faculty_id == faculty_id)

    if subdivision_id is not None:
        query = query.where(PlatonusEmployee.subdivision_id == subdivision_id)

    if search:
        search_pattern = f"%{search}%"
        query = query.where(
            or_(
                PlatonusEmployee.firstname.ilike(search_pattern),
                PlatonusEmployee.lastname.ilike(search_pattern),
                PlatonusEmployee.patronymic.ilike(search_pattern),
                PlatonusEmployee.iin.ilike(search_pattern),
            )
        )

    # Сортировка
    query = query.order_by(PlatonusEmployee.lastname, PlatonusEmployee.firstname)

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

    return EmployeeListResponse(total=len(employees), items=employees)


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

    **Параметры фильтрации:**
    - `date`: Дата (YYYY-MM-DD), по умолчанию сегодня
    - `faculty_id`: ID факультета (для преподавателей)
    - `subdivision_id`: ID подразделения (для административного персонала)
    - `position_type`: Тип должности (Преподаватель/Административный персонал/и т.д.)
    - `search`: Поиск по ФИО или IIN

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

    # Получить всех сотрудников из Platonus с фильтрами
    query = select(PlatonusEmployee)

    # Применить фильтры
    if faculty_id is not None:
        query = query.where(PlatonusEmployee.faculty_id == faculty_id)

    if subdivision_id is not None:
        query = query.where(PlatonusEmployee.subdivision_id == subdivision_id)

    if position_type:
        query = query.where(PlatonusEmployee.position_type == position_type)

    if search:
        search_pattern = f"%{search}%"
        query = query.where(
            or_(
                PlatonusEmployee.firstname.ilike(search_pattern),
                PlatonusEmployee.lastname.ilike(search_pattern),
                PlatonusEmployee.patronymic.ilike(search_pattern),
                PlatonusEmployee.iin.ilike(search_pattern),
            )
        )

    result = await db.execute(query)
    employees = result.scalars().all()

    # Если нет сотрудников - вернуть пустой результат
    if not employees:
        return EmployeeAttendanceListResponse(
            date=date_str,
            total=0,
            items=[],
        )

    # Получить IIN'ы всех сотрудников
    employee_iins = [emp.iin for emp in employees]

    # Один запрос для получения всех записей attendance за день для этих сотрудников
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

        # Если нет записей - пропустить сотрудника
        if not attendance_records:
            continue

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

    return EmployeeAttendanceListResponse(
        date=date_str,
        total=len(employees_attendance),
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

    return LateEmployeesResponse(
        date=date_str,
        threshold_time=threshold_time,
        total_late=len(late_employees),
        items=late_employees,
    )
