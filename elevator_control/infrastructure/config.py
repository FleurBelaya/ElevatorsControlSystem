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

    # 2.1 Авторизация RBAC
    jwt_secret_key: str = "CHANGE_ME"
    access_token_ttl_seconds: int = 60 * 60

    # 2.5.2 - Интеграция очереди: настройки Celery
    # По умолчанию используется файловый брокер (SQLite/filesystem) — работает
    # без установки Redis/RabbitMQ. Для продакшена замените на redis://localhost:6379/0
    celery_broker_url: str = "filesystem://"
    celery_result_backend: str = "db+sqlite:///celery_results.db"

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
