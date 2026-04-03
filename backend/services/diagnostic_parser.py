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

    def parse(self, llm_answer: str) -> list[DifferentialDiagnosis]:
        """Parse *llm_answer* and return a list of at least 3 DifferentialDiagnosis objects.

        Pipeline:

        1. Search for a JSON array using ``re.search(r"\\[.*\\]", ..., re.DOTALL)``.
        2. Deserialize with ``json.loads``.
        3. For each entry: clamp ``probability`` to ``[0.0, 1.0]`` (log warning
           if clamped); nullify ``icd_code`` if it does not match
           ``_ICD_CODE_RE`` (log warning if nullified).
        4. If ≥ 3 valid entries: sort by descending probability and return.
        5. Otherwise: log a warning and return 3 placeholder objects with
           ``probability=0.0`` and ``icd_code=None``.

        Args:
            llm_answer: Raw string returned by the LLM / RAGService.

        Returns:
            A list of at least 3 :class:`~backend.models.consultation.DifferentialDiagnosis`
            objects sorted by descending probability (or 3 placeholders on
            failure).
        """
        json_match = re.search(r"\[.*\]", llm_answer, re.DOTALL)
        if json_match:
            try:
                raw = json.loads(json_match.group())
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

                if len(diagnoses) >= 3:
                    return sorted(diagnoses, key=lambda d: d.probability, reverse=True)

            except (json.JSONDecodeError, ValueError, TypeError) as exc:
                logger.warning("Failed to parse JSON diagnoses: %s", exc)

        logger.warning(
            "Could not parse ≥3 diagnoses from LLM response; returning fallback placeholders."
        )
        return [
            DifferentialDiagnosis(condition="Diagnosis unavailable", probability=0.0, icd_code=None),
            DifferentialDiagnosis(condition="Diagnosis unavailable", probability=0.0, icd_code=None),
            DifferentialDiagnosis(condition="Diagnosis unavailable", probability=0.0, icd_code=None),
        ]
