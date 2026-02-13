"""
Teacher Schedule API endpoints - получение расписания преподавателей
Данные синхронизируются из Platonus раз в день
"""

from typing import Optional
from fastapi import APIRouter, Query, Depends, HTTPException, BackgroundTasks
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
from collections import defaultdict

from app.schemas import (
    TeacherScheduleBase,
    TeacherScheduleDayResponse,
    TeacherScheduleWeekResponse,
    TeacherScheduleListResponse,
    TeacherScheduleSyncStats,
    TeacherScheduleSyncResponse,
)
from app.models import TeacherSchedule, PlatonusEmployee
from app.api.dependencies import get_db
from app.services.teacher_schedule_sync import TeacherScheduleSyncService

router = APIRouter(prefix="/teachers", tags=["Teacher Schedule"])


@router.get(
    "/{iin}/schedule",
    response_model=TeacherScheduleListResponse,
    summary="Получить полное расписание преподавателя",
    description="""
    Получить полное расписание преподавателя на семестр.

    **Параметры:**
    - `iin`: ИИН преподавателя (12 цифр)
    - `study_year`: Учебный год (default: 2025)
    - `study_term`: Семестр (1 или 2, default: 2)

    **Возвращает:**
    - Полную информацию о преподавателе
    - Список всех занятий
    - Статистику (количество занятий, предметов, групп)
    """,
)
async def get_teacher_schedule(
    iin: str,
    study_year: int = Query(2025, description="Учебный год"),
    study_term: int = Query(2, ge=1, le=2, description="Семестр (1 или 2)"),
    db: AsyncSession = Depends(get_db),
):
    """Получить полное расписание преподавателя"""

    # Проверить существование преподавателя
    teacher_query = select(PlatonusEmployee).where(PlatonusEmployee.iin == iin)
    teacher_result = await db.execute(teacher_query)
    teacher = teacher_result.scalar_one_or_none()

    if not teacher:
        raise HTTPException(status_code=404, detail=f"Преподаватель с ИИН {iin} не найден")

    # Получить расписание
    schedule_query = (
        select(TeacherSchedule)
        .where(
            TeacherSchedule.iin == iin,
            TeacherSchedule.study_year == study_year,
            TeacherSchedule.study_term == study_term,
        )
        .order_by(TeacherSchedule.week_day, TeacherSchedule.lesson_number)
    )

    result = await db.execute(schedule_query)
    lessons = result.scalars().all()

    if not lessons:
        raise HTTPException(
            status_code=404,
            detail=f"Расписание для преподавателя {iin} не найдено (год: {study_year}, семестр: {study_term})"
        )

    # Подсчет уникальных предметов и групп
    unique_subjects = len(set(lesson.subject_name for lesson in lessons))
    unique_groups = len(set(lesson.group_name for lesson in lessons))

    # Преобразовать в Pydantic модели
    lessons_response = [
        TeacherScheduleBase(
            id=lesson.id,
            iin=lesson.iin,
            week_day=lesson.week_day,
            day_name_ru=lesson.day_name_ru,
            day_name_en=lesson.day_name_en,
            lesson_number=lesson.lesson_number,
            lesson_start=lesson.lesson_start.strftime("%H:%M"),
            lesson_finish=lesson.lesson_finish.strftime("%H:%M"),
            time_range=lesson.time_range,
            subject_name=lesson.subject_name,
            group_name=lesson.group_name,
            auditory_number=lesson.auditory_number,
            building_number=lesson.building_number,
            full_auditory=lesson.full_auditory,
            study_year=lesson.study_year,
            study_term=lesson.study_term,
            academic_period=lesson.academic_period,
        )
        for lesson in lessons
    ]

    return TeacherScheduleListResponse(
        iin=iin,
        teacher_firstname=teacher.firstname,
        teacher_lastname=teacher.lastname,
        teacher_patronymic=teacher.patronymic,
        study_year=study_year,
        study_term=study_term,
        academic_period=lessons[0].academic_period,
        total_lessons=len(lessons),
        unique_subjects=unique_subjects,
        unique_groups=unique_groups,
        lessons=lessons_response,
    )


