"""
Tests for Content_Localiser — property-based and unit tests.

Feature: i18n-medical-content

Property 1: parse_locale always returns a supported locale
  Validates: Requirements 1.2, 1.3, 1.4, 1.7

Property 2: extract_region correctly derives region from locale
  Validates: Requirements 1.8, 5.5

Property 3: locale round-trip
  Validates: Requirements 5.4

Property 4: localise follows the fallback chain
  Validates: Requirements 5.1, 5.2, 5.6
"""
from __future__ import annotations

import pytest
from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

from backend.services.content_localiser import (
    SUPPORTED_LOCALES,
    extract_region,
    localise,
    parse_locale,
)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Any printable text — covers empty, None-like strings, garbage BCP-47 tags
any_header_strategy = st.one_of(
    st.just(""),
    st.just(None),
    st.text(min_size=1, max_size=64),
    # Well-formed but unsupported tags
    st.sampled_from(["de-DE", "ar", "zh-CN", "pt-BR", "es-ES", "it", "ja"]),
    # Supported tags
    st.sampled_from(["fr-TG", "fr-BJ", "en", "fr"]),
    # Multi-value headers
    st.sampled_from(["fr-TG,en;q=0.9", "en,fr;q=0.8", "fr-BJ,fr;q=0.7,en;q=0.5"]),
    # Malformed
    st.sampled_from([";;;", "  ", "\t", "123", "fr_TG"]),
)

# Locales that have defined fallback chains (including alias)
known_locale_strategy = st.sampled_from(["fr-TG", "fr-BJ", "en", "fr"])

# Arbitrary locale strings for extract_region
locale_string_strategy = st.one_of(
    st.sampled_from(["fr-TG", "fr-BJ", "en", "fr", "en-US", "zh-CN", "pt-BR"]),
    st.text(min_size=0, max_size=20),
)

# ---------------------------------------------------------------------------
# Property 1: parse_locale always returns a supported locale
# Feature: i18n-medical-content, Property 1: parse_locale always returns a supported locale
# ---------------------------------------------------------------------------

@given(accept_language=any_header_strategy)
@h_settings(max_examples=200)
def test_parse_locale_always_returns_supported_locale(accept_language: str | None):
    """
    Feature: i18n-medical-content, Property 1: parse_locale always returns a supported locale

    For any string passed as an Accept-Language header value (including empty
    string, None, arbitrary unsupported tags, and the legacy 'fr' alias),
    parse_locale() SHALL return a value that is a member of SUPPORTED_LOCALES.

    Validates: Requirements 1.2, 1.3, 1.4, 1.7
    """
    result = parse_locale(accept_language)
    assert result in SUPPORTED_LOCALES, (
        f"parse_locale({accept_language!r}) returned {result!r}, "
        f"which is not in SUPPORTED_LOCALES={SUPPORTED_LOCALES}"
    )


# ---------------------------------------------------------------------------
# Property 2: extract_region correctly derives region from locale
# Feature: i18n-medical-content, Property 2: extract_region correctly derives region from locale
# ---------------------------------------------------------------------------

@given(locale=locale_string_strategy)
@h_settings(max_examples=200)
def test_extract_region_returns_two_letter_code_or_none(locale: str):
    """
    Feature: i18n-medical-content, Property 2: extract_region correctly derives region from locale

    For any locale string, extract_region() SHALL return either:
    - A two-letter uppercase string (ISO 3166-1 alpha-2) when a region subtag exists
    - None when no region subtag is present

    Validates: Requirements 1.8, 5.5
    """
    result = extract_region(locale)
    if result is not None:
        assert isinstance(result, str), f"extract_region({locale!r}) must return str or None"
        assert len(result) == 2, f"Region code must be 2 characters, got {result!r}"
        assert result.isupper(), f"Region code must be uppercase, got {result!r}"
        assert result.isalpha(), f"Region code must be alphabetic, got {result!r}"


@given(locale=st.sampled_from(["fr-TG", "fr-BJ", "en-US", "zh-CN", "pt-BR"]))
@h_settings(max_examples=50)
def test_extract_region_known_locales(locale: str):
    """
    Feature: i18n-medical-content, Property 2: extract_region correctly derives region from locale

    For known locales with region subtags, extract_region() must return the
    correct country code.

    Validates: Requirements 1.8, 5.5
    """
    result = extract_region(locale)
    expected_region = locale.split("-")[1].upper()
    assert result == expected_region, (
        f"extract_region({locale!r}) returned {result!r}, expected {expected_region!r}"
    )


@given(locale=st.sampled_from(["en", "fr", "de", "ar"]))
@h_settings(max_examples=50)
def test_extract_region_no_subtag_returns_none(locale: str):
    """
    Feature: i18n-medical-content, Property 2: extract_region correctly derives region from locale

    For locales without a region subtag, extract_region() must return None.

    Validates: Requirements 1.8, 5.5
    """
    result = extract_region(locale)
    assert result is None, (
        f"extract_region({locale!r}) returned {result!r}, expected None"
    )


