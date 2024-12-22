from pydantic_settings import BaseSettings
import os

class Settings(BaseSettings):
    RATE_LIMIT_REQUESTS: int = os.getenv("RATE_LIMIT_REQUESTS")
    RATE_LIMIT_WINDOW: int = os.getenv("RATE_LIMIT_WINDOW")
    REDIS_URL: str = os.getenv("REDIS_URL")
    DATABASE_URL: str = os.getenv("DATABASE_URL")

    class Config:
        env_file = ".env"

settings = Settings()
