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
