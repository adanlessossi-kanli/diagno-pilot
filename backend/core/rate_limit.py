"""Rate limiting configuration using slowapi (REQ 2.1–2.5)."""
from __future__ import annotations

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.core.config import settings


def _get_user_id_or_ip(request: Request) -> str:
    """Key function: use JWT user_id for authenticated requests, IP otherwise."""
    # The Authorization header carries the Bearer token; extract sub from it
    # without full validation — slowapi only needs a stable string key.
    auth: str | None = request.headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        token = auth[7:]
        try:
            import jwt as pyjwt
            from backend.core.config import settings as _s
            payload = pyjwt.decode(
                token,
                _s.JWT_SECRET,
                algorithms=[_s.JWT_ALGORITHM],
            )
            user_id: str | None = payload.get("sub")
            if user_id:
                return user_id
        except Exception:
            pass
    return get_remote_address(request)


limiter = Limiter(
    key_func=_get_user_id_or_ip,
    storage_uri=settings.RATE_LIMIT_STORAGE_URI,
    swallow_errors=True,
)