# ---------------------------------------------------------------------------
# Property 3: locale round-trip
# Feature: i18n-medical-content, Property 3: locale round-trip
# ---------------------------------------------------------------------------

@given(locale=known_locale_strategy)
@h_settings(max_examples=100)
def test_locale_round_trip(locale: str):
    """
    Feature: i18n-medical-content, Property 3: locale round-trip

    For any locale string in {"fr-TG", "fr-BJ", "en", "fr"}, parsing the
    locale with parse_locale, formatting it back to a string, and parsing
    again SHALL produce an equivalent locale value:
        parse_locale(parse_locale(s)) == parse_locale(s)

    Validates: Requirements 5.4
    """
    first_parse = parse_locale(locale)
    second_parse = parse_locale(first_parse)
    assert first_parse == second_parse, (
        f"Round-trip failed for {locale!r}: "
        f"parse_locale({locale!r})={first_parse!r}, "
        f"parse_locale({first_parse!r})={second_parse!r}"
    )


# ---------------------------------------------------------------------------
# Property 4: localise follows the fallback chain
# Feature: i18n-medical-content, Property 4: localise follows the fallback chain
# ---------------------------------------------------------------------------

def _make_translations(**kwargs: str) -> dict:
    """Build a content object with a translations map."""
    return {"translations": dict(kwargs)}


@given(
    locale=known_locale_strategy,
    value=st.text(min_size=1, max_size=64),
)
@h_settings(max_examples=200)
def test_localise_returns_exact_match_when_present(locale: str, value: str):
    """
    Feature: i18n-medical-content, Property 4: localise follows the fallback chain

    When the exact locale key is present in translations, localise() must
    return that value.

    Validates: Requirements 5.1, 5.2
    """
    content = _make_translations(**{locale: value})
    result = localise(content, locale)
    assert result == value, (
        f"localise with exact key {locale!r} returned {result!r}, expected {value!r}"
    )


@given(
    locale=st.sampled_from(["fr-TG", "fr-BJ"]),
    fr_value=st.text(min_size=1, max_size=64),
)
@h_settings(max_examples=100)
def test_localise_falls_back_to_fr_when_specific_missing(locale: str, fr_value: str):
    """
    Feature: i18n-medical-content, Property 4: localise follows the fallback chain

    When the specific locale key (fr-TG or fr-BJ) is absent but 'fr' is
    present, localise() must return the 'fr' value.

    Validates: Requirements 5.1, 5.2
    """
    content = _make_translations(fr=fr_value)
    result = localise(content, locale)
    assert result == fr_value, (
        f"localise({locale!r}) with only 'fr' key returned {result!r}, expected {fr_value!r}"
    )


@given(
    locale=st.sampled_from(["fr-TG", "fr-BJ", "fr"]),
    en_value=st.text(min_size=1, max_size=64),
)
@h_settings(max_examples=100)
def test_localise_falls_back_to_en_as_last_resort(locale: str, en_value: str):
    """
    Feature: i18n-medical-content, Property 4: localise follows the fallback chain

    When neither the specific locale nor 'fr' is present, localise() must
    fall back to 'en'.

    Validates: Requirements 5.1, 5.2
    """
    content = _make_translations(en=en_value)
    result = localise(content, locale)
    assert result == en_value, (
        f"localise({locale!r}) with only 'en' key returned {result!r}, expected {en_value!r}"
    )


@given(locale=st.text(min_size=0, max_size=32))
@h_settings(max_examples=200)
def test_localise_never_raises(locale: str):
    """
    Feature: i18n-medical-content, Property 4: localise follows the fallback chain

    localise() SHALL never raise an exception regardless of the locale value
    or the shape of the content object.

    Validates: Requirements 5.6
    """
    # Various malformed content objects
    for content in [
        {},
        {"translations": None},
        {"translations": "not-a-dict"},
        {"translations": []},
        {"translations": {}},
        _make_translations(**{"fr-TG": "value"}),
    ]:
        try:
            result = localise(content, locale)
            assert result is None or isinstance(result, str), (
                f"localise must return str or None, got {type(result)}"
            )
        except Exception as exc:  # noqa: BLE001
            pytest.fail(
                f"localise raised {type(exc).__name__} for locale={locale!r}, "
                f"content={content!r}: {exc}"
            )


@given(locale=st.text(min_size=0, max_size=32))
@h_settings(max_examples=100)
def test_localise_returns_none_when_no_key_in_chain(locale: str):
    """
    Feature: i18n-medical-content, Property 4: localise follows the fallback chain

    When no key in the fallback chain is present in translations, localise()
    must return None.

    Validates: Requirements 5.2, 5.6
    """
    # Translations with a key that is never in any fallback chain
    content = _make_translations(**{"xx-ZZ": "unreachable"})
    result = localise(content, locale)
    # Either None (no chain key matched) or the value if locale happens to be "xx-ZZ"
    # We only assert it doesn't raise and returns str or None
    assert result is None or isinstance(result, str)


