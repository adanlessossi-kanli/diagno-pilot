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
    LLM_TIMEOUT: int = 60  # seconds

    ALLOWED_ORIGINS: str = "*"
    RATE_LIMIT_STORAGE_URI: str = "memory://"
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"  # "json" | "text"
    METRICS_AUTH: str = ""  # "user:password" for /metrics Basic Auth

    model_config = {"env_file": ".env", "extra": "ignore"}

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        _WEAK_JWT_SECRETS = {
            "change_me_in_production_use_a_long_secret_key",
            "change_me_generate_with_openssl_rand_hex_32",
            "dev_secret_key_change_this_in_production_32chars",
            "secret",
            "",
        }
        if self.ENV == "production":
            if self.JWT_SECRET in _WEAK_JWT_SECRETS or len(self.JWT_SECRET) < 32:
                raise ValueError(
                    "JWT_SECRET must be a strong random secret (≥32 chars) in production. "
                    "Generate one with: openssl rand -hex 32"
                )
            if self.ALLOWED_ORIGINS.strip() in ("*", ""):
                raise ValueError(
                    "ALLOWED_ORIGINS must be an explicit list in production (ENV=production). "
                    "Set ALLOWED_ORIGINS=https://app.example.com,https://api.example.com"
                )

        # Warn early when the URI looks like a Docker service name but we're
        # not explicitly running in a container environment.  This won't block
        # startup (the ping in database.py will do that), but it surfaces the
        # misconfiguration in the logs before any connection is attempted.
        import socket
        from urllib.parse import urlparse
        try:
            host = urlparse(self.MONGODB_URI).hostname or ""
            # Docker service names are single-label hostnames (no dots, not localhost/127.x)
            is_docker_hostname = (
                host
                and "." not in host
                and host not in ("localhost", "127.0.0.1", "::1")
            )
            if is_docker_hostname:
                try:
                    socket.getaddrinfo(host, None)
                except socket.gaierror:
                    import warnings
                    warnings.warn(
                        f"MONGODB_URI host '{host}' cannot be resolved. "
                        "If you are running outside Docker, set MONGODB_URI=mongodb://localhost:27017/diagno_pilot",
                        stacklevel=2,
                    )
        except Exception:
            pass  # never block startup from a validation side-effect

        return self

    def get_allowed_origins(self) -> list[str]:
        """Parse ALLOWED_ORIGINS into a list, handling the wildcard case."""
        if self.ALLOWED_ORIGINS.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]


settings = Settings()
