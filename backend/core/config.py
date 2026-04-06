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
    LLM_RETRY_MAX: int = 3
    LLM_RETRY_BASE_DELAY: float = 1.0
    LLM_RETRY_MAX_DELAY: float = 30.0

    # Model_Container (local llama.cpp server)
    MODEL_CONTAINER_URL: str = "http://model:8080/v1"
    MODEL_CONTAINER_API_KEY: str = ""
    MODEL_GPU_LAYERS: int = 99
    MODEL_CONTEXT_SIZE: int = 4096
    MODEL_THREADS: int = 4

    # LlamaIndex pipeline
    LLAMAINDEX_CHUNK_SIZE: int = 512
    LLAMAINDEX_CHUNK_OVERLAP_TOKENS: int = 50
    LLAMAINDEX_SIMILARITY_THRESHOLD: float = 0.75

    # HIPAA compliance
    HIPAA_ENCRYPTION_KEY_ID: str = ""
    HIPAA_AUDIT_HASH_CHAIN_ENABLED: bool = True
    HIPAA_PHI_STRIP_ON_FALLBACK: bool = True

    ALLOWED_ORIGINS: str = "*"
    RATE_LIMIT_STORAGE_URI: str = "memory://"
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"  # "json" | "text"
    METRICS_AUTH: str = ""  # "user:password" for /metrics Basic Auth

    # Cache / Redis settings
    REDIS_URL: str = "redis://localhost:6379/0"
    CACHE_TTL_PROTOCOLS: int = 3600
    CACHE_TTL_INTERACTIONS: int = 3600
    CACHE_TTL_EMBEDDINGS: int = 86400
    CACHE_TTL_RAG: int = 300
    CACHE_KEY_VERSION: str = "v1"

    model_config = {"env_file": ".env", "extra": "ignore"}

    @model_validator(mode="after")
    def set_rate_limit_storage(self) -> "Settings":
        # Only migrate when REDIS_URL was explicitly provided (env var or kwarg),
        # not when it is just the class default. This prevents slowapi from
        # attempting a Redis connection in environments where Redis is not configured.
        if (
            self.RATE_LIMIT_STORAGE_URI == "memory://"
            and self.REDIS_URL
            and "REDIS_URL" in self.model_fields_set
        ):
            self.RATE_LIMIT_STORAGE_URI = self.REDIS_URL
        return self

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
            if not self.HIPAA_ENCRYPTION_KEY_ID:
                raise ValueError(
                    "HIPAA_ENCRYPTION_KEY_ID must be set in production (ENV=production)."
                )
            if not self.HIPAA_PHI_STRIP_ON_FALLBACK:
                raise ValueError(
                    "HIPAA_PHI_STRIP_ON_FALLBACK must be enabled in production (ENV=production)."
                )

        # Warn early when the URI looks like a Docker service name but we're
        # not explicitly running in a container environment.  This won't block
        # startup (the ping in database.py will do that), but it surfaces the
        # misconfiguration in the logs before any connection is attempted.
        # NOTE: DNS resolution is deferred to a background thread to avoid
        # blocking the event loop or slowing down test instantiation.
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
                import threading
                def _check_dns(h: str) -> None:
                    import socket
                    try:
                        socket.getaddrinfo(h, None)
                    except socket.gaierror:
                        import warnings
                        warnings.warn(
                            f"MONGODB_URI host '{h}' cannot be resolved. "
                            "If you are running outside Docker, set MONGODB_URI=mongodb://localhost:27017/diagno_pilot",
                            stacklevel=2,
                        )
                threading.Thread(target=_check_dns, args=(host,), daemon=True).start()
        except Exception:
            pass  # never block startup from a validation side-effect

        return self

    def get_allowed_origins(self) -> list[str]:
        """Parse ALLOWED_ORIGINS into a list, handling the wildcard case."""
        if self.ALLOWED_ORIGINS.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]


settings = Settings()
