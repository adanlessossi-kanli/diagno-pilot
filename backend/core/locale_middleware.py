"""
Locale middleware — Diagno-Pilot i18n-medical-content

Starlette middleware that resolves the request locale once at the request
boundary and stores the resolved (locale, region) pair in request.state so
that all downstream services receive it as a parameter without re-parsing
the Accept-Language header.

Requirements: 1.1, 1.2, 1.3, 10.1
"""
from __future__ import annotations

import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from backend.services.content_localiser import extract_region, parse_locale

logger = logging.getLogger(__name__)


class LocaleMiddleware(BaseHTTPMiddleware):
    """Resolve Accept-Language → (locale, region) and store in request.state."""

    async def dispatch(self, request: Request, call_next):
        accept_language: str | None = request.headers.get("Accept-Language")
        locale = parse_locale(accept_language)
        region = extract_region(locale)

        request.state.locale = locale
        request.state.region = region

        logger.info(
            "Resolved locale=%r region=%r from Accept-Language=%r",
            locale,
            region,
            accept_language,
        )

        return await call_next(request)
