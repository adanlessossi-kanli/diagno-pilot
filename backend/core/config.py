from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    ENV: str = "development"

    MONGODB_URI: str = "mongodb://localhost:27017/diagno_pilot"
    JWT_SECRET: str = "change_me_in_production_use_a_long_secret_key"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_EXPIRE_DAYS: int = 7

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
    RATE_LIMIT_STORAGE_URI: str = "memory://"
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"  # "json" | "text"
    METRICS_AUTH: str = ""  # "user:password" for /metrics Basic Auth

    model_config = {"env_file": ".env", "extra": "ignore"}

    @model_validator(mode="after")
    def validate_cors_in_production(self) -> "Settings":
        if self.ENV == "production" and self.ALLOWED_ORIGINS.strip() in ("*", ""):
            raise ValueError(
                "ALLOWED_ORIGINS must be an explicit list in production (ENV=production). "
                "Set ALLOWED_ORIGINS=https://app.example.com,https://api.example.com"
            )
        return self

    def get_allowed_origins(self) -> list[str]:
        """Parse ALLOWED_ORIGINS into a list, handling the wildcard case."""
        if self.ALLOWED_ORIGINS.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]


settings = Settings()
