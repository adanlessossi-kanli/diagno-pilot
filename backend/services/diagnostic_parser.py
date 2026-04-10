"""DiagnosticParser — parses and validates LLM JSON responses into DifferentialDiagnosis objects."""
from __future__ import annotations

import json
import logging
import re

from backend.models.consultation import DifferentialDiagnosis

logger = logging.getLogger(__name__)

_ICD_CODE_RE = re.compile(r"^[A-Z][0-9]{2}(\.[0-9]{1,4})?$")

_PLACEHOLDER = DifferentialDiagnosis(
    condition="Diagnosis unavailable",
    probability=0.0,
    icd_code=None,
)


class DiagnosticParser:
    """Stateless LLM response parser for the differential diagnosis pipeline.

    Sole responsibility: transform a raw LLM answer string into a validated
    list of :class:`~backend.models.consultation.DifferentialDiagnosis` objects.
    The class performs no I/O, no HTTP calls, and no database access — it is a
    pure function wrapped in a class.

    Expected JSON format from the LLM::

        [
          {"condition": "<name>", "probability": <0.0-1.0>, "icd_code": "<ICD-10>"},
          ...
        ]

    Fallback behaviour: when the LLM answer contains no parseable JSON array,
    or the array has fewer than 3 valid entries, a warning is logged and a list
    of 3 placeholder ``DifferentialDiagnosis`` objects (``probability=0.0``,
    ``icd_code=None``) is returned.  The parser never raises an exception to
    the caller.
    """

    @staticmethod
    def _clean_llm_response(raw: str) -> str:
        """Strip markdown fences, <think> blocks, and preamble/postamble."""
        # 1. Remove <think>...</think> blocks (case-insensitive)
        cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL | re.IGNORECASE)
        # 2. Remove markdown code fences (```json, ```JSON, ```)
        cleaned = re.sub(r"```(?:json|JSON)?\s*\n?", "", cleaned)
        # 3. Strip preamble before first [ and postamble after last ]
        first_bracket = cleaned.find("[")
        last_bracket = cleaned.rfind("]")
        if first_bracket != -1 and last_bracket != -1 and last_bracket > first_bracket:
            cleaned = cleaned[first_bracket:last_bracket + 1]
        return cleaned.strip()

    @staticmethod
    def _repair_truncated_json(text: str) -> list[dict] | None:
        """Attempt to salvage complete JSON objects from a truncated array.

        When the LLM hits its token limit, the JSON array is cut mid-object.
        This method finds all complete ``{...}`` blocks within the text and
        parses them individually.  Returns a list of dicts or ``None`` if
        nothing could be salvaged.
        """
        results: list[dict] = []
        depth = 0
        start = -1
        for i, ch in enumerate(text):
            if ch == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0 and start != -1:
                    fragment = text[start : i + 1]
                    try:
                        obj = json.loads(fragment)
                        if isinstance(obj, dict):
                            results.append(obj)
                    except (json.JSONDecodeError, ValueError):
                        pass
                    start = -1
        return results if results else None

    def _extract_diagnoses(self, raw: list) -> list[DifferentialDiagnosis]:
        """Convert a list of dicts into validated DifferentialDiagnosis objects."""
        diagnoses: list[DifferentialDiagnosis] = []
        for i, item in enumerate(raw):
            if not isinstance(item, dict):
                continue
            condition = item.get("condition", "Unknown")
            raw_prob = float(item.get("probability", 0.0))
            icd_code = item.get("icd_code") or None

            # Clamp probability
            if raw_prob < 0.0 or raw_prob > 1.0:
                logger.warning(
                    "diagnosis[%d].probability=%r out of [0, 1]; clamping.", i, raw_prob
                )
                raw_prob = max(0.0, min(1.0, raw_prob))

            # Nullify invalid ICD-10 code
            if icd_code is not None and not _ICD_CODE_RE.match(icd_code):
                logger.warning(
                    "diagnosis[%d].icd_code=%r does not match ICD-10 pattern; nullifying.",
                    i,
                    icd_code,
                )
                icd_code = None

            diagnoses.append(
                DifferentialDiagnosis(
                    condition=condition,
                    probability=raw_prob,
                    icd_code=icd_code,
                    matching_symptoms=item.get("matching_symptoms") or item.get("concordant_symptoms") or [],
                )
            )
        return diagnoses

    def parse(self, llm_answer: str, locale: str = "en") -> tuple[list[DifferentialDiagnosis], bool]:
        """Parse *llm_answer* and return a tuple of (diagnoses, parse_failed).

        Pipeline:

        1. Clean the response (strip markdown, think blocks, preamble).
        2. Try ``json.loads`` on the extracted JSON array.
        3. If that fails (e.g. truncated output), attempt to repair by
           extracting individual complete ``{...}`` objects.
        4. For each entry: clamp ``probability`` to ``[0.0, 1.0]``; nullify
           ``icd_code`` if it does not match ``_ICD_CODE_RE``.
        5. If ≥ 3 valid entries: sort by descending probability and return
           ``(diagnoses, False)``.
        6. Otherwise: return 3 locale-aware placeholders with
           ``parse_failed=True``.

        Args:
            llm_answer: Raw string returned by the LLM / RAGService.
            locale: Locale string used for placeholder text (e.g. "fr-TG", "en").

        Returns:
            A tuple of (diagnoses, parse_failed) where diagnoses is a list of
            at least 3 :class:`~backend.models.consultation.DifferentialDiagnosis`
            objects sorted by descending probability (or 3 placeholders on
            failure), and parse_failed is True when <3 valid diagnoses were
            extracted.
        """
        llm_answer = self._clean_llm_response(llm_answer)
        json_match = re.search(r"\[.*\]", llm_answer, re.DOTALL)

        raw_items: list | None = None

        if json_match:
            try:
                raw_items = json.loads(json_match.group())
            except (json.JSONDecodeError, ValueError, TypeError) as exc:
                logger.warning("Failed to parse JSON diagnoses: %s", exc)
                # Attempt repair on the matched text
                raw_items = self._repair_truncated_json(json_match.group())
                if raw_items:
                    logger.info(
                        "Repaired truncated JSON: salvaged %d complete objects.", len(raw_items)
                    )

        # If no [...] match found, try repair on the full cleaned text
        # (handles cases where the closing ] was truncated entirely)
        if raw_items is None:
            raw_items = self._repair_truncated_json(llm_answer)
            if raw_items:
                logger.info(
                    "Repaired truncated JSON (no array brackets): salvaged %d complete objects.",
                    len(raw_items),
                )

        if raw_items is not None:
            diagnoses = self._extract_diagnoses(raw_items)
            if len(diagnoses) >= 3:
                return sorted(diagnoses, key=lambda d: d.probability, reverse=True), False

        logger.warning(
            "Could not parse ≥3 diagnoses from LLM response; returning fallback placeholders."
        )
        placeholder_text = "Diagnostic indisponible" if locale.startswith("fr") else "Diagnosis unavailable"
        return [
            DifferentialDiagnosis(condition=placeholder_text, probability=0.0, icd_code=None),
            DifferentialDiagnosis(condition=placeholder_text, probability=0.0, icd_code=None),
            DifferentialDiagnosis(condition=placeholder_text, probability=0.0, icd_code=None),
        ], True
