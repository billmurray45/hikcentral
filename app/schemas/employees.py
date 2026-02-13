"""
Схемы для сотрудников (employees/tutors из Platonus)
"""

from typing import Optional
from pydantic import BaseModel, Field


class EmployeeBase(BaseModel):
    """Базовая информация о сотруднике"""

    tutor_id: int = Field(..., description="ID преподавателя/сотрудника в Platonus")
    iin: str = Field(..., description="ИИН")
    firstname: str = Field(..., description="Имя")
    lastname: str = Field(..., description="Фамилия")
    patronymic: Optional[str] = Field(None, description="Отчество")
    position: Optional[str] = Field(None, description="Должность")
    position_type: Optional[str] = Field(None, description="Тип должности (преподаватель/руководитель/специалист)")
    cafedra: Optional[str] = Field(None, description="Кафедра (для преподавателей)")
    faculty: Optional[str] = Field(None, description="Факультет (для преподавателей)")
    faculty_id: Optional[int] = Field(None, description="ID факультета")
    subdivision: Optional[str] = Field(None, description="Структурное подразделение (для административного персонала)")
    subdivision_id: Optional[int] = Field(None, description="ID структурного подразделения")
    email: Optional[str] = Field(None, description="Email")
    phone: Optional[str] = Field(None, description="Телефон")


class EmployeeListResponse(BaseModel):
    """Ответ со списком сотрудников"""

    total: int = Field(..., description="Всего сотрудников")
    page: int = Field(..., description="Текущая страница")
    page_size: int = Field(..., description="Размер страницы")
    total_pages: int = Field(..., description="Всего страниц")
    items: list[EmployeeBase] = Field(default_factory=list, description="Список сотрудников")

    class Config:
        from_attributes = True


# ==========================================
# Опоздавшие сотрудники
# ==========================================


class FirstLessonInfo(BaseModel):
    """Информация о первом уроке (для преподавателей)"""

    subject: str = Field(..., description="Название предмета")
    group: str = Field(..., description="Группа")
    time_range: str = Field(..., description="Время урока (HH:MM-HH:MM)")
    auditory: Optional[str] = Field(None, description="Аудитория")


class WorkScheduleRuleInfo(BaseModel):
    """Информация о правиле рабочего времени (для административного персонала)"""

    position_type: Optional[str] = Field(None, description="Тип должности")
    position: Optional[str] = Field(None, description="Должность")
    start_time: str = Field(..., description="Время начала работы (HH:MM:SS)")
    description: Optional[str] = Field(None, description="Описание правила")


class LateEmployeeSummary(BaseModel):
    """Информация об опоздавшем сотруднике"""

    # Данные сотрудника
    iin: str = Field(..., description="ИИН")
    firstname: str = Field(..., description="Имя")
    lastname: str = Field(..., description="Фамилия")
    patronymic: Optional[str] = Field(None, description="Отчество")
    position: Optional[str] = Field(None, description="Должность")
    position_type: Optional[str] = Field(None, description="Тип должности")

    # Структура
    cafedra: Optional[str] = Field(None, description="Кафедра (для преподавателей)")
    faculty: Optional[str] = Field(None, description="Факультет (для преподавателей)")
    faculty_id: Optional[int] = Field(None, description="ID факультета")
    subdivision: Optional[str] = Field(None, description="Подразделение (для административного персонала)")
    subdivision_id: Optional[int] = Field(None, description="ID подразделения")

    # Данные об опоздании
    late_type: str = Field(..., description="Тип опоздания: 'lesson' или 'work_schedule'")
    expected_time: str = Field(..., description="Ожидаемое время (начало урока или работы, HH:MM:SS)")
    first_entry_time: str = Field(..., description="Время первого входа (HH:MM:SS)")
    first_entry_datetime: str = Field(..., description="Дата и время первого входа (ISO)")
    minutes_late: int = Field(..., description="Количество минут опоздания")

    # Детали опоздания
    first_lesson: Optional[FirstLessonInfo] = Field(None, description="Информация о первом уроке (если late_type='lesson')")
    work_schedule_rule: Optional[WorkScheduleRuleInfo] = Field(None, description="Информация о правиле (если late_type='work_schedule')")


