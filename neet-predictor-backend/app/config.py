"""
Centralized application configuration.

All settings are read from environment variables (or a local .env file
during development). Nothing sensitive is hardcoded.
"""
from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    PROJECT_NAME: str = "NEET Rank Predictor API"
    API_V1_PREFIX: str = "/api/v1"
    ENVIRONMENT: str = "development"

    DATABASE_URL: str = "postgresql+psycopg2://neet_user:neet_password@localhost:5432/neet_predictor"

    SECRET_KEY: str = "insecure-dev-key-change-me"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120

    CORS_ORIGINS: str = "*"

    FIRST_ADMIN_USERNAME: str = "admin"
    FIRST_ADMIN_PASSWORD: str = "change-this-password"

    @property
    def cors_origin_list(self) -> List[str]:
        if self.CORS_ORIGINS.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
