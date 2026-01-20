"""
Модель для кеширования данных сотрудников из Platonus
"""

from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime
from app.core.database import Base


class PlatonusEmployee(Base):
    """
    Таблица с данными сотрудников из Platonus
    Синхронизируется раз в неделю
    """

    __tablename__ = "platonus_employees"

    # Первичный ключ - IIN
    iin = Column(String(12), primary_key=True, index=True, comment="ИИН сотрудника")

    # Данные из Platonus
    tutor_id = Column(Integer, nullable=False, comment="ID в таблице tutors (Platonus)")
    firstname = Column(String(128), nullable=False, comment="Имя")
    lastname = Column(String(128), nullable=False, comment="Фамилия")
    patronymic = Column(String(128), nullable=True, comment="Отчество")

    # Должность
    position = Column(String(256), nullable=True, comment="Должность")
    position_type = Column(
        String(50), nullable=True, comment="Тип должности (Преподаватель/Руководитель/и т.д.)"
    )

    # Структура (для преподавателей)
    cafedra_id = Column(Integer, nullable=True, comment="ID кафедры")
    cafedra_name = Column(String(256), nullable=True, comment="Название кафедры")
    faculty_id = Column(Integer, nullable=True, comment="ID факультета")
    faculty_name = Column(String(256), nullable=True, comment="Название факультета")

    # Структурное подразделение (для административного персонала)
    subdivision_id = Column(Integer, nullable=True, comment="ID структурного подразделения")
    subdivision_name = Column(String(256), nullable=True, comment="Название подразделения")
    subdivision_type = Column(Integer, nullable=True, comment="Тип подразделения")

    # Контакты
    email = Column(String(512), nullable=True, comment="Email")
    phone = Column(String(128), nullable=True, comment="Телефон")

    # Служебные поля
    synced_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, comment="Дата последней синхронизации"
    )
    created_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, comment="Дата создания записи"
    )

    def __repr__(self):
        return f"<PlatonusEmployee(iin={self.iin}, name={self.firstname} {self.lastname}, position={self.position})>"
