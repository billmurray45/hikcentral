"""
Pydantic схемы для работы с AttendanceRecord
"""

from datetime import datetime, date, time
from typing import Optional
from pydantic import BaseModel, Field, field_validator


# ==========================================
# Схемы для API Response
# ==========================================


class AttendanceRecordResponse(BaseModel):
    """
    Полная информация о записи прохода
    GET /api/v1/attendance/{id}
    """

    id: int

    # Данные о человеке
    employee_id: str = Field(..., description="ID сотрудника")
    person_name: str = Field(..., description="Полное имя")
    first_name: Optional[str] = Field(None, description="Имя")
    last_name: Optional[str] = Field(None, description="Фамилия")
    patronymic: Optional[str] = Field(None, description="Отчество")
    iin: Optional[str] = Field(None, description="ИИН")

    # Тип и принадлежность
    position: Optional[str] = Field(None, description="Должность/Специальность")
    position1: Optional[str] = Field(None, description="Дополнительная позиция")
    person_group: Optional[str] = Field(None, description="Группа/Иерархия")
    person_type: str = Field(..., description="Тип: student_yu, student_yc, teacher, employee, bachelor, master, other")

    # Извлеченные данные
    faculty: Optional[str] = Field(None, description="Факультет")
    department: Optional[str] = Field(None, description="Кафедра/Отдел")
    group_name: Optional[str] = Field(None, description="Группа студента")

    # Данные о проходе
    access_datetime: str = Field(..., description="Дата и время прохода")
    access_date: str = Field(..., description="Дата прохода")
    access_time: str = Field(..., description="Время прохода")
    direction: Optional[str] = Field(None, description="Направление: Вход или Выход")
    is_entry: bool = Field(..., description="Это вход?")
    is_exit: bool = Field(..., description="Это выход?")

    # Устройство
    device_name: Optional[str] = Field(None, description="Название устройства")
    resource_name: Optional[str] = Field(None, description="Название ресурса")
    card_number: Optional[str] = Field(None, description="Номер карты")

    # Аутентификация
    auth_result: Optional[str] = Field(None, description="Результат аутентификации")
    auth_type: Optional[str] = Field(None, description="Тип аутентификации")

    # Метаданные
    created_at: Optional[datetime] = Field(None, description="Время создания записи")

    class Config:
        from_attributes = True


class AttendanceRecordShort(BaseModel):
    """
    Краткая информация о проходе (для списков)
    GET /api/v1/attendance
    """

    id: int
    employee_id: str
    person_name: str
    iin: Optional[str] = None
    person_type: str
    access_datetime: str
    access_date: str
    access_time: str
    direction: Optional[str] = None
    device_name: Optional[str] = None

    class Config:
        from_attributes = True


class AttendanceListResponse(BaseModel):
    """
    Список записей с пагинацией
    GET /api/v1/attendance
    """

    total: int = Field(..., description="Общее количество записей")
    page: int = Field(..., description="Текущая страница")
    page_size: int = Field(..., description="Размер страницы")
    pages: int = Field(..., description="Всего страниц")
    items: list[AttendanceRecordShort] = Field(default_factory=list, description="Список записей")


# ==========================================
# Фильтры для запросов
# ==========================================


class AttendanceFilter(BaseModel):
    """
    Параметры фильтрации для записей посещаемости
    GET /api/v1/attendance?date=2025-12-17&type=student_yu
    """

    # Фильтры по дате
    date: Optional[str] = Field(None, description="Дата (YYYY-MM-DD)")
    date_from: Optional[str] = Field(None, description="Дата от (YYYY-MM-DD)")
    date_to: Optional[str] = Field(None, description="Дата до (YYYY-MM-DD)")

    # Фильтры по времени
    time_from: Optional[str] = Field(None, description="Время от (HH:MM:SS)")
    time_to: Optional[str] = Field(None, description="Время до (HH:MM:SS)")

    # Фильтры по типу пользователя
    person_type: Optional[str] = Field(
        None, description="Тип: student_yu, student_yc, teacher, employee, bachelor, master"
    )

    # Фильтры по направлению
    direction: Optional[str] = Field(None, description="Направление: Вход или Выход")

    # Фильтры по организации
    position: Optional[str] = Field(None, description="Поиск по должности")
    person_group: Optional[str] = Field(None, description="Поиск по группе")

    # Фильтр по конкретному человеку
    employee_id: Optional[str] = Field(None, description="ID конкретного сотрудника")
    iin: Optional[str] = Field(None, description="ИИН")

    # Поиск
    search: Optional[str] = Field(None, description="Поиск по имени, ИИН, карте")

    # Устройство
    device_name: Optional[str] = Field(None, description="Название устройства")

    # Пагинация
    page: int = Field(1, ge=1, description="Номер страницы")
    page_size: int = Field(50, ge=1, le=500, description="Размер страницы")

    # Сортировка
    sort_by: str = Field("id", description="Поле для сортировки")
    sort_order: str = Field("desc", description="Порядок: asc или desc")

    @field_validator("sort_order")
    @classmethod
    def validate_sort_order(cls, v):
        if v not in ["asc", "desc"]:
            raise ValueError("sort_order must be 'asc' or 'desc'")
        return v

    @field_validator("direction")
    @classmethod
    def validate_direction(cls, v):
        if v and v not in ["Вход", "Выход"]:
            raise ValueError("direction must be 'Вход' or 'Выход'")
        return v


