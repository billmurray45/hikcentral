"""
Схемы для студентов из Platonus
"""

from typing import Optional
from pydantic import BaseModel, Field


class StudentBase(BaseModel):
    """Базовая информация о студенте"""

    student_id: int = Field(..., description="ID студента в Platonus")
    iin: str = Field(..., description="ИИН")
    firstname: str = Field(..., description="Имя")
    lastname: str = Field(..., description="Фамилия")
    patronymic: Optional[str] = Field(None, description="Отчество")
    student_type: Optional[str] = Field(None, description="Тип студента (student_yu/student_yc/bachelor/master)")
    student_group: Optional[str] = Field(None, description="Название группы")
    student_group_id: Optional[int] = Field(None, description="ID группы")
    specialization: Optional[str] = Field(None, description="Название специальности/ОП")
    specialization_id: Optional[int] = Field(None, description="ID специальности")
    specialization_code: Optional[str] = Field(None, description="Код специальности")
    enrollment_year: Optional[int] = Field(None, description="Год поступления")
    study_year: Optional[int] = Field(None, description="Текущий курс")
    email: Optional[str] = Field(None, description="Email")
    phone: Optional[str] = Field(None, description="Телефон")
    expected_time: Optional[str] = Field(
        None, description="Ожидаемое время первого занятия (HH:MM) или 'Нет занятий'"
    )


class StudentListResponse(BaseModel):
    """Ответ со списком студентов"""

    total: int = Field(..., description="Всего студентов")
    page: int = Field(..., description="Текущая страница")
    page_size: int = Field(..., description="Размер страницы")
    total_pages: int = Field(..., description="Всего страниц")
    items: list[StudentBase] = Field(default_factory=list, description="Список студентов")

    class Config:
        from_attributes = True


# ==========================================
# Опоздавшие студенты
# ==========================================


class FirstLessonStudentInfo(BaseModel):
    """Информация о первом занятии (для студента)"""

    subject: str = Field(..., description="Название предмета")
    teacher: Optional[str] = Field(None, description="Преподаватель")
    time_range: str = Field(..., description="Время занятия (HH:MM-HH:MM)")
    auditory: Optional[str] = Field(None, description="Аудитория")


class LateStudentSummary(BaseModel):
    """Информация об опоздавшем студенте"""

    # Данные студента
    iin: str = Field(..., description="ИИН")
    firstname: str = Field(..., description="Имя")
    lastname: str = Field(..., description="Фамилия")
    patronymic: Optional[str] = Field(None, description="Отчество")
    student_type: Optional[str] = Field(None, description="Тип студента")

    # Структура
    student_group: Optional[str] = Field(None, description="Группа")
    student_group_id: Optional[int] = Field(None, description="ID группы")
    specialization: Optional[str] = Field(None, description="Специальность/ОП")
    specialization_id: Optional[int] = Field(None, description="ID специальности")

    # Данные об опоздании
    expected_time: str = Field(..., description="Ожидаемое время начала занятия (HH:MM:SS)")
    first_entry_time: str = Field(..., description="Время первого входа (HH:MM:SS)")
    first_entry_datetime: str = Field(..., description="Дата и время первого входа (ISO)")
    minutes_late: int = Field(..., description="Количество минут опоздания")

    # Детали опоздания
    first_lesson: Optional[FirstLessonStudentInfo] = Field(
        None, description="Информация о первом занятии"
    )


class LateStudentsResponse(BaseModel):
    """Ответ со списком опоздавших студентов"""

    date: str = Field(..., description="Дата (YYYY-MM-DD)")
    total_late: int = Field(..., description="Всего опоздавших")
    page: int = Field(..., description="Текущая страница")
    page_size: int = Field(..., description="Размер страницы")
    total_pages: int = Field(..., description="Всего страниц")
    items: list[LateStudentSummary] = Field(
        default_factory=list, description="Список опоздавших студентов"
    )


