"""
Content_Localiser — locale resolution and medical content localisation.

Provides three pure, stateless functions:
  - parse_locale:    parse an Accept-Language header → supported locale
  - extract_region:  derive ISO 3166-1 alpha-2 country code from a locale tag
  - localise:        select the correct string from a translations map

Requirements: 1.2, 1.3, 1.4, 1.5, 1.7, 5.1, 5.2, 5.3, 5.5, 5.6
"""
from __future__ import annotations

import logging
import os
import re

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SUPPORTED_LOCALES: frozenset[str] = frozenset({"fr-TG", "fr-BJ", "en"})

# Fallback chains: most-specific → base language → English
FALLBACK_CHAINS: dict[str, list[str]] = {
    "fr-TG": ["fr-TG", "fr", "en"],
    "fr-BJ": ["fr-BJ", "fr", "en"],
    "en":    ["en", "fr-TG", "fr"],
    "fr":    ["fr-TG", "fr", "en"],   # backward-compat alias (Req 1.7)
}

# Default locale — overridable via environment variable (Req 1.5)
DEFAULT_LOCALE: str = os.environ.get("DEFAULT_LOCALE", "fr-TG")
if DEFAULT_LOCALE not in SUPPORTED_LOCALES:
    logger.warning(
        "DEFAULT_LOCALE=%r is not a supported locale; falling back to 'fr-TG'",
        DEFAULT_LOCALE,
    )
    DEFAULT_LOCALE = "fr-TG"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LOCALE_ALIAS: dict[str, str] = {"fr": "fr-TG"}

# Regex to extract the primary language tag and optional region subtag
# from a single BCP-47 language range (e.g. "fr-TG", "fr", "en-US;q=0.9")
_TAG_RE = re.compile(r"^([a-zA-Z]{2,8})(?:-([a-zA-Z]{2,3}))?")


def _normalise_tag(tag: str) -> str:
    """Normalise a single BCP-47 language tag to lowercase-UPPERCASE form."""
    tag = tag.strip().split(";")[0].strip()  # strip quality value
    m = _TAG_RE.match(tag)
    if not m:
        return ""
    lang = m.group(1).lower()
    region = m.group(2).upper() if m.group(2) else None
    return f"{lang}-{region}" if region else lang


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_locale(accept_language: str | None) -> str:
    """Parse an Accept-Language header and return the best-matching supported locale.

    Resolution order:
      1. Iterate comma-separated tags in the header (quality values ignored).
      2. For each tag, try an exact match against SUPPORTED_LOCALES.
      3. Try the backward-compat alias map (e.g. "fr" → "fr-TG").
      4. Try a prefix match on the language subtag (e.g. "fr-CI" → "fr-TG").
      5. If nothing matches, return DEFAULT_LOCALE.

    Args:
        accept_language: Value of the HTTP Accept-Language header, or None.

    Returns:
        A locale string that is always a member of SUPPORTED_LOCALES.
    """
    if not accept_language:
        return DEFAULT_LOCALE

    for raw_tag in accept_language.split(","):
        tag = _normalise_tag(raw_tag)
        if not tag:
            continue

        # 1. Exact match
        if tag in SUPPORTED_LOCALES:
            return tag

        # 2. Alias (e.g. "fr" → "fr-TG")
        if tag in _LOCALE_ALIAS:
            return _LOCALE_ALIAS[tag]

        # 3. Language-prefix match: pick the first supported locale whose
        #    language subtag matches (e.g. "fr-CI" → "fr-TG")
        lang_prefix = tag.split("-")[0]
        for supported in sorted(SUPPORTED_LOCALES):  # deterministic order
            if supported.split("-")[0] == lang_prefix:
                return supported

    return DEFAULT_LOCALE


def extract_region(locale: str) -> str | None:
    """Return the ISO 3166-1 alpha-2 country code from a locale tag, or None.

    Examples:
        extract_region("fr-TG") → "TG"
        extract_region("fr-BJ") → "BJ"
        extract_region("en")    → None
        extract_region("fr")    → None

    Args:
        locale: A BCP-47 locale string.

    Returns:
        Two-letter uppercase country code, or None when no region subtag exists.
    """
    if not locale:
        return None
    parts = locale.strip().split("-")
    if len(parts) >= 2 and len(parts[1]) == 2 and parts[1].isalpha():
        return parts[1].upper()
    return None


def localise(content_object: dict, locale: str) -> str | None:
    """Select the correct localised string from a content object's translations map.

    The function walks the fallback chain for the given locale and returns the
    first matching value found in ``content_object['translations']``.  It
    never raises an exception regardless of the locale value or the shape of
    the content object.

    Args:
        content_object: A dict that may contain a ``'translations'`` key whose
            value is a mapping of locale → string.
        locale: The requested locale (BCP-47 string).

    Returns:
        The localised string for the best-matching locale in the fallback
        chain, or ``None`` when no matching key is found.
    """
    try:
        translations: dict = content_object.get("translations", {})
        if not isinstance(translations, dict):
            return None

        chain = FALLBACK_CHAINS.get(locale, FALLBACK_CHAINS.get(DEFAULT_LOCALE, ["fr-TG", "fr", "en"]))

        for fallback_locale in chain:
            value = translations.get(fallback_locale)
            if value is not None:
                return value

        return None
    except Exception:  # noqa: BLE001 — never raise (Req 5.6)
        logger.debug("localise: unexpected error for locale=%r", locale, exc_info=True)
        return None