# ==========================================
# Статистика
# ==========================================


class PersonTypeStats(BaseModel):
    """Статистика по типу пользователя"""

    person_type: str
    count: int


class DirectionStats(BaseModel):
    """Статистика по направлениям"""

    direction: str
    count: int


class HourlyStats(BaseModel):
    """Статистика по часам"""

    hour: str
    count: int


class AttendanceStatsResponse(BaseModel):
    """
    Статистика по посещаемости
    GET /api/v1/attendance/stats
    """

    # Общая статистика
    total_records: int = Field(..., description="Всего записей")
    total_entries: int = Field(..., description="Всего входов")
    total_exits: int = Field(..., description="Всего выходов")
    unique_persons: int = Field(..., description="Уникальных людей")

    # Группировки
    by_type: list[PersonTypeStats] = Field(default_factory=list, description="По типам")
    by_direction: list[DirectionStats] = Field(default_factory=list, description="По направлениям")
    by_hour: Optional[list[HourlyStats]] = Field(None, description="По часам (если указана дата)")

    # Период
    date_from: Optional[str] = Field(None, description="Дата начала периода")
    date_to: Optional[str] = Field(None, description="Дата окончания периода")


# ==========================================
# Данные о персоне (уникальный пользователь)
# ==========================================


class PersonInfo(BaseModel):
    """
    Информация о персоне (уникальный пользователь из attendance_records)
    GET /api/v1/persons/{employee_id}
    """

    employee_id: str
    person_name: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    patronymic: Optional[str] = None
    iin: Optional[str] = None

    # Тип и принадлежность
    person_type: str
    position: Optional[str] = None
    position1: Optional[str] = None
    person_group: Optional[str] = None
    faculty: Optional[str] = None
    department: Optional[str] = None
    group_name: Optional[str] = None

    # Статистика
    total_visits: int = Field(..., description="Всего проходов")
    last_visit: Optional[str] = Field(None, description="Последний проход")


class PersonListResponse(BaseModel):
    """
    Список уникальных персон с пагинацией
    GET /api/v1/persons
    """

    total: int = Field(..., description="Общее количество уникальных персон")
    page: int = Field(..., description="Текущая страница")
    page_size: int = Field(..., description="Размер страницы")
    pages: int = Field(..., description="Всего страниц")
    items: list[PersonInfo] = Field(default_factory=list, description="Список персон")


class PersonFilter(BaseModel):
    """
    Фильтры для поиска персон
    GET /api/v1/persons?type=student_yu
    """

    # Фильтры
    person_type: Optional[str] = Field(None, description="Тип пользователя")
    position: Optional[str] = Field(None, description="Должность")
    person_group: Optional[str] = Field(None, description="Группа")
    search: Optional[str] = Field(None, description="Поиск по имени, ИИН")

    # Пагинация
    page: int = Field(1, ge=1, description="Номер страницы")
    page_size: int = Field(50, ge=1, le=500, description="Размер страницы")

    # Сортировка
    sort_by: str = Field("person_name", description="Поле для сортировки")
    sort_order: str = Field("asc", description="Порядок: asc или desc")

    @field_validator("sort_order")
    @classmethod
    def validate_sort_order(cls, v):
        if v not in ["asc", "desc"]:
            raise ValueError("sort_order must be 'asc' or 'desc'")
        return v


# ==========================================
# Дневной отчет
# ==========================================


class DailyAttendanceSummary(BaseModel):
    """
    Сводка посещаемости за день
    GET /api/v1/attendance/daily-summary?date=2025-12-17
    """

    date: str = Field(..., description="Дата")
    total_entries: int = Field(..., description="Всего входов")
    total_exits: int = Field(..., description="Всего выходов")
    unique_persons: int = Field(..., description="Уникальных людей")

    # Разбивка по типам
    students_yu: int = Field(0, description="Студентов YU")
    students_yc: int = Field(0, description="Студентов YC")
    teachers: int = Field(0, description="Преподавателей")
    employees: int = Field(0, description="Сотрудников")
    other: int = Field(0, description="Прочие")

    # Пиковые часы
    peak_hour: Optional[str] = Field(None, description="Час пик")
    peak_hour_count: Optional[int] = Field(None, description="Количество в час пик")


# ==========================================
# История конкретного человека
# ==========================================


class PersonHistoryResponse(BaseModel):
    """
    История проходов конкретного человека
    GET /api/v1/persons/{employee_id}/history
    """

    person: PersonInfo = Field(..., description="Информация о персоне")
    records: list[AttendanceRecordShort] = Field(default_factory=list, description="Список проходов")
    total: int = Field(..., description="Всего записей")
    page: int = Field(..., description="Текущая страница")
    page_size: int = Field(..., description="Размер страницы")
