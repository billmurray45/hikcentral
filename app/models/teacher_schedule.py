from datetime import datetime, time
from sqlalchemy import Column, String, Integer, SmallInteger, Time, DateTime, ForeignKey, CheckConstraint
from sqlalchemy.orm import relationship
from app.core.database import Base


class TeacherSchedule(Base):
    """
    Таблица расписания преподавателей из Platonus
    Денормализованная структура для быстрого доступа
    Синхронизируется раз в день
    """

    __tablename__ = "teacher_schedule"

    # Первичный ключ
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Идентификация преподавателя
    iin = Column(
        String(12),
        ForeignKey("platonus_employees.iin", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
        index=True,
        comment="ИИН преподавателя (связь с platonus_employees)",
    )

    # Информация о занятии
    week_day = Column(
        SmallInteger,
        CheckConstraint("week_day BETWEEN 1 AND 7"),
        nullable=False,
        index=True,
        comment="День недели: 1=Понедельник, 2=Вторник, ..., 7=Воскресенье",
    )
    lesson_number = Column(
        SmallInteger,
        nullable=False,
        comment="ID из lesson_hours (для связи с Platonus, обычно 655-836)",
    )
    lesson_start = Column(Time, nullable=False, comment="Время начала пары (например, 09:00)")
    lesson_finish = Column(Time, nullable=False, comment="Время окончания пары (например, 10:30)")

    # Информация о предмете и группе
    subject_name = Column(String(500), nullable=False, comment="Название предмета")
    group_name = Column(String(200), nullable=False, comment="Название учебной группы")

    # Информация об аудитории
    auditory_number = Column(String(50), nullable=True, comment="Номер аудитории")
    building_number = Column(String(50), nullable=True, comment="Номер корпуса")

    # Учебный год и семестр
    study_year = Column(
        SmallInteger,
        nullable=False,
        index=True,
        comment="Учебный год (например, 2025 для 2025-2026 уч.года)",
    )
    study_term = Column(
        SmallInteger,
        CheckConstraint("study_term IN (1, 2)"),
        nullable=False,
        index=True,
        comment="Семестр: 1 или 2",
    )

    # Связь с Platonus (для отладки и обновлений)
    platonus_lesson_id = Column(
        Integer, nullable=True, comment="ID занятия в Platonus (timetable.lessonID)"
    )
    platonus_study_group_id = Column(
        Integer, nullable=True, comment="ID учебной группы в Platonus (studygroups.studyGroupID)"
    )

    # Метаданные
    synced_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        index=True,
        comment="Дата и время последней синхронизации из Platonus",
    )
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, comment="Дата создания записи")
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, comment="Дата последнего обновления")

    # Relationships
    teacher = relationship("PlatonusEmployee", backref="schedule", lazy="joined")

    # Table args для дополнительных ограничений
    __table_args__ = (
        CheckConstraint("lesson_start < lesson_finish", name="check_lesson_time"),
        {"comment": "Расписание преподавателей из Platonus (денормализованная копия для быстрого доступа)"},
    )

    # Properties для удобного доступа
    @property
    def day_name_ru(self) -> str:
        """Название дня недели на русском"""
        days = {
            1: "Понедельник",
            2: "Вторник",
            3: "Среда",
            4: "Четверг",
            5: "Пятница",
            6: "Суббота",
            7: "Воскресенье",
        }
        return days.get(self.week_day, f"День {self.week_day}")

    @property
    def day_name_en(self) -> str:
        """Название дня недели на английском"""
        days = {
            1: "Monday",
            2: "Tuesday",
            3: "Wednesday",
            4: "Thursday",
            5: "Friday",
            6: "Saturday",
            7: "Sunday",
        }
        return days.get(self.week_day, f"Day {self.week_day}")

    @property
    def time_range(self) -> str:
        """Диапазон времени в формате HH:MM-HH:MM"""
        start_str = self.lesson_start.strftime("%H:%M") if self.lesson_start else ""
        finish_str = self.lesson_finish.strftime("%H:%M") if self.lesson_finish else ""
        return f"{start_str}-{finish_str}"

    @property
    def full_auditory(self) -> str | None:
        """Полное название аудитории в формате Корпус-Аудитория"""
        if self.auditory_number and self.building_number:
            return f"{self.building_number}-{self.auditory_number}"
        return None

    @property
    def academic_period(self) -> str:
        """Учебный период в формате '2025-2026 уч.год, 2 семестр'"""
        return f"{self.study_year}-{self.study_year + 1} уч.год, {self.study_term} семестр"

    def __repr__(self):
        return (
            f"<TeacherSchedule(id={self.id}, iin={self.iin}, "
            f"day={self.day_name_ru}, lesson={self.lesson_number}, "
            f"subject={self.subject_name[:30]}...)>"
        )
