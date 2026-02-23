from datetime import datetime
from sqlalchemy import Column, String, Integer, SmallInteger, DateTime
from app.core.database import Base


class PlatonusStudent(Base):
    """
    Таблица с данными студентов из Platonus
    Синхронизируется раз в неделю
    """

    __tablename__ = "platonus_students"

    # Первичный ключ - IIN
    iin = Column(String(12), primary_key=True, index=True, comment="ИИН студента")

    # Данные из Platonus
    student_id = Column(Integer, nullable=False, comment="ID в таблице students (Platonus)")
    firstname = Column(String(128), nullable=False, comment="Имя")
    lastname = Column(String(128), nullable=False, comment="Фамилия")
    patronymic = Column(String(128), nullable=True, comment="Отчество")

    # Тип студента (определяется по HikCentral)
    student_type = Column(
        String(50),
        nullable=True,
        index=True,
        comment="Тип студента (student_yu/student_yc/bachelor/master)",
    )

    # Академическая структура
    student_group_id = Column(Integer, nullable=True, index=True, comment="ID группы в Platonus")
    student_group_name = Column(String(256), nullable=True, comment="Название группы (например, ТОРА-25-2)")
    specialization_id = Column(Integer, nullable=True, index=True, comment="ID специальности/ОП")
    specialization_code = Column(String(50), nullable=True, comment="Код специальности (например, 6B07106)")
    specialization_name = Column(String(500), nullable=True, comment="Название специальности/ОП")

    # Курс и год поступления
    enrollment_year = Column(Integer, nullable=True, comment="Год поступления")
    study_year = Column(SmallInteger, nullable=True, comment="Текущий курс (1, 2, 3, 4)")

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

    @property
    def full_name(self) -> str:
        """Полное имя студента"""
        parts = [self.lastname, self.firstname]
        if self.patronymic:
            parts.append(self.patronymic)
        return " ".join(parts)

    @property
    def student_type_display(self) -> str:
        """Отображаемое название типа студента"""
        types = {
            "student_yu": "Студент YU",
            "student_yc": "Студент YC",
            "bachelor": "Бакалавр",
            "master": "Магистрант",
        }
        return types.get(self.student_type, self.student_type or "Неизвестно")

    def __repr__(self):
        return f"<PlatonusStudent(iin={self.iin}, name={self.full_name}, group={self.student_group_name})>"
