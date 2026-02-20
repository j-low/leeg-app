# Pydantic Settings for environment variable management
# Populated via .env file or environment

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    # App
    debug: bool = False
    secret_key: str = "change-me-in-production"
    # Comma-separated list of allowed CORS origins, e.g. "http://localhost:3000,https://app.leeg.com"
    cors_origins: list[str] = ["http://localhost:3000"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str | list) -> list[str]:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v

    # Database
    database_url: str = "postgresql+asyncpg://leeg:leeg@localhost:5432/leeg"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

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
