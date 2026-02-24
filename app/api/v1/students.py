"""
Students API endpoints - получение списка студентов кто проходит турникет
Данные берутся из кеша platonus_students (синхронизация раз в неделю)
"""

from typing import Optional
from fastapi import APIRouter, Query, Depends, HTTPException
from sqlalchemy import select, func, or_, text
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date, datetime, time, timedelta
from collections import defaultdict

from app.schemas.students import (
    StudentBase,
    StudentListResponse,
    StudentAttendanceSummary,
    StudentAttendanceListResponse,
    StudentAttendanceRecord,
    LateStudentSummary,
    LateStudentsResponse,
    FirstLessonStudentInfo,
    Specialization,
    SpecializationListResponse,
    StudentGroup,
    StudentGroupListResponse,
    StudentAttendanceHistory,
    StudentAttendanceHistoryRecord,
)
from app.models import PlatonusStudent, AttendanceRecord, StudentSchedule
from app.api.dependencies import get_db
from app.services.student_sync import StudentSyncService
from app.services.student_schedule_sync import StudentScheduleSyncService
from app.services.student_late_service import StudentLateService

router = APIRouter(prefix="/students", tags=["Students"])


@router.get(
    "",
    response_model=StudentListResponse,
    summary="Получить список студентов",
    description="""
    Получить список студентов которые проходят турникет.

    **Источник данных:**
    - Список IIN из HikCentral (attendance_records, person_type in student_yu/student_yc/bachelor/master)
    - Данные обогащены из Platonus (группа, специальность)
    - Данные кешируются в таблице platonus_students
    - Синхронизация: раз в неделю

    **Фильтры:**
    - `student_type`: Тип студента (student_yu, student_yc, bachelor, master)
    - `specialization_id`: ID специальности/ОП
    - `student_group_id`: ID группы
    - `course_number`: Курс обучения (1-5)
    - `cafedra_id`: ID кафедры
    - `search`: Поиск по ФИО или IIN

    **Пагинация:**
    - `page`: Номер страницы (default: 1, min: 1)
    - `page_size`: Размер страницы (default: 20, min: 10, max: 100)

    **Сортировка:**
    - `sort_by`: Поле для сортировки (lastname, firstname, student_type, course_number)
    - `sort_order`: Порядок сортировки (asc, desc)
    """,
)
async def get_students(
    student_type: Optional[str] = Query(None, description="Тип студента (student_yu, student_yc, bachelor, master)"),
    specialization_id: Optional[int] = Query(None, description="ID специальности"),
    student_group_id: Optional[int] = Query(None, description="ID группы"),
    course_number: Optional[int] = Query(None, ge=1, le=5, description="Курс обучения (1-5)"),
    cafedra_id: Optional[int] = Query(None, description="ID кафедры"),
    search: Optional[str] = Query(None, description="Поиск по ФИО или IIN"),
    page: int = Query(1, ge=1, description="Номер страницы"),
    page_size: int = Query(20, ge=10, le=100, description="Размер страницы"),
    sort_by: str = Query("lastname", description="Поле для сортировки"),
    sort_order: str = Query("asc", description="Порядок: asc или desc"),
    db: AsyncSession = Depends(get_db),
):
    """
    Получить список студентов из кеша
    """

    # Построить базовый запрос для подсчета
    count_query = select(func.count()).select_from(PlatonusStudent)

    # Построить запрос для данных
    query = select(PlatonusStudent)

    # Фильтры
    if student_type:
        query = query.where(PlatonusStudent.student_type == student_type)
        count_query = count_query.where(PlatonusStudent.student_type == student_type)

    if specialization_id is not None:
        query = query.where(PlatonusStudent.specialization_id == specialization_id)
        count_query = count_query.where(PlatonusStudent.specialization_id == specialization_id)

    if student_group_id is not None:
        query = query.where(PlatonusStudent.student_group_id == student_group_id)
        count_query = count_query.where(PlatonusStudent.student_group_id == student_group_id)

    if course_number is not None:
        query = query.where(PlatonusStudent.course_number == course_number)
        count_query = count_query.where(PlatonusStudent.course_number == course_number)

    if cafedra_id is not None:
        query = query.where(PlatonusStudent.cafedra_id == cafedra_id)
        count_query = count_query.where(PlatonusStudent.cafedra_id == cafedra_id)

    if search:
        search_pattern = f"%{search}%"
        search_filter = or_(
            PlatonusStudent.firstname.ilike(search_pattern),
            PlatonusStudent.lastname.ilike(search_pattern),
            PlatonusStudent.patronymic.ilike(search_pattern),
            PlatonusStudent.iin.ilike(search_pattern),
        )
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)

    # Подсчитать общее количество
    total_count = await db.scalar(count_query)
    total_count = total_count or 0

    # Сортировка
    sort_column = PlatonusStudent.lastname
    if sort_by == "firstname":
        sort_column = PlatonusStudent.firstname
    elif sort_by == "student_type":
        sort_column = PlatonusStudent.student_type

    if sort_order.lower() == "desc":
        query = query.order_by(sort_column.desc(), PlatonusStudent.lastname, PlatonusStudent.firstname)
    else:
        query = query.order_by(sort_column, PlatonusStudent.lastname, PlatonusStudent.firstname)

    # Пагинация
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    # Выполнить запрос
    result = await db.execute(query)
    students_db = result.scalars().all()

    # Получить время первого занятия для каждого студента
    late_service = StudentLateService(db)
    today = date.today()

    # Преобразовать в схемы
    students = []
    for student in students_db:
        # Определить ожидаемое время первого занятия
        expected_time = None
        if student.student_group_id:
            first_lesson_time = await late_service.get_first_lesson_time(
                student_group_id=student.student_group_id,
                target_date=today,
            )
            if first_lesson_time:
                expected_time = first_lesson_time.strftime("%H:%M")
            else:
                expected_time = "Нет занятий"

        students.append(
            StudentBase(
                student_id=student.student_id,
                iin=student.iin,
                firstname=student.firstname,
                lastname=student.lastname,
                patronymic=student.patronymic,
                student_type=student.student_type,
                student_group=student.student_group_name,
                student_group_id=student.student_group_id,
                specialization=student.specialization_name,
                specialization_id=student.specialization_id,
                specialization_code=student.specialization_code,
                enrollment_year=student.enrollment_year,
                study_year=student.study_year,
                course_number=student.course_number,
                degree=student.degree,
                cafedra_id=student.cafedra_id,
                cafedra_name=student.cafedra_name,
                email=student.email,
                phone=student.phone,
                expected_time=expected_time,
            )
        )

    # Вычислить количество страниц
    total_pages = (total_count + page_size - 1) // page_size

    return StudentListResponse(
        total=total_count,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        items=students,
    )


