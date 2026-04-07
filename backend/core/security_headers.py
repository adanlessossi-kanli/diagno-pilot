"""
Security headers middleware — Diagno-Pilot Security Hardening

Injects security-relevant HTTP response headers on every response:
  - X-Content-Type-Options: nosniff  (Requirement 8.1)
  - X-Frame-Options: DENY            (Requirement 8.2)
  - Strict-Transport-Security        (Requirement 8.4, production only)
  - Content-Security-Policy           (Requirement 9.1)
  - Referrer-Policy                   (Requirement 13.1)
  - Permissions-Policy                (Requirement 13.2)
"""
from starlette.middleware.base import BaseHTTPMiddleware

from backend.core.config import settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = settings.CSP_POLICY
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=()"
        )
        if settings.ENV == "production":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        return response
