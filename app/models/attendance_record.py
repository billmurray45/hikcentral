"""
AttendanceRecord - read-only модель для чтения из hikvision_sync БД
Денормализованная таблица с данными о проходах (Person + Attendance в одной таблице)
"""

from sqlalchemy import Column, Integer, String, DateTime, Index
from app.core.database import Base


class AttendanceRecord(Base):
    """
    Read-only модель для attendance_records из hikvision_sync БД
    Данные синхронизируются из HikCentral в реальном времени
    """

    __tablename__ = "attendance_records"

    # Primary key
    id = Column(Integer, primary_key=True)

    # Данные о человеке
    employee_id = Column(String(256), index=True, comment="ID сотрудника из HikCentral")
    person_name = Column(String(512), comment="Полное имя")
    first_name = Column(String(256), comment="Имя")
    last_name = Column(String(256), comment="Фамилия")
    patronymic = Column(String(256), comment="Отчество")

    # Тип и принадлежность
    position = Column(String(512), index=True, comment="Должность/Специальность")
    position1 = Column(String(512), index=True, comment="Дополнительная позиция")
    person_group = Column(String(512), comment="Группа/Иерархия (Faculty > Department > Group)")
    iin = Column(String(256), index=True, comment="ИИН (12 цифр)")

    # Данные о проходе
    access_datetime = Column(String(256), comment="Дата и время прохода (ISO формат)")
    access_date = Column(String(256), index=True, comment="Дата прохода (YYYY-MM-DD)")
    access_time = Column(String(256), comment="Время прохода (HH:MM:SS)")
    direction = Column(String(256), index=True, comment="Направление: Вход или Выход")

    # Аутентификация
    auth_result = Column(String(256), comment="Результат аутентификации (Успешно)")
    auth_type = Column(String(256), comment="Тип аутентификации (ACSEventFaceVerifyPass)")
    auth_image_url = Column(String(1024), comment="URL фото при проходе")
    card_number = Column(String(256), comment="Номер карты")

    # Устройство
    device_name = Column(String(512), comment="Название устройства")
    device_serial = Column(String(256), comment="Серийный номер устройства")
    resource_name = Column(String(512), comment="Название ресурса")
    reader_name = Column(String(512), comment="Название считывателя")

    # Дополнительные данные
    temperature = Column(String(256), comment="Температура")
    temperature_status = Column(String(256), comment="Статус температуры")
    mask_status = Column(String(256), comment="Статус маски")
    attendance_status = Column(String(256), comment="Статус посещаемости")

    # Метаданные
    created_at = Column(DateTime(timezone=True), comment="Время создания записи")
    synced_at = Column(DateTime(timezone=True), comment="Время синхронизации")

    # Индексы для производительности
    __table_args__ = (
        Index("idx_employee_date", "employee_id", "access_date"),  # Записи конкретного человека за день
        Index("idx_date_direction", "access_date", "direction"),  # Входы/выходы за день
        Index("idx_position_date", "position", "access_date"),  # По типу за день
        Index("idx_created_at", "created_at"),  # Для сортировки по времени создания
    )

    def __repr__(self):
        return f"<AttendanceRecord {self.id}: {self.person_name} - {self.direction} at {self.access_time}>"

    # Helper properties для удобства

    @property
    def is_entry(self) -> bool:
        """Проверка: это вход?"""
        return self.direction == "Вход"

    @property
    def is_exit(self) -> bool:
        """Проверка: это выход?"""
        return self.direction == "Выход"

    @property
    def is_student_yu(self) -> bool:
        """Проверка: студент YU?"""
        return "Студент YU" in (self.position1 or "") or "Студенты YU" in (self.person_group or "")

    @property
    def is_student_yc(self) -> bool:
        """Проверка: студент YC?"""
        return "Студент YC" in (self.position1 or "") or "Обучающиеся YC" in (self.person_group or "")

    @property
    def is_employee(self) -> bool:
        """Проверка: сотрудник?"""
        return "Сотрудники YU" in (self.person_group or "")

    @property
    def person_type(self) -> str:
        """
        Определить тип пользователя

        Returns:
            student_yu, student_yc, bachelor, master, teacher, employee, other
        """
        position1_lower = (self.position1 or "").lower()
        position_lower = (self.position or "").lower()
        person_group_lower = (self.person_group or "").lower()

        # Студенты колледжа
        if "студент yc" in position1_lower or "обучающиеся yc" in person_group_lower:
            return "student_yc"

        # Студенты университета
        if "студент yu" in position1_lower or "студенты yu" in person_group_lower:
            return "student_yu"

        # Бакалавры
        if "бакалавр" in position1_lower:
            return "bachelor"

        # Магистранты
        if "магистрант" in position1_lower or "магистратура" in person_group_lower:
            return "master"

        # Преподаватели и сотрудники
        if "сотрудники yu" in person_group_lower:
            if any(
                word in position_lower
                for word in ["преподаватель", "профессор", "доцент", "ассистент", "лектор"]
            ):
                return "teacher"
            return "employee"

        return "other"

    @property
    def faculty(self) -> str | None:
        """
        Извлечь факультет из person_group

        Returns:
            Название факультета или None

        Example:
            "Студенты YU > Факультет Инжиниринг > ..." -> "Факультет Инжиниринг"
        """
        if not self.person_group:
            return None

        parts = self.person_group.split(" > ")
        for part in parts:
            if "Факультет" in part or "факультет" in part:
                return part.strip()

        return None

    @property
    def department(self) -> str | None:
        """
        Извлечь отдел/кафедру из person_group

        Returns:
            Название отдела или None

        Example:
            "Сотрудники YU > Факультет > Кафедра Менеджмент" -> "Кафедра Менеджмент"
        """
        if not self.person_group:
            return None

        parts = self.person_group.split(" > ")
        if len(parts) >= 3:
            return parts[-1].strip()

        return None

    @property
    def group_name(self) -> str | None:
        """
        Извлечь название группы (для студентов)

        Returns:
            Название группы или position1

        Example:
            "ТОРА-25-2" или "6B07106 Электроэнергетика 2024"
        """
        if self.is_student_yc or self.is_student_yu:
            # Для студентов YC - position1 содержит группу
            if self.is_student_yc:
                return self.position1

            # Для студентов YU - position содержит специальность
            return self.position

        return None