@router.post(
    "/sync",
    summary="Синхронизировать данные студентов",
    description="""
    Запустить синхронизацию данных студентов из Platonus.

    **Процесс:**
    1. Получить всех уникальных студентов с IIN из HikCentral
    2. Для каждого IIN получить данные из Platonus (группа, специальность)
    3. Сохранить/обновить в таблице platonus_students

    **Примечание:** Обычно запускается автоматически раз в неделю
    """,
)
async def sync_students(db: AsyncSession = Depends(get_db)):
    """
    Синхронизировать данные студентов из Platonus
    """
    service = StudentSyncService(db)
    result = await service.sync_students()
    return result


@router.get(
    "/sync/stats",
    summary="Статистика синхронизации студентов",
    description="""
    Получить статистику последней синхронизации.

    **Включает:**
    - Всего студентов в кеше
    - Дата последней синхронизации
    - Распределение по типам студентов
    - Распределение по специальностям
    - Распределение по группам
    """,
)
async def get_sync_stats(db: AsyncSession = Depends(get_db)):
    """
    Получить статистику синхронизации студентов
    """
    service = StudentSyncService(db)
    stats = await service.get_sync_stats()
    return stats


@router.post(
    "/schedule/sync",
    summary="Синхронизировать расписание студентов",
    description="""
    Запустить синхронизацию расписания студенческих групп из Platonus.

    **Процесс:**
    1. Получить список групп из platonus_students
    2. Для каждой группы получить расписание из Platonus
    3. Сохранить в таблице student_schedule

    **Примечание:** Обычно запускается автоматически раз в день
    """,
)
async def sync_student_schedules(
    study_year: Optional[int] = Query(None, description="Учебный год (например, 2025)"),
    study_term: Optional[int] = Query(None, description="Семестр (1 или 2)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Синхронизировать расписание студенческих групп из Platonus
    """
    service = StudentScheduleSyncService(db)
    result = await service.sync_schedules(study_year=study_year, study_term=study_term)
    return result


@router.get(
    "/schedule/stats",
    summary="Статистика расписания студентов",
    description="""
    Получить статистику синхронизации расписания студентов.
    """,
)
async def get_schedule_stats(
    study_year: int = Query(2025, description="Учебный год"),
    study_term: int = Query(2, description="Семестр"),
    db: AsyncSession = Depends(get_db),
):
    """
    Получить статистику расписания студентов
    """
    service = StudentScheduleSyncService(db)
    stats = await service.get_sync_stats(study_year=study_year, study_term=study_term)
    return stats


@router.get(
    "/attendance",
    response_model=StudentAttendanceListResponse,
    summary="Посещаемость студентов за день",
    description="""
    Получить данные о посещаемости студентов за определенный день.

    **Источник данных:**
    - История проходов из attendance_records (турникеты)
    - Данные студентов из platonus_students (группа, специальность)

    **Фильтры:**
    - `date`: Дата (YYYY-MM-DD), по умолчанию сегодня
    - `specialization_id`: ID специальности
    - `student_group_id`: ID группы
    - `student_type`: Тип студента
    - `search`: Поиск по ФИО или IIN

    **Пагинация:**
    - `page`: Номер страницы (default: 1, min: 1)
    - `page_size`: Размер страницы (default: 20, min: 10, max: 100)

    **Возвращает:**
    - Список студентов с их проходами за день
    - Первый вход и последний выход
    - Все проходы с временем и направлением
    """,
)
async def get_students_attendance(
    date_param: Optional[str] = Query(None, alias="date", description="Дата (YYYY-MM-DD)"),
    specialization_id: Optional[int] = Query(None, description="ID специальности"),
    student_group_id: Optional[int] = Query(None, description="ID группы"),
    student_type: Optional[str] = Query(None, description="Тип студента"),
    search: Optional[str] = Query(None, description="Поиск по ФИО или IIN"),
    page: int = Query(1, ge=1, description="Номер страницы"),
    page_size: int = Query(20, ge=10, le=100, description="Размер страницы"),
    db: AsyncSession = Depends(get_db),
):
    """
    Получить посещаемость студентов за день
    """

    # Определить дату
    if date_param:
        try:
            target_date = datetime.strptime(date_param, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Неверный формат даты. Используйте YYYY-MM-DD")
    else:
        target_date = date.today()

    # Построить запрос для получения студентов с проходами
    base_query = """
        SELECT
            ps.iin,
            ps.firstname,
            ps.lastname,
            ps.patronymic,
            ps.student_type,
            ps.student_group_name,
            ps.specialization_name,
            ar.id as record_id,
            ar.access_datetime,
            ar.access_time,
            ar.direction,
            ar.device_name
        FROM platonus_students ps
        INNER JOIN attendance_records ar ON ps.iin = ar.iin
        WHERE ar.access_date = :target_date
    """

    params = {"target_date": target_date.isoformat()}

    if specialization_id is not None:
        base_query += " AND ps.specialization_id = :specialization_id"
        params["specialization_id"] = specialization_id

    if student_group_id is not None:
        base_query += " AND ps.student_group_id = :student_group_id"
        params["student_group_id"] = student_group_id

    if student_type:
        base_query += " AND ps.student_type = :student_type"
        params["student_type"] = student_type

    if search:
        base_query += """ AND (
            ps.firstname ILIKE :search
            OR ps.lastname ILIKE :search
            OR ps.patronymic ILIKE :search
            OR ps.iin ILIKE :search
        )"""
        params["search"] = f"%{search}%"

    base_query += " ORDER BY ar.access_datetime"

    result = await db.execute(text(base_query), params)
    records = result.fetchall()

    # Группировать по студентам
    students_data = defaultdict(lambda: {
        "iin": None,
        "firstname": None,
        "lastname": None,
        "patronymic": None,
        "student_type": None,
        "student_group": None,
        "specialization": None,
        "passes": [],
        "first_entry": None,
        "last_exit": None,
    })

    for record in records:
        iin = record[0]
        if students_data[iin]["iin"] is None:
            students_data[iin]["iin"] = iin
            students_data[iin]["firstname"] = record[1]
            students_data[iin]["lastname"] = record[2]
            students_data[iin]["patronymic"] = record[3]
            students_data[iin]["student_type"] = record[4]
            students_data[iin]["student_group"] = record[5]
            students_data[iin]["specialization"] = record[6]

        # Добавить проход
        access_datetime = record[8]
        if isinstance(access_datetime, str):
            access_datetime = datetime.fromisoformat(access_datetime)

        access_time = record[9]
        if isinstance(access_time, str):
            access_time_obj = datetime.strptime(access_time, "%H:%M:%S").time()
        else:
            access_time_obj = access_time

        direction = record[10]

        students_data[iin]["passes"].append({
            "id": record[7],
            "access_datetime": access_datetime.isoformat() if access_datetime else None,
            "access_time": access_time if isinstance(access_time, str) else access_time.strftime("%H:%M:%S"),
            "direction": direction,
            "device_name": record[11],
        })

        # Определить первый вход и последний выход
        if direction == "Вход":
            if students_data[iin]["first_entry"] is None:
                students_data[iin]["first_entry"] = access_time if isinstance(access_time, str) else access_time.strftime("%H:%M:%S")
        elif direction == "Выход":
            students_data[iin]["last_exit"] = access_time if isinstance(access_time, str) else access_time.strftime("%H:%M:%S")

    # Преобразовать в список
    students_list = list(students_data.values())

    # Пагинация
    total = len(students_list)
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    paginated_students = students_list[start_idx:end_idx]

    total_pages = (total + page_size - 1) // page_size

    # Преобразовать в схемы
    items = []
    for student in paginated_students:
        passes = [
            StudentAttendanceRecord(
                id=p["id"],
                access_datetime=p["access_datetime"],
                access_time=p["access_time"],
                direction=p["direction"],
                device_name=p["device_name"],
            )
            for p in student["passes"]
        ]

        items.append(
            StudentAttendanceSummary(
                iin=student["iin"],
                firstname=student["firstname"],
                lastname=student["lastname"],
                patronymic=student["patronymic"],
                student_type=student["student_type"],
                student_group=student["student_group"],
                specialization=student["specialization"],
                total_passes=len(passes),
                first_entry=student["first_entry"],
                last_exit=student["last_exit"],
                passes=passes,
            )
        )

    return StudentAttendanceListResponse(
        date=target_date.isoformat(),
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        items=items,
    )


@router.get(
    "/attendance/late",
    response_model=LateStudentsResponse,
    summary="Опоздавшие студенты",
    description="""
    Получить список студентов опоздавших на первое занятие.

    **Логика определения опоздания:**
    - Сравнивается время первого входа с началом первого занятия группы
    - Если расписания нет - не считается опозданием

    **Фильтры:**
    - `date`: Дата (YYYY-MM-DD), по умолчанию сегодня
    - `specialization_id`: ID специальности
    - `student_group_id`: ID группы
    - `student_type`: Тип студента

    **Пагинация:**
    - `page`: Номер страницы (default: 1, min: 1)
    - `page_size`: Размер страницы (default: 20, min: 10, max: 100)
    """,
)
async def get_late_students(
    date_param: Optional[str] = Query(None, alias="date", description="Дата (YYYY-MM-DD)"),
    specialization_id: Optional[int] = Query(None, description="ID специальности"),
    student_group_id: Optional[int] = Query(None, description="ID группы"),
    student_type: Optional[str] = Query(None, description="Тип студента"),
    page: int = Query(1, ge=1, description="Номер страницы"),
    page_size: int = Query(50, ge=10, le=100, description="Размер страницы"),
    db: AsyncSession = Depends(get_db),
):
    """
    Получить список опоздавших студентов
    """

    # Определить дату
    if date_param:
        try:
            target_date = datetime.strptime(date_param, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Неверный формат даты. Используйте YYYY-MM-DD")
    else:
        target_date = date.today()

    # Использовать сервис
    service = StudentLateService(db)
    result = await service.get_late_arrivals(
        target_date=target_date,
        specialization_id=specialization_id,
        student_group_id=student_group_id,
        student_type=student_type,
        page=page,
        page_size=page_size,
    )

    # Преобразовать в схемы
    items = []
    for item in result["items"]:
        first_lesson = None
        if item.get("first_lesson"):
            first_lesson = FirstLessonStudentInfo(
                subject=item["first_lesson"]["subject"],
                teacher=item["first_lesson"]["teacher"],
                time_range=item["first_lesson"]["time_range"],
                auditory=item["first_lesson"]["auditory"],
            )

        items.append(
            LateStudentSummary(
                iin=item["iin"],
                firstname=item["firstname"],
                lastname=item["lastname"],
                patronymic=item["patronymic"],
                student_type=item["student_type"],
                student_group=item["student_group"],
                student_group_id=item["student_group_id"],
                specialization=item["specialization"],
                specialization_id=item["specialization_id"],
                expected_time=item["expected_time"],
                first_entry_time=item["first_entry_time"],
                first_entry_datetime=item["first_entry_datetime"],
                minutes_late=item["minutes_late"],
                first_lesson=first_lesson,
            )
        )

    return LateStudentsResponse(
        date=result["date"],
        total_late=result["total_late"],
        page=result["page"],
        page_size=result["page_size"],
        total_pages=result["total_pages"],
        items=items,
    )


@router.get(
    "/{iin}/attendance",
    response_model=StudentAttendanceHistory,
    summary="История посещаемости студента",
    description="""
    Получить историю посещаемости конкретного студента.

    **Фильтры:**
    - `date_from`: Начало периода (YYYY-MM-DD)
    - `date_to`: Конец периода (YYYY-MM-DD)

    **Пагинация:**
    - `page`: Номер страницы (default: 1, min: 1)
    - `page_size`: Размер страницы (default: 50, min: 1, max: 200)
    """,
)
async def get_student_attendance_history(
    iin: str,
    date_from: Optional[str] = Query(None, description="Начало периода (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="Конец периода (YYYY-MM-DD)"),
    page: int = Query(1, ge=1, description="Номер страницы"),
    page_size: int = Query(50, ge=1, le=200, description="Размер страницы"),
    sort_order: str = Query("desc", description="Порядок сортировки: asc или desc"),
    db: AsyncSession = Depends(get_db),
):
    """
    Получить историю посещаемости конкретного студента
    """

    # Получить информацию о студенте
    result = await db.execute(
        select(PlatonusStudent).where(PlatonusStudent.iin == iin)
    )
    student = result.scalars().first()

    if not student:
        raise HTTPException(status_code=404, detail=f"Студент с IIN {iin} не найден")

    # Определить период
    if date_from:
        try:
            start_date = datetime.strptime(date_from, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Неверный формат даты date_from")
    else:
        start_date = date.today() - timedelta(days=30)

    if date_to:
        try:
            end_date = datetime.strptime(date_to, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Неверный формат даты date_to")
    else:
        end_date = date.today()

    # Получить записи посещаемости
    query_params = {
        "iin": iin,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
    }

    count_query = text("""
        SELECT COUNT(*)
        FROM attendance_records
        WHERE iin = :iin
        AND access_date >= :start_date
        AND access_date <= :end_date
    """)

    total_count = await db.scalar(count_query, query_params)
    total_count = total_count or 0

    # Подсчет входов и выходов
    stats_query = text("""
        SELECT
            direction,
            COUNT(*) as cnt,
            MIN(access_date) as first_date,
            MAX(access_date) as last_date
        FROM attendance_records
        WHERE iin = :iin
        AND access_date >= :start_date
        AND access_date <= :end_date
        GROUP BY direction
    """)

    stats_result = await db.execute(stats_query, query_params)
    stats = stats_result.fetchall()

    total_entries = 0
    total_exits = 0
    first_record_date = None
    last_record_date = None

    for row in stats:
        if row[0] == "Вход":
            total_entries = row[1]
            if first_record_date is None or row[2] < first_record_date:
                first_record_date = row[2]
            if last_record_date is None or row[3] > last_record_date:
                last_record_date = row[3]
        elif row[0] == "Выход":
            total_exits = row[1]
            if first_record_date is None or row[2] < first_record_date:
                first_record_date = row[2]
            if last_record_date is None or row[3] > last_record_date:
                last_record_date = row[3]

    # Получить записи с пагинацией
    offset = (page - 1) * page_size
    order_dir = "DESC" if sort_order.lower() == "desc" else "ASC"

    records_query = text(f"""
        SELECT
            id,
            access_datetime,
            access_date,
            access_time,
            direction,
            device_name,
            card_number
        FROM attendance_records
        WHERE iin = :iin
        AND access_date >= :start_date
        AND access_date <= :end_date
        ORDER BY access_datetime {order_dir}
        LIMIT :limit OFFSET :offset
    """)

    query_params["limit"] = page_size
    query_params["offset"] = offset

    records_result = await db.execute(records_query, query_params)
    records = records_result.fetchall()

    # Преобразовать в схемы
    record_items = []
    for record in records:
        access_datetime = record[1]
        if isinstance(access_datetime, str):
            access_datetime = datetime.fromisoformat(access_datetime)

        access_date = record[2]
        if isinstance(access_date, str):
            access_date_str = access_date
        else:
            access_date_str = access_date.isoformat()

        access_time = record[3]
        if isinstance(access_time, str):
            access_time_str = access_time
        else:
            access_time_str = access_time.strftime("%H:%M:%S")

        record_items.append(
            StudentAttendanceHistoryRecord(
                id=record[0],
                access_datetime=access_datetime.isoformat() if access_datetime else None,
                access_date=access_date_str,
                access_time=access_time_str,
                direction=record[4],
                device_name=record[5],
                card_number=record[6],
            )
        )

    total_pages = (total_count + page_size - 1) // page_size

    return StudentAttendanceHistory(
        iin=student.iin,
        firstname=student.firstname,
        lastname=student.lastname,
        patronymic=student.patronymic,
        student_type=student.student_type,
        student_group=student.student_group_name,
        student_group_id=student.student_group_id,
        specialization=student.specialization_name,
        specialization_id=student.specialization_id,
        total_records=total_count,
        total_entries=total_entries,
        total_exits=total_exits,
        first_record_date=first_record_date if isinstance(first_record_date, str) else (first_record_date.isoformat() if first_record_date else None),
        last_record_date=last_record_date if isinstance(last_record_date, str) else (last_record_date.isoformat() if last_record_date else None),
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        records=record_items,
    )


@router.get(
    "/specializations",
    response_model=SpecializationListResponse,
    summary="Список специальностей",
    description="""
    Получить список специальностей/ОП с количеством студентов.
    """,
)
async def get_specializations(db: AsyncSession = Depends(get_db)):
    """
    Получить список специальностей
    """

    query = text("""
        SELECT
            specialization_id,
            specialization_code,
            specialization_name,
            COUNT(*) as student_count
        FROM platonus_students
        WHERE specialization_id IS NOT NULL
        GROUP BY specialization_id, specialization_code, specialization_name
        ORDER BY student_count DESC
    """)

    result = await db.execute(query)
    rows = result.fetchall()

    items = [
        Specialization(
            specialization_id=row[0],
            specialization_code=row[1],
            specialization_name=row[2] or "Без названия",
            student_count=row[3],
        )
        for row in rows
    ]

    return SpecializationListResponse(
        total=len(items),
        items=items,
    )


@router.get(
    "/groups",
    response_model=StudentGroupListResponse,
    summary="Список студенческих групп",
    description="""
    Получить список студенческих групп с количеством студентов.

    **Фильтры:**
    - `specialization_id`: ID специальности

    **Пагинация:**
    - `page`: Номер страницы (default: 1, min: 1)
    - `page_size`: Размер страницы (default: 20, min: 10, max: 100)
    """,
)
async def get_student_groups(
    specialization_id: Optional[int] = Query(None, description="ID специальности"),
    page: int = Query(1, ge=1, description="Номер страницы"),
    page_size: int = Query(20, ge=10, le=100, description="Размер страницы"),
    db: AsyncSession = Depends(get_db),
):
    """
    Получить список студенческих групп
    """

    base_query = """
        SELECT
            student_group_id,
            student_group_name,
            specialization_id,
            specialization_name,
            COUNT(*) as student_count
        FROM platonus_students
        WHERE student_group_id IS NOT NULL
    """

    params = {}

    if specialization_id is not None:
        base_query += " AND specialization_id = :specialization_id"
        params["specialization_id"] = specialization_id

    base_query += """
        GROUP BY student_group_id, student_group_name, specialization_id, specialization_name
        ORDER BY student_count DESC
    """

    result = await db.execute(text(base_query), params)
    rows = result.fetchall()

    # Пагинация
    total = len(rows)
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    paginated_rows = rows[start_idx:end_idx]

    total_pages = (total + page_size - 1) // page_size

    items = [
        StudentGroup(
            student_group_id=row[0],
            student_group_name=row[1] or "Без названия",
            specialization_id=row[2],
            specialization_name=row[3],
            student_count=row[4],
        )
        for row in paginated_rows
    ]

    return StudentGroupListResponse(
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        items=items,
    )