class LateEmployeesResponse(BaseModel):
    """Ответ со списком опоздавших сотрудников"""

    date: str = Field(..., description="Дата (YYYY-MM-DD)")
    total_late: int = Field(..., description="Всего опоздавших")
    page: int = Field(..., description="Текущая страница")
    page_size: int = Field(..., description="Размер страницы")
    total_pages: int = Field(..., description="Всего страниц")
    items: list[LateEmployeeSummary] = Field(default_factory=list, description="Список опоздавших сотрудников")


# ==========================================
# Справочники (факультеты, подразделения)
# ==========================================


class PlatonusFaculty(BaseModel):
    """Факультет из Platonus"""

    faculty_id: int = Field(..., description="ID факультета в Platonus")
    faculty_name: str = Field(..., description="Название факультета")
    employee_count: int = Field(..., description="Количество сотрудников")


class PlatonusFacultyListResponse(BaseModel):
    """Список факультетов из Platonus"""

    total: int = Field(..., description="Всего факультетов")
    items: list[PlatonusFaculty] = Field(default_factory=list, description="Список факультетов")


class PlatonusSubdivision(BaseModel):
    """Структурное подразделение из Platonus"""

    subdivision_id: int = Field(..., description="ID подразделения в Platonus")
    subdivision_name: str = Field(..., description="Название подразделения")
    subdivision_type: Optional[int] = Field(None, description="Тип подразделения")
    employee_count: int = Field(..., description="Количество сотрудников")


class PlatonusSubdivisionListResponse(BaseModel):
    """Список структурных подразделений из Platonus"""

    total: int = Field(..., description="Всего подразделений")
    page: int = Field(..., description="Текущая страница")
    page_size: int = Field(..., description="Размер страницы")
    total_pages: int = Field(..., description="Всего страниц")
    items: list[PlatonusSubdivision] = Field(default_factory=list, description="Список подразделений")


# ==========================================
# Статистика по опоздавшим
# ==========================================


class TopLateEmployee(BaseModel):
    """Сотрудник в топе опоздавших"""

    iin: str = Field(..., description="ИИН")
    firstname: str = Field(..., description="Имя")
    lastname: str = Field(..., description="Фамилия")
    patronymic: Optional[str] = Field(None, description="Отчество")
    position: Optional[str] = Field(None, description="Должность")
    position_type: Optional[str] = Field(None, description="Тип должности")

    # Структура
    cafedra: Optional[str] = Field(None, description="Кафедра")
    faculty: Optional[str] = Field(None, description="Факультет")
    faculty_id: Optional[int] = Field(None, description="ID факультета")
    subdivision: Optional[str] = Field(None, description="Подразделение")
    subdivision_id: Optional[int] = Field(None, description="ID подразделения")

    # Статистика
    total_lates: int = Field(..., description="Количество опозданий за период")
    avg_late_minutes: float = Field(..., description="Среднее время опоздания (минуты)")
    max_late_minutes: int = Field(..., description="Максимальное опоздание (минуты)")
    min_late_minutes: int = Field(..., description="Минимальное опоздание (минуты)")


class DivisionLateStats(BaseModel):
    """Статистика опозданий по подразделению/факультету"""

    name: str = Field(..., description="Название подразделения/факультета")
    type: str = Field(..., description="Тип: faculty или subdivision")
    id: Optional[int] = Field(None, description="ID подразделения/факультета")

    total_employees: int = Field(..., description="Всего сотрудников в подразделении")
    total_lates: int = Field(..., description="Всего опозданий за период")
    unique_late_employees: int = Field(..., description="Уникальных опоздавших сотрудников")
    late_percentage: float = Field(..., description="Процент опоздавших от общего числа сотрудников")
    avg_late_minutes: float = Field(..., description="Среднее время опоздания (минуты)")


