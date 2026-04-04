from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Загрузка настроек из переменных окружения и файла .env в корне проекта."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Подключение к PostgreSQL. Впишите свои USER, PASSWORD, хост и имя БД в .env
    database_url: str = "postgresql+psycopg://user:password@localhost:5432/elevator_control"

    simulation_interval_seconds: float = 4.0


settings = Settings()