@router.get(
    "/{iin}/schedule/week",
    response_model=TeacherScheduleWeekResponse,
    summary="Получить недельное расписание преподавателя",
    description="""
    Получить расписание преподавателя на неделю, сгруппированное по дням.

    **Параметры:**
    - `iin`: ИИН преподавателя (12 цифр)
    - `study_year`: Учебный год (default: 2025)
    - `study_term`: Семестр (1 или 2, default: 2)

    **Возвращает:**
    - Информацию о преподавателе
    - Расписание по дням недели
    - Статистику (количество занятий, рабочих дней)
    """,
)
async def get_teacher_schedule_week(
    iin: str,
    study_year: int = Query(2025, description="Учебный год"),
    study_term: int = Query(2, ge=1, le=2, description="Семестр (1 или 2)"),
    db: AsyncSession = Depends(get_db),
):
    """Получить недельное расписание преподавателя, сгруппированное по дням"""

    # Проверить существование преподавателя
    teacher_query = select(PlatonusEmployee).where(PlatonusEmployee.iin == iin)
    teacher_result = await db.execute(teacher_query)
    teacher = teacher_result.scalar_one_or_none()

    if not teacher:
        raise HTTPException(status_code=404, detail=f"Преподаватель с ИИН {iin} не найден")

    # Получить расписание
    schedule_query = (
        select(TeacherSchedule)
        .where(
            TeacherSchedule.iin == iin,
            TeacherSchedule.study_year == study_year,
            TeacherSchedule.study_term == study_term,
        )
        .order_by(TeacherSchedule.week_day, TeacherSchedule.lesson_number)
    )

    result = await db.execute(schedule_query)
    lessons = result.scalars().all()

    if not lessons:
        raise HTTPException(
            status_code=404,
            detail=f"Расписание для преподавателя {iin} не найдено (год: {study_year}, семестр: {study_term})"
        )

    # Группировать по дням
    lessons_by_day = defaultdict(list)
    for lesson in lessons:
        lessons_by_day[lesson.week_day].append(lesson)

    # Создать ответ по дням
    schedule_by_day = []
    for day in sorted(lessons_by_day.keys()):
        day_lessons = lessons_by_day[day]
        day_response = TeacherScheduleDayResponse(
            iin=iin,
            week_day=day,
            day_name_ru=day_lessons[0].day_name_ru,
            day_name_en=day_lessons[0].day_name_en,
            total_lessons=len(day_lessons),
            lessons=[
                TeacherScheduleBase(
                    id=lesson.id,
                    iin=lesson.iin,
                    week_day=lesson.week_day,
                    day_name_ru=lesson.day_name_ru,
                    day_name_en=lesson.day_name_en,
                    lesson_number=lesson.lesson_number,
                    lesson_start=lesson.lesson_start.strftime("%H:%M"),
                    lesson_finish=lesson.lesson_finish.strftime("%H:%M"),
                    time_range=lesson.time_range,
                    subject_name=lesson.subject_name,
                    group_name=lesson.group_name,
                    auditory_number=lesson.auditory_number,
                    building_number=lesson.building_number,
                    full_auditory=lesson.full_auditory,
                    study_year=lesson.study_year,
                    study_term=lesson.study_term,
                    academic_period=lesson.academic_period,
                )
                for lesson in day_lessons
            ],
        )
        schedule_by_day.append(day_response)

    return TeacherScheduleWeekResponse(
        iin=iin,
        teacher_firstname=teacher.firstname,
        teacher_lastname=teacher.lastname,
        teacher_patronymic=teacher.patronymic,
        study_year=study_year,
        study_term=study_term,
        academic_period=lessons[0].academic_period,
        total_lessons=len(lessons),
        working_days=len(lessons_by_day),
        schedule_by_day=schedule_by_day,
    )


@router.get(
    "/{iin}/schedule/day/{day}",
    response_model=TeacherScheduleDayResponse,
    summary="Получить расписание преподавателя на один день",
    description="""
    Получить расписание преподавателя на конкретный день недели.

    **Параметры:**
    - `iin`: ИИН преподавателя (12 цифр)
    - `day`: День недели (1-7, где 1=Понедельник, 7=Воскресенье)
    - `study_year`: Учебный год (default: 2025)
    - `study_term`: Семестр (1 или 2, default: 2)

    **Возвращает:**
    - Расписание на указанный день
    - Количество пар
    """,
)
async def get_teacher_schedule_day(
    iin: str,
    day: int,
    study_year: int = Query(2025, description="Учебный год"),
    study_term: int = Query(2, ge=1, le=2, description="Семестр (1 или 2)"),
    db: AsyncSession = Depends(get_db),
):
    """Получить расписание преподавателя на конкретный день"""

    if day < 1 or day > 7:
        raise HTTPException(status_code=400, detail="День недели должен быть от 1 до 7")

    # Получить расписание на день
    schedule_query = (
        select(TeacherSchedule)
        .where(
            TeacherSchedule.iin == iin,
            TeacherSchedule.week_day == day,
            TeacherSchedule.study_year == study_year,
            TeacherSchedule.study_term == study_term,
        )
        .order_by(TeacherSchedule.lesson_number)
    )

    result = await db.execute(schedule_query)
    lessons = result.scalars().all()

    if not lessons:
        raise HTTPException(
            status_code=404,
            detail=f"Расписание для преподавателя {iin} на день {day} не найдено"
        )

    return TeacherScheduleDayResponse(
        iin=iin,
        week_day=day,
        day_name_ru=lessons[0].day_name_ru,
        day_name_en=lessons[0].day_name_en,
        total_lessons=len(lessons),
        lessons=[
            TeacherScheduleBase(
                id=lesson.id,
                iin=lesson.iin,
                week_day=lesson.week_day,
                day_name_ru=lesson.day_name_ru,
                day_name_en=lesson.day_name_en,
                lesson_number=lesson.lesson_number,
                lesson_start=lesson.lesson_start.strftime("%H:%M"),
                lesson_finish=lesson.lesson_finish.strftime("%H:%M"),
                time_range=lesson.time_range,
                subject_name=lesson.subject_name,
                group_name=lesson.group_name,
                auditory_number=lesson.auditory_number,
                building_number=lesson.building_number,
                full_auditory=lesson.full_auditory,
                study_year=lesson.study_year,
                study_term=lesson.study_term,
                academic_period=lesson.academic_period,
            )
            for lesson in lessons
        ],
    )


