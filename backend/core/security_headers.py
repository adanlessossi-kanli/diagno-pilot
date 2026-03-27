"""
Security headers middleware — Diagno-Pilot Security Hardening

Injects security-relevant HTTP response headers on every response:
  - X-Content-Type-Options: nosniff  (Requirement 8.1)
  - X-Frame-Options: DENY            (Requirement 8.2)
  - Strict-Transport-Security        (Requirement 8.4, production only)
"""
from starlette.middleware.base import BaseHTTPMiddleware

from backend.core.config import settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        if settings.ENV == "production":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        return response
