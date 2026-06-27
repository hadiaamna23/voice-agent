from typing import List

from pydantic_settings import BaseSettings
from pydantic import Field, AnyUrl


class Settings(BaseSettings):
    environment: str = Field("production", env="ENVIRONMENT")
    database_url: str = Field(..., env="DATABASE_URL")
    jwt_secret: str = Field(..., env="JWT_SECRET")
    jwt_algorithm: str = Field("HS256", env="JWT_ALGORITHM")
    jwt_expiration_minutes: int = Field(1440, env="JWT_EXPIRATION_MINUTES")
    allowed_hosts: List[str] = Field(["*"], env="ALLOWED_HOSTS")
    openapi_url: str = Field("/api/openapi.json", env="OPENAPI_URL")
    docs_url: str = Field("/docs", env="DOCS_URL")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
