from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    SECRET_KEY: str = "change-me-must-match-vendex"
    DATABASE_URL: str = "postgresql+asyncpg://vendex:vendex@localhost:5432/vendex"
    DB_SCHEMA: str = "claims"
    VENDEX_INTERNAL_URL: str = "http://localhost:8000"
    GENERATED_DIR: str = "/var/uzum-claims/generated"
    JWT_ALGORITHM: str = "HS256"
    ALLOWED_ORIGINS: list[str] = [
        "http://localhost:8000",
        "http://localhost:8100",
        "http://127.0.0.1:8100",
    ]

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    s = Settings()
    if s.DATABASE_URL.startswith("postgres://"):
        s.DATABASE_URL = s.DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
    elif s.DATABASE_URL.startswith("postgresql://") and "+asyncpg" not in s.DATABASE_URL:
        s.DATABASE_URL = s.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
    return s
