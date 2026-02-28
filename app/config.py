# Pydantic Settings for environment variable management
# Populated via .env file or environment

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    # App
    debug: bool = False
    secret_key: str = "change-me-in-production"
    # Comma-separated origins, e.g. "http://localhost:3000,https://app.leeg.com"
    # Stored as str to avoid pydantic-settings JSON-parsing a plain URL value.
    cors_origins: str = "http://localhost:3000"

    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",")]

    # Database
    database_url: str = "postgresql+asyncpg://leeg:leeg@localhost:5432/leeg"

    # Auth
    access_token_expire_minutes: int = 60 * 24  # 24 hours

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"

    # Twilio
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_number: str = ""

    # Ollama
    ollama_host: str = "http://localhost:11434"

    # Qdrant
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333


settings = Settings()
