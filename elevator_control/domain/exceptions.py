class NotFoundError(Exception):
    """Сущность не найдена (для маппинга в HTTP 404)."""


class ConflictError(Exception):
    """Конфликт бизнес-правил (для HTTP 409)."""
