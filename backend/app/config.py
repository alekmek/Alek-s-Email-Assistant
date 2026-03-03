from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Anthropic
    anthropic_api_key: str = ""
    anthropic_model: str = "cl" + "aude-sonnet-4-20250514"

    # Nylas
    nylas_api_key: str = ""
    nylas_client_id: str = ""
    nylas_client_secret: str = ""
    nylas_grant_id: str = ""
    nylas_sid: str = ""

    # Deepgram
    deepgram_api_key: str = ""

    # Cartesia
    cartesia_api_key: str = ""

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    frontend_url: str = "http://localhost:5173"

    # Database
    database_url: str = "sqlite+aiosqlite:///./conversations.db"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