class DailyLateStats(BaseModel):
    """Статистика опозданий за день"""

    date: str = Field(..., description="Дата (YYYY-MM-DD)")
    day_of_week: str = Field(..., description="День недели (Monday, Tuesday, ...)")
    total_lates: int = Field(..., description="Количество опоздавших")
    avg_late_minutes: float = Field(..., description="Среднее время опоздания (минуты)")


class LateTimeDistribution(BaseModel):
    """Распределение опозданий по времени"""

    range: str = Field(..., description="Диапазон времени (например, '1-15 минут')")
    count: int = Field(..., description="Количество опозданий в этом диапазоне")
    percentage: float = Field(..., description="Процент от общего числа опозданий")


class LateStatisticsResponse(BaseModel):
    """Полная статистика по опоздавшим за период"""

    # Период
    date_from: str = Field(..., description="Начало периода")
    date_to: str = Field(..., description="Конец периода")
    threshold_time: str = Field(..., description="Пороговое время (HH:MM:SS)")

    # Общая информация
    total_working_days: int = Field(..., description="Рабочих дней в периоде")
    total_lates: int = Field(..., description="Всего случаев опозданий")
    unique_late_employees: int = Field(..., description="Уникальных опоздавших сотрудников")

    # Топ опоздавших
    top_late_employees: list[TopLateEmployee] = Field(
        default_factory=list, description="Топ опоздавших сотрудников"
    )

    # Статистика по подразделениям
    by_division: list[DivisionLateStats] = Field(
        default_factory=list, description="Статистика по подразделениям/факультетам"
    )

    # Динамика по дням
    by_day: list[DailyLateStats] = Field(
        default_factory=list, description="Динамика опозданий по дням"
    )

    # Распределение по времени
    time_distribution: list[LateTimeDistribution] = Field(
        default_factory=list, description="Распределение по времени опоздания"
    )


# ==========================================
# История посещаемости конкретного сотрудника
# ==========================================


class EmployeeAttendanceHistoryRecord(BaseModel):
    """Одна запись прохода в истории сотрудника"""

    id: int = Field(..., description="ID записи")
    access_datetime: str = Field(..., description="Дата и время прохода (ISO)")
    access_date: str = Field(..., description="Дата прохода (YYYY-MM-DD)")
    access_time: str = Field(..., description="Время прохода (HH:MM:SS)")
    direction: str = Field(..., description="Направление (Вход/Выход)")
    device_name: Optional[str] = Field(None, description="Название устройства")
    card_number: Optional[str] = Field(None, description="Номер карты")


class EmployeeAttendanceHistory(BaseModel):
    """История посещаемости конкретного сотрудника"""

    # Информация о сотруднике
    iin: str = Field(..., description="ИИН")
    firstname: str = Field(..., description="Имя")
    lastname: str = Field(..., description="Фамилия")
    patronymic: Optional[str] = Field(None, description="Отчество")
    position: Optional[str] = Field(None, description="Должность")
    position_type: Optional[str] = Field(None, description="Тип должности")

    # Структура
    cafedra: Optional[str] = Field(None, description="Кафедра")
    faculty: Optional[str] = Field(None, description="Факультет")
    faculty_id: Optional[int] = Field(None, description="ID факультета")
    subdivision: Optional[str] = Field(None, description="Подразделение")
    subdivision_id: Optional[int] = Field(None, description="ID подразделения")

    # Статистика за период
    total_records: int = Field(..., description="Всего записей за период")
    total_entries: int = Field(..., description="Всего входов")
    total_exits: int = Field(..., description="Всего выходов")
    first_record_date: Optional[str] = Field(None, description="Дата первой записи")
    last_record_date: Optional[str] = Field(None, description="Дата последней записи")

    # Пагинация и записи
    page: int = Field(..., description="Текущая страница")
    page_size: int = Field(..., description="Размер страницы")
    total_pages: int = Field(..., description="Всего страниц")
    records: list[EmployeeAttendanceHistoryRecord] = Field(
        default_factory=list, description="Записи посещаемости"
    )
