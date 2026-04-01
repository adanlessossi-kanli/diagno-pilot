import asyncio
import logging
import time
import traceback
import uuid
from contextlib import asynccontextmanager

import httpx
from dotenv import load_dotenv

load_dotenv()

from fastapi import Depends, FastAPI, HTTPException, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from fastapi.security import HTTPBasic, HTTPBasicCredentials  # noqa: E402
from prometheus_fastapi_instrumentator import Instrumentator  # noqa: E402
from slowapi.errors import RateLimitExceeded  # noqa: E402
from slowapi.middleware import SlowAPIMiddleware  # noqa: E402
from starlette.exceptions import HTTPException as StarletteHTTPException  # noqa: E402
from starlette.responses import Response  # noqa: E402

from backend.core.cache import cache_service  # noqa: E402
from backend.core.config import settings  # noqa: E402
from backend.core.csrf import verify_csrf  # noqa: E402
from backend.core.security_headers import SecurityHeadersMiddleware  # noqa: E402
from backend.core.database import db  # noqa: E402
from backend.core.logging_config import request_id_var, setup_logging  # noqa: E402
from backend.core.rate_limit import limiter  # noqa: E402
from backend.routers import admin, alerts, auth, chat, diagnose, documents, files, patients, qa  # noqa: E402
from backend.services.diagnostic_service import DiagnosticService  # noqa: E402
from backend.services.embedding_service import EmbeddingModel  # noqa: E402
from backend.services.llm_router import LLMRouter  # noqa: E402
from backend.services.alert_service import alert_service  # noqa: E402
from backend.services.prescription_service import prescription_service  # noqa: E402
from backend.services.rag_service import RAGService  # noqa: E402

# Initialise structured logging before anything else
setup_logging(log_level=settings.LOG_LEVEL, log_format=settings.LOG_FORMAT)
logger = logging.getLogger(__name__)


async def _warm_up_cache() -> None:
    """Pre-populate Redis with protocols and interactions (non-blocking background task).

    Runs with a 10-second timeout. On timeout or any other error the application
    continues with a cold cache — warm-up failures are never fatal.
    """
    try:
        async with asyncio.timeout(10):
            await prescription_service.load_protocols_from_db()
            await alert_service.load_interactions_from_db()
    except TimeoutError:
        logger.warning("Cache warm-up timed out after 10 s; starting with cold cache")
    except Exception:
        logger.error("Cache warm-up failed; starting with cold cache", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Connect CacheService first (non-blocking — enters degraded mode if Redis is down)
    await cache_service.connect()

    # Fire warm-up as a background task so the app starts serving immediately
    asyncio.create_task(_warm_up_cache())

    try:
        await db.connect()
    except RuntimeError as exc:
        # Log clearly and re-raise so uvicorn exits instead of serving a broken app
        logger.critical("Startup failed — %s", exc)
        raise
    logger.info("MongoDB connected")
    from backend.routers.auth import ensure_refresh_token_indexes
    await ensure_refresh_token_indexes()
    logger.info("refresh_tokens indexes ensured")

    # Ensure query indexes (background=True avoids blocking startup)
    _db = db.get_db()
    await _db["patients"].create_index("created_by", background=True)
    await _db["patients"].create_index(
        [("created_by", 1), ("created_at", -1)], background=True
    )
    logger.info("patients indexes ensured")

    # Ensure vector search index on document_chunks for RAG
    try:
        await _db.create_collection("document_chunks")
    except Exception:
        pass  # collection already exists
    existing = await _db["document_chunks"].list_search_indexes("embedding_index").to_list(1)
    if not existing:
        await _db["document_chunks"].create_search_index({
            "name": "embedding_index",
            "type": "vectorSearch",
            "definition": {
                "fields": [{
                    "type": "vector",
                    "path": "embedding",
                    "numDimensions": 1536,
                    "similarity": "cosine",
                }]
            },
        })
        logger.info("embedding_index vector search index created")
    else:
        logger.info("embedding_index vector search index already exists")

    # Singleton DiagnosticService (REQ 6.5)
    database = db.get_db()
    mongo_client = database.client
    llm_router = LLMRouter()
    embedder = EmbeddingModel()
    rag = RAGService(
        mongo_client=mongo_client,
        llm_router=llm_router,
        embedder=embedder,
        db_name=database.name,
    )
    app.state.diagnostic_service = DiagnosticService(rag_service=rag)
    logger.info("DiagnosticService singleton initialised")

    yield
    await cache_service.disconnect()
    await db.disconnect()
    logger.info("MongoDB disconnected")


app = FastAPI(
    title="Diagno-Pilot API",
    description="API d'aide au diagnostic des maladies infectieuses et à la prescription antibiotique",
    version="0.1.0",
    lifespan=lifespan,
)

# Rate limiter state
app.state.limiter = limiter


def _rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> Response:
    """Custom handler that always includes Retry-After header (REQ 2.3)."""
    response = JSONResponse(
        {"error": f"Rate limit exceeded: {exc.detail}"}, status_code=429
    )
    # Calculate seconds until window reset and add Retry-After header
    try:
        view_rate_limit = getattr(request.state, "view_rate_limit", None)
        if view_rate_limit is not None:
            window_stats = limiter.limiter.get_window_stats(
                view_rate_limit[0], *view_rate_limit[1]
            )
            reset_in = max(1, int(window_stats[0] - time.time()))
            response.headers["Retry-After"] = str(reset_in)
        else:
            response.headers["Retry-After"] = "60"
    except Exception:
        response.headers["Retry-After"] = "60"
    return response


app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
app.add_middleware(SlowAPIMiddleware)

# CORS
origins = settings.get_allowed_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security headers — registered after CORS so it wraps CORS and runs on every response
# (Starlette applies middleware in reverse registration order; this becomes the outermost layer)
app.add_middleware(SecurityHeadersMiddleware)


# Request logging middleware — injects request_id and logs structured HTTP fields (REQ 14.1, 14.2)
@app.middleware("http")
async def log_requests(request: Request, call_next):
    req_id = str(uuid.uuid4())
    token = request_id_var.set(req_id)
    request.state.request_id = req_id
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - start) * 1000, 1)
    logger.info(
        "%s %s %s",
        request.method,
        request.url.path,
        response.status_code,
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
        },
    )
    request_id_var.reset(token)
    return response