# ==========================================
# Посещаемость студентов
# ==========================================


class StudentAttendanceRecord(BaseModel):
    """Запись прохода студента"""

    id: int = Field(..., description="ID записи")
    access_datetime: str = Field(..., description="Дата и время прохода (ISO)")
    access_time: str = Field(..., description="Время прохода (HH:MM:SS)")
    direction: str = Field(..., description="Направление (Вход/Выход)")
    device_name: Optional[str] = Field(None, description="Название устройства")


class StudentAttendanceSummary(BaseModel):
    """Сводка посещаемости студента за день"""

    iin: str = Field(..., description="ИИН")
    firstname: str = Field(..., description="Имя")
    lastname: str = Field(..., description="Фамилия")
    patronymic: Optional[str] = Field(None, description="Отчество")
    student_type: Optional[str] = Field(None, description="Тип студента")
    student_group: Optional[str] = Field(None, description="Группа")
    specialization: Optional[str] = Field(None, description="Специальность/ОП")
    total_passes: int = Field(..., description="Всего проходов за день")
    first_entry: Optional[str] = Field(None, description="Время первого входа (HH:MM:SS)")
    last_exit: Optional[str] = Field(None, description="Время последнего выхода (HH:MM:SS)")
    passes: list[StudentAttendanceRecord] = Field(
        default_factory=list, description="Все проходы за день"
    )


class StudentAttendanceListResponse(BaseModel):
    """Ответ со списком посещаемости студентов"""

    date: str = Field(..., description="Дата (YYYY-MM-DD)")
    total: int = Field(..., description="Всего студентов с записями")
    page: int = Field(..., description="Текущая страница")
    page_size: int = Field(..., description="Размер страницы")
    total_pages: int = Field(..., description="Всего страниц")
    items: list[StudentAttendanceSummary] = Field(
        default_factory=list, description="Список студентов с посещаемостью"
    )


# ==========================================
# История посещаемости конкретного студента
# ==========================================


class StudentAttendanceHistoryRecord(BaseModel):
    """Одна запись прохода в истории студента"""

    id: int = Field(..., description="ID записи")
    access_datetime: str = Field(..., description="Дата и время прохода (ISO)")
    access_date: str = Field(..., description="Дата прохода (YYYY-MM-DD)")
    access_time: str = Field(..., description="Время прохода (HH:MM:SS)")
    direction: str = Field(..., description="Направление (Вход/Выход)")
    device_name: Optional[str] = Field(None, description="Название устройства")
    card_number: Optional[str] = Field(None, description="Номер карты")


class StudentAttendanceHistory(BaseModel):
    """История посещаемости конкретного студента"""

    # Информация о студенте
    iin: str = Field(..., description="ИИН")
    firstname: str = Field(..., description="Имя")
    lastname: str = Field(..., description="Фамилия")
    patronymic: Optional[str] = Field(None, description="Отчество")
    student_type: Optional[str] = Field(None, description="Тип студента")

    # Структура
    student_group: Optional[str] = Field(None, description="Группа")
    student_group_id: Optional[int] = Field(None, description="ID группы")
    specialization: Optional[str] = Field(None, description="Специальность/ОП")
    specialization_id: Optional[int] = Field(None, description="ID специальности")

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
    records: list[StudentAttendanceHistoryRecord] = Field(
        default_factory=list, description="Записи посещаемости"
    )


# ==========================================
# Справочники (специальности, группы)
# ==========================================


class Specialization(BaseModel):
    """Специальность/ОП из Platonus"""

    specialization_id: int = Field(..., description="ID специальности в Platonus")
    specialization_code: Optional[str] = Field(None, description="Код специальности")
    specialization_name: str = Field(..., description="Название специальности")
    student_count: int = Field(..., description="Количество студентов")


class SpecializationListResponse(BaseModel):
    """Список специальностей из Platonus"""

    total: int = Field(..., description="Всего специальностей")
    items: list[Specialization] = Field(default_factory=list, description="Список специальностей")


