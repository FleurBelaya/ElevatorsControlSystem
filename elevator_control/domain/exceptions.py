class NotFoundError(Exception):
    """Сущность не найдена (для маппинга в HTTP 404)."""


class ConflictError(Exception):
    """Конфликт бизнес-правил (для HTTP 409)."""


class UnauthorizedError(Exception):
    """Не авторизован (для маппинга в HTTP 401)."""


class ForbiddenError(Exception):
    """Недостаточно прав (для HTTP 403)."""
