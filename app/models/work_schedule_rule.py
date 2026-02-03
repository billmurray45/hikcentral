"""
SQLAlchemy модель для правил рабочего времени
"""

from datetime import time, date, datetime
from sqlalchemy import Column, Integer, String, Time, Date, Boolean, Text, TIMESTAMP, CheckConstraint
from sqlalchemy.sql import func

from app.core.database import Base


class WorkScheduleRule(Base):
    """
    Модель правил рабочего времени для разных должностей

    Используется для определения времени начала/окончания работы
    для различных должностей и типов должностей
    """

    __tablename__ = "work_schedule_rules"

    id = Column(Integer, primary_key=True, index=True)

    # Условие применения правила (одно из двух должно быть заполнено)
    position_type = Column(String(100), nullable=True, index=True, comment="Тип должности")
    position = Column(String(255), nullable=True, index=True, comment="Конкретная должность")

    # Дополнительные фильтры (опционально)
    faculty_id = Column(Integer, nullable=True, index=True, comment="ID факультета")
    subdivision_id = Column(Integer, nullable=True, index=True, comment="ID подразделения")

    # Рабочее время
    start_time = Column(Time, nullable=False, comment="Время начала работы (порог опоздания)")
    end_time = Column(Time, nullable=True, comment="Время окончания работы")

    # Дни недели (опционально, NULL = все дни)
    apply_days = Column(String(50), nullable=True, comment="Дни недели (JSON массив)")

    # Период действия правила (опционально)
    valid_from = Column(Date, nullable=True, comment="Дата начала действия")
    valid_to = Column(Date, nullable=True, comment="Дата окончания действия")

    # Приоритет и статус
    priority = Column(Integer, default=0, index=True, comment="Приоритет правила (больше = выше)")
    is_active = Column(Boolean, default=True, index=True, comment="Активно ли правило")

    # Метаданные
    description = Column(Text, nullable=True, comment="Описание правила")
    created_at = Column(TIMESTAMP, server_default=func.now(), comment="Дата создания")
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now(), comment="Дата обновления")
    created_by = Column(String(100), nullable=True, comment="Кто создал правило")

    # Ограничения
    __table_args__ = (
        CheckConstraint(
            "(position_type IS NOT NULL) OR (position IS NOT NULL)",
            name="check_has_condition"
        ),
        CheckConstraint(
            "(valid_from IS NULL) OR (valid_to IS NULL) OR (valid_from <= valid_to)",
            name="check_valid_dates"
        ),
    )

    def __repr__(self):
        condition = self.position_type or self.position or "Unknown"
        return f"<WorkScheduleRule(id={self.id}, condition='{condition}', start={self.start_time}, priority={self.priority})>"

    def to_dict(self):
        """Преобразовать в словарь"""
        return {
            "id": self.id,
            "position_type": self.position_type,
            "position": self.position,
            "faculty_id": self.faculty_id,
            "subdivision_id": self.subdivision_id,
            "start_time": self.start_time.strftime("%H:%M:%S") if self.start_time else None,
            "end_time": self.end_time.strftime("%H:%M:%S") if self.end_time else None,
            "apply_days": self.apply_days,
            "valid_from": self.valid_from.isoformat() if self.valid_from else None,
            "valid_to": self.valid_to.isoformat() if self.valid_to else None,
            "priority": self.priority,
            "is_active": self.is_active,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "created_by": self.created_by,
        }
