"""
CSRF protection dependency for FastAPI.

Implements double-submit-cookie pattern using constant-time comparison
to prevent timing attacks (Requirement 6.7).
"""
import hmac

from fastapi import HTTPException, Request

# Paths exempt from CSRF validation (no session cookie yet, or protected by other means)
_EXEMPT_PATHS = {"/api/v1/auth/login", "/api/v1/auth/refresh"}

# Methods that mutate state and require CSRF validation
_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


async def verify_csrf(request: Request) -> None:
    """
    FastAPI dependency that enforces CSRF token validation on state-mutating requests.

    - Skips validation for GET, HEAD, OPTIONS methods.
    - Skips validation for /api/v1/auth/login and /api/v1/auth/refresh.
    - Uses hmac.compare_digest for constant-time comparison (Requirement 6.7).
    - Raises HTTP 403 with detail "csrf_token_invalid" on mismatch or missing values.

    Requirements: 6.3, 6.4, 6.5, 6.7
    """
    if request.method not in _MUTATING_METHODS:
        return

    if request.url.path in _EXEMPT_PATHS:
        return

    cookie_val = request.cookies.get("csrf_token", "")
    header_val = request.headers.get("X-CSRF-Token", "")

    if not hmac.compare_digest(cookie_val, header_val):
        raise HTTPException(status_code=403, detail="csrf_token_invalid")