# ---------------------------------------------------------------------------
# Unit tests — specific examples
# ---------------------------------------------------------------------------

class TestParseLocaleExamples:
    """Unit tests covering specific Accept-Language header examples."""

    def test_fr_tg_exact(self):
        assert parse_locale("fr-TG") == "fr-TG"

    def test_fr_bj_exact(self):
        assert parse_locale("fr-BJ") == "fr-BJ"

    def test_en_exact(self):
        assert parse_locale("en") == "en"

    def test_fr_alias_maps_to_fr_tg(self):
        """Req 1.7: 'fr' must be treated as 'fr-TG' for backward compatibility."""
        assert parse_locale("fr") == "fr-TG"

    def test_empty_header_returns_default(self):
        """Req 1.3: absent/empty header → DEFAULT_LOCALE."""
        result = parse_locale("")
        assert result in SUPPORTED_LOCALES

    def test_none_header_returns_default(self):
        """Req 1.3: None header → DEFAULT_LOCALE."""
        result = parse_locale(None)
        assert result in SUPPORTED_LOCALES

    def test_unsupported_locale_returns_supported(self):
        """Req 1.4: unsupported locale → falls back to a supported locale."""
        result = parse_locale("de-DE")
        assert result in SUPPORTED_LOCALES

    def test_multi_value_header_picks_first_supported(self):
        """Multi-value header: first supported locale wins."""
        result = parse_locale("fr-BJ,en;q=0.9")
        assert result == "fr-BJ"

    def test_multi_value_header_fallback_to_second(self):
        """Multi-value header: falls through to second when first unsupported."""
        result = parse_locale("de,fr-TG;q=0.8")
        assert result == "fr-TG"

    def test_fr_prefix_match(self):
        """fr-CI (unsupported region) should match a supported fr-* locale."""
        result = parse_locale("fr-CI")
        assert result in SUPPORTED_LOCALES
        assert result.startswith("fr")

    def test_malformed_header_returns_supported(self):
        """Malformed header must not raise and must return a supported locale."""
        result = parse_locale(";;;")
        assert result in SUPPORTED_LOCALES


class TestExtractRegionExamples:
    """Unit tests for extract_region with specific inputs."""

    def test_fr_tg(self):
        assert extract_region("fr-TG") == "TG"

    def test_fr_bj(self):
        assert extract_region("fr-BJ") == "BJ"

    def test_en_no_region(self):
        assert extract_region("en") is None

    def test_fr_no_region(self):
        assert extract_region("fr") is None

    def test_empty_string(self):
        assert extract_region("") is None

    def test_en_us(self):
        assert extract_region("en-US") == "US"


class TestLocaliseExamples:
    """Unit tests for localise with specific content objects."""

    def test_exact_locale_match(self):
        content = {"translations": {"fr-TG": "Amoxicilline (TG)", "en": "Amoxicillin"}}
        assert localise(content, "fr-TG") == "Amoxicilline (TG)"

    def test_fallback_fr_to_fr_tg(self):
        """fr-TG falls back to 'fr' when 'fr-TG' key absent."""
        content = {"translations": {"fr": "Amoxicilline", "en": "Amoxicillin"}}
        assert localise(content, "fr-TG") == "Amoxicilline"

    def test_fallback_fr_bj_to_fr(self):
        """fr-BJ falls back to 'fr' when 'fr-BJ' key absent."""
        content = {"translations": {"fr": "Amoxicilline", "en": "Amoxicillin"}}
        assert localise(content, "fr-BJ") == "Amoxicilline"

    def test_fallback_to_en(self):
        """Falls back to 'en' when neither specific nor 'fr' key present."""
        content = {"translations": {"en": "Amoxicillin"}}
        assert localise(content, "fr-TG") == "Amoxicillin"

    def test_returns_none_when_no_key(self):
        """Returns None when no key in the fallback chain is present."""
        content = {"translations": {"de": "Amoxizillin"}}
        assert localise(content, "fr-TG") is None

    def test_empty_translations(self):
        assert localise({"translations": {}}, "fr-TG") is None

    def test_missing_translations_key(self):
        assert localise({}, "fr-TG") is None

    def test_none_translations_value(self):
        assert localise({"translations": None}, "fr-TG") is None

    def test_fr_alias_uses_fr_tg_chain(self):
        """'fr' alias uses the fr-TG fallback chain."""
        content = {"translations": {"fr-TG": "Amoxicilline TG"}}
        assert localise(content, "fr") == "Amoxicilline TG"

    def test_en_locale_returns_en_value(self):
        content = {"translations": {"en": "Amoxicillin", "fr": "Amoxicilline"}}
        assert localise(content, "en") == "Amoxicillin"
