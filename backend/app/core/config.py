from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    environment: str = Field("development", env="ENVIRONMENT")
    log_level: str = Field("INFO", env="LOG_LEVEL")

    database_url: str = Field(..., env="DATABASE_URL")

    # GROQ
    groq_api_key: str = Field(..., env="GROQ_API_KEY")
    groq_model: str = Field(
        "llama-3.3-70b-versatile",
        env="GROQ_MODEL"
    )

    # DEEPGRAM
    deepgram_api_key: str = Field(..., env="DEEPGRAM_API_KEY")

    # ELEVENLABS
    elevenlabs_api_key: str = Field(..., env="ELEVENLABS_API_KEY")

    # CRM
    crm_base_url: str = Field(..., env="CRM_BASE_URL")
    crm_api_key: str = Field(..., env="CRM_API_KEY")

    # JWT
    jwt_secret: str = Field(..., env="JWT_SECRET")
    jwt_algorithm: str = Field("HS256", env="JWT_ALGORITHM")
    jwt_expiration_minutes: int = Field(
        1440,
        env="JWT_EXPIRATION_MINUTES"
    )

    # APP
    allowed_hosts: list[str] = ["*"]

    # VOICE
    default_voice_id: str = Field(
        "eleven_monolingual_v1",
        env="DEFAULT_VOICE_ID"
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()