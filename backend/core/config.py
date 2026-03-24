from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    MONGODB_URI: str = "mongodb://localhost:27017/diagno_pilot"
    JWT_SECRET: str = "change_me_in_production_use_a_long_secret_key"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60

    AWS_ENDPOINT_URL: str | None = None
    AWS_ACCESS_KEY_ID: str | None = None
    AWS_SECRET_ACCESS_KEY: str | None = None
    AWS_DEFAULT_REGION: str = "us-east-1"
    S3_BUCKET: str = "diagno-pilot-files"

    LLM_PRIMARY_URL: str | None = None
    LLM_PRIMARY_API_KEY: str | None = None
    LLM_FALLBACK_URL: str | None = None
    LLM_FALLBACK_API_KEY: str | None = None
    EMBED_MODEL: str = "text-embedding-ada-002"

    ALLOWED_ORIGINS: str = "*"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
