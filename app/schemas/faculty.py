"""
Pydantic схемы для работы с факультетами
"""

from typing import Optional
from pydantic import BaseModel, Field


# ==========================================
# MAPPING: Название факультета -> slug
# ==========================================

FACULTY_SLUG_MAP = {
    "Факультет Инжиниринг": "engineering",
    "Факультет Туризм и языки": "tourism",
    "Факультет Науки и технологии": "science",
    "Факультет Образование": "education",
    "Факультет Бизнес и право": "business",
    "Факультет Филология и спорт": "philology-sport",
    "Факультет Филология и  спорт": "philology-sport",  # с двойным пробелом
    "Факультет Педагогика": "pedagogy",
    "Факультет Бизнес и туризм": "business-tourism",
    "Факультет Право и международные отношения": "law",
    "Факультет Морская академия": "marine",
    "Факультет Компьютерные науки и искусственный интеллект": "cs-ai",
    "Факультет Компьютерные науки и  искусственный интеллект": "cs-ai",  # с двойным пробелом
}

# Reverse mapping: slug -> название
SLUG_FACULTY_MAP = {v: k for k, v in FACULTY_SLUG_MAP.items() if "  " not in k}


def get_faculty_slug(faculty_name: str) -> str:
    """
    Получить slug для факультета

    Args:
        faculty_name: Название факультета

    Returns:
        slug или 'other'
    """
    return FACULTY_SLUG_MAP.get(faculty_name, "other")


def get_faculty_name(slug: str) -> str | None:
    """
    Получить название факультета по slug

    Args:
        slug: Slug факультета

    Returns:
        Название факультета или None
    """
    return SLUG_FACULTY_MAP.get(slug)


# ==========================================
# Схемы для API Response
# ==========================================


class FacultyBasic(BaseModel):
    """
    Базовая информация о факультете
    GET /api/v1/faculties
    """

    id: str = Field(..., description="Slug факультета (engineering, tourism, etc.)")
    name: str = Field(..., description="Полное название факультета")
    total_records: int = Field(..., description="Общее количество записей")


class FacultyWithStats(BaseModel):
    """
    Факультет с детальной статистикой
    GET /api/v1/faculties?include_stats=true
    """

    id: str = Field(..., description="Slug факультета")
    name: str = Field(..., description="Полное название факультета")
    total_records: int = Field(..., description="Общее количество записей")
    total_students: int = Field(..., description="Количество студентов")
    total_teachers: int = Field(..., description="Количество преподавателей")
    total_employees: int = Field(..., description="Количество сотрудников")
    total_other: int = Field(..., description="Количество прочих")
    unique_persons: int = Field(..., description="Уникальных персон")
    last_activity: Optional[str] = Field(None, description="Последняя активность")


class FacultyListResponse(BaseModel):
    """
    Список факультетов
    """

    total: int = Field(..., description="Количество факультетов")
    date: Optional[str] = Field(None, description="Дата для статистики (если указана)")
    items: list[FacultyBasic | FacultyWithStats] = Field(..., description="Список факультетов")


class FacultyStats(BaseModel):
    """
    Детальная статистика факультета
    GET /api/v1/faculties/{faculty_id}/stats
    """

    id: str = Field(..., description="Slug факультета")
    name: str = Field(..., description="Название факультета")
    date_from: Optional[str] = Field(None, description="Начало периода")
    date_to: Optional[str] = Field(None, description="Конец периода")

    # Общая статистика
    total_entries: int = Field(..., description="Всего входов")
    total_exits: int = Field(..., description="Всего выходов")
    unique_persons: int = Field(..., description="Уникальных персон")

    # По типам
    by_type: dict[str, int] = Field(
        ...,
        description="Распределение по типам",
        example={"students": 850, "teachers": 30, "employees": 10},
    )

    # По дням
    by_day: list[dict[str, int | str]] = Field(
        ..., description="Распределение по дням", example=[{"date": "2025-12-01", "count": 320}]
    )

    # Час пик
    peak_hour: Optional[str] = Field(None, description="Час пик")
    peak_hour_count: int = Field(0, description="Количество проходов в час пик")

    # Средние значения
    avg_daily_visits: float = Field(..., description="Среднее количество визитов в день")


class FacultyFilter(BaseModel):
    """
    Параметры фильтрации для факультетов
    """

    include_stats: bool = Field(False, description="Включить детальную статистику")
    person_type: Optional[str] = Field(None, description="Фильтр по типу пользователя")
    date: Optional[str] = Field(None, description="Дата для статистики")
    sort_by: str = Field("name", description="Поле для сортировки: name, total_records")
    sort_order: str = Field("asc", description="Порядок: asc или desc")


class DepartmentBasic(BaseModel):
    """
    Базовая информация о подразделении (для записей без факультета)
    """

    name: str = Field(..., description="Название подразделения")
    total_records: int = Field(..., description="Количество записей")
    category: str = Field(
        ..., description="Категория: college, marine, administrative, other"
    )


class DepartmentListResponse(BaseModel):
    """
    Список подразделений (для записей без факультета)
    """

    total: int = Field(..., description="Количество подразделений")
    total_records: int = Field(..., description="Общее количество записей")
    items: list[DepartmentBasic] = Field(..., description="Список подразделений")