# Global error handlers
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if isinstance(exc, RateLimitExceeded):
        return _rate_limit_exceeded_handler(request, exc)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.error(
        "Unhandled error: %s",
        exc,
        extra={
            "error": f"{type(exc).__name__}: {exc}",
            "stack_trace": traceback.format_exc(),
        },
    )
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# Routers
API_PREFIX = "/api/v1"
app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(chat.router, prefix=API_PREFIX)
app.include_router(diagnose.router, prefix=API_PREFIX)
app.include_router(patients.router, prefix=API_PREFIX)
app.include_router(documents.router, prefix=API_PREFIX)
app.include_router(files.router, prefix=API_PREFIX)
app.include_router(alerts.router, prefix=API_PREFIX)
app.include_router(admin.router, prefix=API_PREFIX)
app.include_router(qa.router, prefix=API_PREFIX)

# Apply CSRF validation globally to all routes (Requirements 6.3, 6.4, 6.5)
app.router.dependencies.append(Depends(verify_csrf))


_PROBE_TIMEOUT = 5.0  # seconds


async def _probe_llm_primary() -> str:
    """Probe the primary LLM endpoint. Returns 'ok', 'not_configured', or 'unreachable: <reason>'."""
    url = settings.LLM_PRIMARY_URL
    if not url:
        return "not_configured"
    try:
        async with httpx.AsyncClient(timeout=_PROBE_TIMEOUT) as client:
            resp = await client.get(f"{url.rstrip('/')}/models")
            resp.raise_for_status()
        return "ok"
    except Exception as exc:
        logger.warning("Health probe failed for llm_primary: %s", exc)
        return f"unreachable: {exc}"


async def _probe_llm_fallback() -> str:
    """Probe the fallback LLM endpoint. Returns 'ok', 'not_configured', or 'unreachable: <reason>'."""
    url = settings.LLM_FALLBACK_URL
    if not url:
        return "not_configured"
    try:
        async with httpx.AsyncClient(timeout=_PROBE_TIMEOUT) as client:
            resp = await client.get(f"{url.rstrip('/')}/models")
            resp.raise_for_status()
        return "ok"
    except Exception as exc:
        logger.warning("Health probe failed for llm_fallback: %s", exc)
        return f"unreachable: {exc}"


