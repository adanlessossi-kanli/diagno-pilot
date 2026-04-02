"""
Unit tests for LocaleMiddleware — Diagno-Pilot i18n-medical-content

Tests cover:
  - fr-TG, fr-BJ, en explicit headers
  - fr alias → fr-TG (backward compat, Req 1.7)
  - absent Accept-Language header → default fr-TG (Req 1.3)
  - unsupported locale → fr-TG fallback (Req 1.3)
  - request.state.locale and request.state.region are set correctly (Req 1.1)
  - INFO log is emitted (Req 10.1)

Requirements: 1.2, 1.3, 1.7
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from backend.core.locale_middleware import LocaleMiddleware


# ---------------------------------------------------------------------------
# Test app fixture
# ---------------------------------------------------------------------------

def _make_app() -> FastAPI:
    """Minimal FastAPI app with LocaleMiddleware and an echo endpoint."""
    test_app = FastAPI()
    test_app.add_middleware(LocaleMiddleware)

    @test_app.get("/echo-locale")
    async def echo_locale(request: Request):
        return JSONResponse({
            "locale": request.state.locale,
            "region": request.state.region,
        })

    return test_app


@pytest.fixture()
def app():
    return _make_app()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get(app: FastAPI, accept_language: str | None = None) -> dict:
    headers = {}
    if accept_language is not None:
        headers["Accept-Language"] = accept_language
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/echo-locale", headers=headers)
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fr_tg_header(app):
    """Explicit fr-TG header → locale=fr-TG, region=TG."""
    data = await _get(app, "fr-TG")
    assert data["locale"] == "fr-TG"
    assert data["region"] == "TG"


@pytest.mark.asyncio
async def test_fr_bj_header(app):
    """Explicit fr-BJ header → locale=fr-BJ, region=BJ."""
    data = await _get(app, "fr-BJ")
    assert data["locale"] == "fr-BJ"
    assert data["region"] == "BJ"


@pytest.mark.asyncio
async def test_en_header(app):
    """Explicit en header → locale=en, region=None."""
    data = await _get(app, "en")
    assert data["locale"] == "en"
    assert data["region"] is None


@pytest.mark.asyncio
async def test_fr_alias_maps_to_fr_tg(app):
    """fr alias → fr-TG for backward compatibility (Req 1.7)."""
    data = await _get(app, "fr")
    assert data["locale"] == "fr-TG"
    assert data["region"] == "TG"


@pytest.mark.asyncio
async def test_absent_header_defaults_to_fr_tg(app):
    """No Accept-Language header → default locale fr-TG (Req 1.3)."""
    data = await _get(app, accept_language=None)
    assert data["locale"] == "fr-TG"
    assert data["region"] == "TG"


@pytest.mark.asyncio
async def test_unsupported_locale_falls_back_to_fr_tg(app):
    """Unsupported locale (e.g. de-DE) → fr-TG fallback (Req 1.3)."""
    data = await _get(app, "de-DE")
    assert data["locale"] == "fr-TG"
    assert data["region"] == "TG"


@pytest.mark.asyncio
async def test_empty_accept_language_defaults_to_fr_tg(app):
    """Empty Accept-Language string → fr-TG default."""
    data = await _get(app, "")
    assert data["locale"] == "fr-TG"
    assert data["region"] == "TG"


@pytest.mark.asyncio
async def test_info_log_emitted(app, caplog):
    """Middleware logs resolved locale and region at INFO level (Req 10.1)."""
    import logging
    with caplog.at_level(logging.INFO, logger="backend.core.locale_middleware"):
        await _get(app, "fr-BJ")
    assert any("fr-BJ" in record.message for record in caplog.records)
    assert any("BJ" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_quality_value_in_header(app):
    """Accept-Language with quality values (e.g. fr-TG;q=0.9) is parsed correctly."""
    data = await _get(app, "fr-TG;q=0.9")
    assert data["locale"] == "fr-TG"


@pytest.mark.asyncio
async def test_multiple_locales_first_supported_wins(app):
    """First supported locale in a comma-separated list is selected."""
    data = await _get(app, "de-DE, fr-BJ;q=0.8")
    # de-DE is unsupported → falls through to fr-BJ
    assert data["locale"] == "fr-BJ"
    assert data["region"] == "BJ"
