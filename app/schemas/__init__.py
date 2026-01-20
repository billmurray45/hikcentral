from .attendance import (
    AttendanceRecordResponse,
    AttendanceRecordShort,
    AttendanceListResponse,
    AttendanceFilter,
    AttendanceStatsResponse,
    PersonInfo,
    PersonListResponse,
    PersonFilter,
    DailyAttendanceSummary,
    PersonHistoryResponse,
    LateArrivalPerson,
    LateArrivalsResponse,
)

from .common import (
    PaginationParams,
    PaginatedResponse,
    SuccessResponse,
    ErrorResponse,
    HealthCheckResponse,
)

from .faculty import (
    FacultyBasic,
    FacultyWithStats,
    FacultyListResponse,
    FacultyStats,
    FacultyFilter,
    DepartmentBasic,
    DepartmentListResponse,
    get_faculty_slug,
    get_faculty_name,
)

from .employees import (
    EmployeeBase,
    EmployeeListResponse,
)

__all__ = [
    # Attendance schemas
    "AttendanceRecordResponse",
    "AttendanceRecordShort",
    "AttendanceListResponse",
    "AttendanceFilter",
    "AttendanceStatsResponse",
    "PersonInfo",
    "PersonListResponse",
    "PersonFilter",
    "DailyAttendanceSummary",
    "PersonHistoryResponse",
    "LateArrivalPerson",
    "LateArrivalsResponse",
    # Common schemas
    "PaginationParams",
    "PaginatedResponse",
    "SuccessResponse",
    "ErrorResponse",
    "HealthCheckResponse",
    # Faculty schemas
    "FacultyBasic",
    "FacultyWithStats",
    "FacultyListResponse",
    "FacultyStats",
    "FacultyFilter",
    "DepartmentBasic",
    "DepartmentListResponse",
    "get_faculty_slug",
    "get_faculty_name",
    # Employee schemas
    "EmployeeBase",
    "EmployeeListResponse",
]