class StudentGroup(BaseModel):
    """Студенческая группа"""

    student_group_id: int = Field(..., description="ID группы в Platonus")
    student_group_name: str = Field(..., description="Название группы")
    specialization_id: Optional[int] = Field(None, description="ID специальности")
    specialization_name: Optional[str] = Field(None, description="Название специальности")
    student_count: int = Field(..., description="Количество студентов")


class StudentGroupListResponse(BaseModel):
    """Список студенческих групп"""

    total: int = Field(..., description="Всего групп")
    page: int = Field(..., description="Текущая страница")
    page_size: int = Field(..., description="Размер страницы")
    total_pages: int = Field(..., description="Всего страниц")
    items: list[StudentGroup] = Field(default_factory=list, description="Список групп")


# ==========================================
# Статистика по опоздавшим студентам
# ==========================================


class TopLateStudent(BaseModel):
    """Студент в топе опоздавших"""

    iin: str = Field(..., description="ИИН")
    firstname: str = Field(..., description="Имя")
    lastname: str = Field(..., description="Фамилия")
    patronymic: Optional[str] = Field(None, description="Отчество")
    student_type: Optional[str] = Field(None, description="Тип студента")

    # Структура
    student_group: Optional[str] = Field(None, description="Группа")
    student_group_id: Optional[int] = Field(None, description="ID группы")
    specialization: Optional[str] = Field(None, description="Специальность/ОП")
    specialization_id: Optional[int] = Field(None, description="ID специальности")

    # Статистика
    total_lates: int = Field(..., description="Количество опозданий за период")
    avg_late_minutes: float = Field(..., description="Среднее время опоздания (минуты)")
    max_late_minutes: int = Field(..., description="Максимальное опоздание (минуты)")
    min_late_minutes: int = Field(..., description="Минимальное опоздание (минуты)")


class GroupLateStats(BaseModel):
    """Статистика опозданий по группе"""

    student_group_name: str = Field(..., description="Название группы")
    student_group_id: int = Field(..., description="ID группы")
    specialization_name: Optional[str] = Field(None, description="Специальность")
    specialization_id: Optional[int] = Field(None, description="ID специальности")

    total_students: int = Field(..., description="Всего студентов в группе")
    total_lates: int = Field(..., description="Всего опозданий за период")
    unique_late_students: int = Field(..., description="Уникальных опоздавших студентов")
    late_percentage: float = Field(..., description="Процент опоздавших от общего числа")
    avg_late_minutes: float = Field(..., description="Среднее время опоздания (минуты)")


class DailyStudentLateStats(BaseModel):
    """Статистика опозданий студентов за день"""

    date: str = Field(..., description="Дата (YYYY-MM-DD)")
    day_of_week: str = Field(..., description="День недели (Monday, Tuesday, ...)")
    total_lates: int = Field(..., description="Количество опоздавших")
    avg_late_minutes: float = Field(..., description="Среднее время опоздания (минуты)")


class StudentLateStatisticsResponse(BaseModel):
    """Полная статистика по опоздавшим студентам за период"""

    # Период
    date_from: str = Field(..., description="Начало периода")
    date_to: str = Field(..., description="Конец периода")

    # Общая информация
    total_working_days: int = Field(..., description="Учебных дней в периоде")
    total_lates: int = Field(..., description="Всего случаев опозданий")
    unique_late_students: int = Field(..., description="Уникальных опоздавших студентов")

    # Топ опоздавших
    top_late_students: list[TopLateStudent] = Field(
        default_factory=list, description="Топ опоздавших студентов"
    )

    # Статистика по группам
    by_group: list[GroupLateStats] = Field(
        default_factory=list, description="Статистика по группам"
    )

    # Динамика по дням
    by_day: list[DailyStudentLateStats] = Field(
        default_factory=list, description="Динамика опозданий по дням"
    )
