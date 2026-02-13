"""
Схемы для расписания преподавателей (teacher_schedule)
"""

from typing import Optional
from pydantic import BaseModel, Field


# ==========================================
# Базовые схемы
# ==========================================


class TeacherScheduleBase(BaseModel):
    """Базовая информация об одном занятии в расписании"""

    id: int = Field(..., description="ID записи")
    iin: str = Field(..., description="ИИН преподавателя")
    week_day: int = Field(..., description="День недели (1-7, где 1=Понедельник)")
    day_name_ru: str = Field(..., description="Название дня недели на русском")
    day_name_en: str = Field(..., description="Название дня недели на английском")
    lesson_number: int = Field(..., description="Номер пары (1-10)")
    lesson_start: str = Field(..., description="Время начала пары (HH:MM)")
    lesson_finish: str = Field(..., description="Время окончания пары (HH:MM)")
    time_range: str = Field(..., description="Диапазон времени (HH:MM-HH:MM)")
    subject_name: str = Field(..., description="Название предмета")
    group_name: str = Field(..., description="Название учебной группы")
    auditory_number: Optional[str] = Field(None, description="Номер аудитории")
    building_number: Optional[str] = Field(None, description="Номер корпуса")
    full_auditory: Optional[str] = Field(None, description="Полное название аудитории (Корпус-Аудитория)")
    study_year: int = Field(..., description="Учебный год (например, 2025)")
    study_term: int = Field(..., description="Семестр (1 или 2)")
    academic_period: str = Field(..., description="Учебный период (например, '2025-2026 уч.год, 2 семестр')")

    class Config:
        from_attributes = True


class TeacherScheduleWithTeacher(TeacherScheduleBase):
    """Информация о занятии с данными преподавателя"""

    teacher_firstname: str = Field(..., description="Имя преподавателя")
    teacher_lastname: str = Field(..., description="Фамилия преподавателя")
    teacher_patronymic: Optional[str] = Field(None, description="Отчество преподавателя")
    teacher_position: Optional[str] = Field(None, description="Должность преподавателя")
    teacher_cafedra: Optional[str] = Field(None, description="Кафедра преподавателя")
    teacher_faculty: Optional[str] = Field(None, description="Факультет преподавателя")

    class Config:
        from_attributes = True


# ==========================================
# Расписание на день
# ==========================================


class TeacherScheduleDayResponse(BaseModel):
    """Расписание преподавателя на один день недели"""

    iin: str = Field(..., description="ИИН преподавателя")
    week_day: int = Field(..., description="День недели (1-7)")
    day_name_ru: str = Field(..., description="Название дня недели на русском")
    day_name_en: str = Field(..., description="Название дня недели на английском")
    total_lessons: int = Field(..., description="Количество пар в этот день")
    lessons: list[TeacherScheduleBase] = Field(default_factory=list, description="Список занятий в этот день")


# ==========================================
# Расписание на неделю
# ==========================================


class TeacherScheduleWeekResponse(BaseModel):
    """Расписание преподавателя на неделю (сгруппировано по дням)"""

    iin: str = Field(..., description="ИИН преподавателя")
    teacher_firstname: str = Field(..., description="Имя преподавателя")
    teacher_lastname: str = Field(..., description="Фамилия преподавателя")
    teacher_patronymic: Optional[str] = Field(None, description="Отчество преподавателя")
    study_year: int = Field(..., description="Учебный год")
    study_term: int = Field(..., description="Семестр")
    academic_period: str = Field(..., description="Учебный период")
    total_lessons: int = Field(..., description="Всего занятий в неделю")
    working_days: int = Field(..., description="Рабочих дней в неделю")
    schedule_by_day: list[TeacherScheduleDayResponse] = Field(
        default_factory=list, description="Расписание по дням недели"
    )


# ==========================================
# Полное расписание (список всех занятий)
# ==========================================