@router.post(
    "/schedule/sync",
    response_model=TeacherScheduleSyncResponse,
    summary="Синхронизировать расписание из Platonus",
    description="""
    Запустить синхронизацию расписания преподавателей из Platonus.

    **Параметры:**
    - `study_year`: Учебный год для синхронизации (default: 2025)
    - `study_term`: Семестр для синхронизации (1 или 2, default: 2)
    - `background`: Запустить в фоне (default: false)

    **Процесс:**
    1. Подключение к Platonus через SSH туннель
    2. Получение расписания для всех преподавателей
    3. Удаление старых данных для указанного года/семестра
    4. Вставка новых данных

    **Примечание:** Синхронизация может занять 5-10 минут для ~365 преподавателей.
    """,
)
async def sync_teacher_schedules(
    background_tasks: BackgroundTasks,
    study_year: int = Query(2025, description="Учебный год"),
    study_term: int = Query(2, ge=1, le=2, description="Семестр (1 или 2)"),
    background: bool = Query(False, description="Запустить в фоне"),
    db: AsyncSession = Depends(get_db),
):
    """Синхронизировать расписание из Platonus"""

    sync_service = TeacherScheduleSyncService(db)

    if background:
        # Запустить в фоне
        background_tasks.add_task(sync_service.sync_schedules, study_year, study_term)
        return TeacherScheduleSyncResponse(
            success=True,
            message="Синхронизация запущена в фоне",
            teachers_synced=0,
            lessons_synced=0,
            duration_seconds=0,
            errors=[],
        )
    else:
        # Синхронная синхронизация
        try:
            result = await sync_service.sync_schedules(study_year, study_term)
            return TeacherScheduleSyncResponse(
                success=True,
                message=result["message"],
                teachers_synced=result["teachers_synced"],
                lessons_synced=result["lessons_synced"],
                duration_seconds=result["duration_seconds"],
                errors=result.get("errors", []),
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Ошибка синхронизации: {str(e)}")


@router.get(
    "/schedule/sync/stats",
    response_model=TeacherScheduleSyncStats,
    summary="Получить статистику синхронизации",
    description="""
    Получить статистику последней синхронизации расписания.

    **Параметры:**
    - `study_year`: Учебный год (default: 2025)
    - `study_term`: Семестр (1 или 2, default: 2)

    **Возвращает:**
    - Количество преподавателей с расписанием
    - Количество занятий
    - Количество уникальных предметов и групп
    - Дату последней синхронизации
    """,
)
async def get_sync_stats(
    study_year: int = Query(2025, description="Учебный год"),
    study_term: int = Query(2, ge=1, le=2, description="Семестр (1 или 2)"),
    db: AsyncSession = Depends(get_db),
):
    """Получить статистику синхронизации"""

    sync_service = TeacherScheduleSyncService(db)
    stats = await sync_service.get_sync_stats(study_year, study_term)

    return TeacherScheduleSyncStats(
        total_teachers=stats["total_teachers"],
        total_lessons=stats["total_lessons"],
        unique_subjects=stats["unique_subjects"],
        unique_groups=stats["unique_groups"],
        study_year=stats["study_year"],
        study_term=stats["study_term"],
        last_sync=stats["last_sync"],
        sync_duration_seconds=None,  # Пока не отслеживаем
    )