async def _probe_embedding() -> str:
    """Probe the embedding endpoint. Returns 'ok', 'not_configured', or 'unreachable: <reason>'."""
    url = settings.LLM_PRIMARY_URL  # embedding reuses the primary LLM URL
    if not url:
        return "not_configured"
    try:
        async with httpx.AsyncClient(timeout=_PROBE_TIMEOUT) as client:
            resp = await client.get(f"{url.rstrip('/')}/models")
            resp.raise_for_status()
        return "ok"
    except Exception as exc:
        logger.warning("Health probe failed for embedding: %s", exc)
        return f"unreachable: {exc}"


@app.get("/health", tags=["health"])
async def health():
    # Run all four probes concurrently
    db_status_result, redis_ok, llm_primary_status, llm_fallback_status, embedding_status = (
        await asyncio.gather(
            _probe_mongo(),
            cache_service.ping(),
            _probe_llm_primary(),
            _probe_llm_fallback(),
            _probe_embedding(),
            return_exceptions=True,
        )
    )

    # Handle exceptions from gather (treat as failures)
    if isinstance(db_status_result, Exception):
        db_status = f"unreachable: {db_status_result}"
    else:
        db_status = db_status_result

    if isinstance(redis_ok, Exception) or not redis_ok:
        redis_status = "degraded"
        redis_ok_bool = False
    else:
        redis_status = "ok"
        redis_ok_bool = True

    if isinstance(llm_primary_status, Exception):
        llm_primary_status = f"unreachable: {llm_primary_status}"
    if isinstance(llm_fallback_status, Exception):
        llm_fallback_status = f"unreachable: {llm_fallback_status}"
    if isinstance(embedding_status, Exception):
        embedding_status = f"unreachable: {embedding_status}"

    all_ok = (
        db_status == "ok"
        and redis_ok_bool
        and llm_primary_status == "ok"
        and llm_fallback_status == "ok"
        and embedding_status == "ok"
    )
    overall = "ok" if all_ok else "degraded"

    return {
        "status": overall,
        "db": db_status,
        "redis": redis_status,
        "llm_primary": llm_primary_status,
        "llm_fallback": llm_fallback_status,
        "embedding": embedding_status,
    }


async def _probe_mongo() -> str:
    """Probe MongoDB. Returns 'ok' or 'unreachable: <reason>'."""
    try:
        await db.get_db().client.admin.command("ping")
        return "ok"
    except Exception as exc:
        return f"unreachable: {exc}"


# ---------------------------------------------------------------------------
# Prometheus metrics — REQ 18
# ---------------------------------------------------------------------------

def _verify_metrics_auth(credentials: HTTPBasicCredentials) -> bool:
    """Return True if credentials match METRICS_AUTH, or if METRICS_AUTH is empty."""
    auth_cfg = settings.METRICS_AUTH.strip()
    if not auth_cfg:
        return True  # dev mode — unauthenticated access allowed
    if ":" not in auth_cfg:
        return False
    expected_user, expected_password = auth_cfg.split(":", 1)
    return credentials.username == expected_user and credentials.password == expected_password


_http_basic = HTTPBasic(auto_error=False)


def _metrics_auth_dependency(credentials: HTTPBasicCredentials | None = Depends(_http_basic)):
    """FastAPI dependency that enforces Basic Auth on /metrics when METRICS_AUTH is set."""
    auth_cfg = settings.METRICS_AUTH.strip()
    if not auth_cfg:
        return  # dev mode — allow all
    if credentials is None or not _verify_metrics_auth(credentials):
        raise HTTPException(
            status_code=401,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic realm=\"Diagno-Pilot Metrics\""},
        )


# Instrument the app — exposes diagno_pilot_http_requests_total and
# diagno_pilot_http_request_duration_seconds via the /metrics endpoint.
Instrumentator(
    excluded_handlers=["/metrics", "/health"],
).instrument(app).expose(
    app,
    endpoint="/metrics",
    include_in_schema=False,
    dependencies=[Depends(_metrics_auth_dependency)],
)