class TeacherScheduleListResponse(BaseModel):
    """Полный список всех занятий преподавателя"""

    iin: str = Field(..., description="ИИН преподавателя")
    teacher_firstname: str = Field(..., description="Имя преподавателя")
    teacher_lastname: str = Field(..., description="Фамилия преподавателя")
    teacher_patronymic: Optional[str] = Field(None, description="Отчество преподавателя")
    study_year: int = Field(..., description="Учебный год")
    study_term: int = Field(..., description="Семестр")
    academic_period: str = Field(..., description="Учебный период")
    total_lessons: int = Field(..., description="Всего занятий")
    unique_subjects: int = Field(..., description="Уникальных предметов")
    unique_groups: int = Field(..., description="Уникальных групп")
    lessons: list[TeacherScheduleBase] = Field(default_factory=list, description="Список всех занятий")


# ==========================================
# Статистика синхронизации
# ==========================================


class TeacherScheduleSyncStats(BaseModel):
    """Статистика последней синхронизации расписания"""

    total_teachers: int = Field(..., description="Всего преподавателей с расписанием")
    total_lessons: int = Field(..., description="Всего занятий синхронизировано")
    unique_subjects: int = Field(..., description="Уникальных предметов")
    unique_groups: int = Field(..., description="Уникальных групп")
    study_year: int = Field(..., description="Учебный год")
    study_term: int = Field(..., description="Семестр")
    last_sync: Optional[str] = Field(None, description="Дата последней синхронизации (ISO)")
    sync_duration_seconds: Optional[float] = Field(None, description="Длительность последней синхронизации (сек)")


class TeacherScheduleSyncResponse(BaseModel):
    """Ответ на запрос синхронизации расписания"""

    success: bool = Field(..., description="Успешность синхронизации")
    message: str = Field(..., description="Сообщение о результате")
    teachers_synced: int = Field(..., description="Количество преподавателей синхронизировано")
    lessons_synced: int = Field(..., description="Количество занятий синхронизировано")
    duration_seconds: float = Field(..., description="Длительность синхронизации (сек)")
    errors: list[str] = Field(default_factory=list, description="Список ошибок (если были)")


# ==========================================
# Поиск по расписанию
# ==========================================


class TeacherScheduleSearchResult(BaseModel):
    """Результат поиска в расписании"""

    total: int = Field(..., description="Всего найдено занятий")
    teachers_count: int = Field(..., description="Количество преподавателей")
    page: int = Field(..., description="Текущая страница")
    page_size: int = Field(..., description="Размер страницы")
    total_pages: int = Field(..., description="Всего страниц")
    lessons: list[TeacherScheduleWithTeacher] = Field(
        default_factory=list, description="Найденные занятия"
    )


# ==========================================
# Статистика преподавателя
# ==========================================


class TeacherScheduleStatistics(BaseModel):
    """Статистика расписания для конкретного преподавателя"""

    iin: str = Field(..., description="ИИН преподавателя")
    teacher_firstname: str = Field(..., description="Имя преподавателя")
    teacher_lastname: str = Field(..., description="Фамилия преподавателя")
    teacher_patronymic: Optional[str] = Field(None, description="Отчество преподавателя")

    # Общая нагрузка
    total_lessons_per_week: int = Field(..., description="Всего пар в неделю")
    total_hours_per_week: float = Field(..., description="Всего часов в неделю")
    working_days_per_week: int = Field(..., description="Рабочих дней в неделю")

    # Разбивка по дням
    lessons_by_day: dict[str, int] = Field(
        default_factory=dict, description="Количество пар по дням недели"
    )

    # Предметы и группы
    unique_subjects: int = Field(..., description="Уникальных предметов")
    unique_groups: int = Field(..., description="Уникальных групп")
    subjects_list: list[str] = Field(default_factory=list, description="Список предметов")
    groups_list: list[str] = Field(default_factory=list, description="Список групп")

    # Самый загруженный день
    busiest_day: str = Field(..., description="Самый загруженный день недели")
    busiest_day_lessons: int = Field(..., description="Количество пар в самый загруженный день")

    # Время работы
    earliest_lesson_start: str = Field(..., description="Начало первой пары (HH:MM)")
    latest_lesson_finish: str = Field(..., description="Окончание последней пары (HH:MM)")
