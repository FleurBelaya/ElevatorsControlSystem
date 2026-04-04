from enum import Enum


class LiftStatus(str, Enum):
    ACTIVE = "active"
    STOPPED = "stopped"
    MAINTENANCE = "maintenance"


class EventType(str, Enum):
    WARNING = "warning"
    CRITICAL = "critical"


class EventStatus(str, Enum):
    NEW = "new"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"


class ServiceRequestStatus(str, Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TechnicianStatus(str, Enum):
    FREE = "free"
    BUSY = "busy"
