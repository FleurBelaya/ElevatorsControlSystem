from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Загрузка настроек из переменных окружения и файла .env в корне проекта."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Для Alembic и синхронных утилит: postgresql+psycopg://...
    # Рантайм API использует asyncpg (см. database_url_async).
    database_url: str = "postgresql+psycopg://user:password@localhost:5432/elevator_control"

    simulation_interval_seconds: float = 4.0

    # 2.1 Авторизация RBAC + 6.2 JWT
    jwt_secret_key: str = "CHANGE_ME"
    # 6.2.1 Срок жизни access-токена: короткий, ~15 минут.
    access_token_ttl_seconds: int = 15 * 60
    # 6.2.2 Refresh-токен: дольше, ~7 суток.
    refresh_token_ttl_seconds: int = 7 * 24 * 60 * 60

    # 3.2 / регистрация второго и более администратора через общий код
    registration_admin_code: str | None = Field(
        default=None, validation_alias="ELEVATOR_REGISTRATION_ADMIN_CODE"
    )

    # 2.5.2 - Интеграция очереди: настройки Celery
    celery_broker_url: str = "filesystem://"
    celery_result_backend: str = "db+sqlite:///celery_results.db"

    # 6.3.4 CORS: только разрешённые домены. Список через запятую в .env.
    # По умолчанию — локальные адреса разработчика и сборки клиентов.
    cors_allowed_origins: str = (
        "http://localhost:8000,http://127.0.0.1:8000,"
        "http://localhost:3000,http://127.0.0.1:3000,"
        "http://localhost:5173,http://127.0.0.1:5173"
    )

    # 6.3.1 Rate limiting: лимиты на минуту и на 10 секунд.
    rate_limit_per_minute: int = 120
    rate_limit_burst_per_10s: int = 30

    # 4.4 Eventual Consistency: задержка обработки доменных событий воркером.
    cqrs_event_delay_seconds: int = 2

    @property
    def cors_allowed_origins_list(self) -> list[str]:
        # 6.3.4 CORS whitelist: парсим строку из переменной окружения.
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

    @property
    def database_url_async(self) -> str:
        """URL для SQLAlchemy AsyncEngine (драйвер asyncpg)."""
        url = self.database_url.strip()
        if "+asyncpg" in url:
            return url
        if url.startswith("postgresql+psycopg://"):
            return url.replace("postgresql+psycopg://", "postgresql+asyncpg://", 1)
        if url.startswith("postgresql://"):
            return "postgresql+asyncpg://" + url.removeprefix("postgresql://")
        raise ValueError(
            "database_url должен начинаться с postgresql+psycopg:// или postgresql:// "
            "(для миграций); для приложения он будет преобразован в asyncpg."
        )


settings = Settings()
