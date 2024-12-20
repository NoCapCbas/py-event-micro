from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    RATE_LIMIT_REQUESTS: int = 10
    RATE_LIMIT_WINDOW: int = 60

    class Config:
        env_file = ".env"

settings = Settings()
