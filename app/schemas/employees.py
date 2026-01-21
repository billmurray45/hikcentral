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
    items: list[EmployeeBase] = Field(default_factory=list, description="Список сотрудников")

    class Config:
        from_attributes = True


# ==========================================
# Опоздавшие сотрудники
# ==========================================


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
    first_entry_time: str = Field(..., description="Время первого входа (HH:MM:SS)")
    first_entry_datetime: str = Field(..., description="Дата и время первого входа (ISO)")
    minutes_late: int = Field(..., description="Количество минут опоздания")


class LateEmployeesResponse(BaseModel):
    """Ответ со списком опоздавших сотрудников"""

    date: str = Field(..., description="Дата (YYYY-MM-DD)")
    threshold_time: str = Field(..., description="Пороговое время (HH:MM:SS)")
    total_late: int = Field(..., description="Всего опоздавших")
    items: list[LateEmployeeSummary] = Field(default_factory=list, description="Список опоздавших сотрудников")
