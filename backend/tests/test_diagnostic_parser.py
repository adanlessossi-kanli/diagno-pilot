"""Tests for DiagnosticParser — code-quality spec, Task 2.

Covers:
- 2.1  Property 3: DiagnosticParser probability clamping invariant (Hypothesis)
- 2.2  Property 4: DiagnosticParser ICD-10 nullification invariant (Hypothesis)
- 2.3  Property 5: DiagnosticParser always returns at least 3 results (Hypothesis)
- 2.4  Property 6: DiagnosticParser round-trip consistency (Hypothesis)
- 2.5  Property 7: DiagnosticParser is a pure function (Hypothesis)
- 2.6  Unit tests for DiagnosticParser
"""
from __future__ import annotations

import json

from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

from backend.models.consultation import DifferentialDiagnosis
from backend.services.diagnostic_parser import DiagnosticParser, _ICD_CODE_RE

# ---------------------------------------------------------------------------
# Shared strategies
# ---------------------------------------------------------------------------

# Valid ICD-10 codes matching ^[A-Z][0-9]{2}(\.[0-9]{1,4})?$
_valid_icd_st = st.one_of(
    # Without decimal part: e.g. "A01", "Z99"
    st.builds(
        lambda letter, digits: letter + digits,
        letter=st.sampled_from("ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
        digits=st.from_regex(r"[0-9]{2}", fullmatch=True),
    ),
    # With decimal part: e.g. "A01.1", "B54.12"
    st.builds(
        lambda letter, digits, dec: letter + digits + "." + dec,
        letter=st.sampled_from("ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
        digits=st.from_regex(r"[0-9]{2}", fullmatch=True),
        dec=st.from_regex(r"[0-9]{1,4}", fullmatch=True),
    ),
)

# Invalid ICD-10 codes — strings that do NOT match the pattern
_invalid_icd_st = st.text(min_size=1, max_size=20).filter(
    lambda s: not _ICD_CODE_RE.match(s)
)

# Condition names: non-empty, non-whitespace-only strings
_condition_st = st.text(min_size=1, max_size=80).filter(str.strip)

# Probability in [0.0, 1.0]
_valid_prob_st = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)

# Probability outside [0.0, 1.0]
_out_of_range_prob_st = st.one_of(
    st.floats(max_value=-0.001, allow_nan=False, allow_infinity=False),
    st.floats(min_value=1.001, allow_nan=False, allow_infinity=False),
)


def _make_entry(condition: str, probability: float, icd_code: str | None) -> dict:
    return {"condition": condition, "probability": probability, "icd_code": icd_code}


def _json_array(*entries: dict) -> str:
    return json.dumps(list(entries))


# Strategy: LLM answer with ≥3 entries where at least one probability is out of range
def _llm_answer_with_out_of_range_probability():
    return st.builds(
        lambda conditions, probs, bad_prob, icd_codes: _json_array(
            _make_entry(conditions[0], bad_prob, icd_codes[0]),
            _make_entry(conditions[1], probs[0], icd_codes[1]),
            _make_entry(conditions[2], probs[1], icd_codes[2]),
        ),
        conditions=st.lists(_condition_st, min_size=3, max_size=3),
        probs=st.lists(_valid_prob_st, min_size=2, max_size=2),
        bad_prob=_out_of_range_prob_st,
        icd_codes=st.lists(st.one_of(st.none(), _valid_icd_st), min_size=3, max_size=3),
    )


# Strategy: LLM answer with ≥3 entries where at least one icd_code is invalid
def _llm_answer_with_invalid_icd():
    return st.builds(
        lambda conditions, probs, bad_icd: _json_array(
            _make_entry(conditions[0], probs[0], bad_icd),
            _make_entry(conditions[1], probs[1], None),
            _make_entry(conditions[2], probs[2], None),
        ),
        conditions=st.lists(_condition_st, min_size=3, max_size=3),
        probs=st.lists(_valid_prob_st, min_size=3, max_size=3),
        bad_icd=_invalid_icd_st,
    )


# Strategy: valid DifferentialDiagnosis (probability in [0,1], icd_code valid or None)
def _valid_differential_diagnosis_strategy():
    return st.builds(
        DifferentialDiagnosis,
        condition=_condition_st,
        probability=_valid_prob_st,
        icd_code=st.one_of(st.none(), _valid_icd_st),
    )


# ---------------------------------------------------------------------------
# 2.1  Property 3: DiagnosticParser probability clamping invariant
# **Validates: Requirements 2.1, 2.4**
# ---------------------------------------------------------------------------

@given(answer=_llm_answer_with_out_of_range_probability())
@h_settings(max_examples=100)
def test_parser_clamps_probability(answer: str) -> None:
    """Feature: code-quality, Property 3: DiagnosticParser probability clamping invariant.

    For any LLM answer containing a JSON array with out-of-range probability
    values, every DifferentialDiagnosis returned must have probability in [0.0, 1.0].

    **Validates: Requirements 2.1, 2.4**
    """
    results, _pf = DiagnosticParser().parse(answer)
    for d in results:
        assert 0.0 <= d.probability <= 1.0, (
            f"probability {d.probability!r} is outside [0.0, 1.0] for condition {d.condition!r}"
        )


# ---------------------------------------------------------------------------
# 2.2  Property 4: DiagnosticParser ICD-10 nullification invariant
# **Validates: Requirements 2.5**
# ---------------------------------------------------------------------------

@given(answer=_llm_answer_with_invalid_icd())
@h_settings(max_examples=100)
def test_parser_nullifies_invalid_icd(answer: str) -> None:
    """Feature: code-quality, Property 4: DiagnosticParser ICD-10 nullification invariant.

    For any LLM answer containing a JSON array with invalid icd_code values,
    the corresponding DifferentialDiagnosis objects must have icd_code = None.

    **Validates: Requirements 2.5**
    """
    results, _pf = DiagnosticParser().parse(answer)
    for d in results:
        if d.icd_code is not None:
            assert _ICD_CODE_RE.match(d.icd_code), (
                f"icd_code {d.icd_code!r} does not match ICD-10 pattern"
            )


# ---------------------------------------------------------------------------
# 2.3  Property 5: DiagnosticParser always returns at least 3 results
# **Validates: Requirements 2.2, 2.3, 2.6**
# ---------------------------------------------------------------------------

@given(answer=st.text())
@h_settings(max_examples=100)
def test_parser_always_returns_at_least_3(answer: str) -> None:
    """Feature: code-quality, Property 5: DiagnosticParser always returns at least 3 results.

    For any string input — including empty strings, non-JSON content, and JSON
    arrays with fewer than 3 valid entries — the returned list must have length >= 3.

    **Validates: Requirements 2.2, 2.3, 2.6**
    """
    results, _pf = DiagnosticParser().parse(answer)
    assert len(results) >= 3, (
        f"Expected at least 3 results, got {len(results)} for input {answer!r}"
    )


# ---------------------------------------------------------------------------
# 2.4  Property 6: DiagnosticParser round-trip consistency
# **Validates: Requirements 2.7**
# ---------------------------------------------------------------------------

@given(diagnosis=_valid_differential_diagnosis_strategy())
@h_settings(max_examples=100)
def test_parser_round_trip(diagnosis: DifferentialDiagnosis) -> None:
    """Feature: code-quality, Property 6: DiagnosticParser round-trip.

    Serializing a valid DifferentialDiagnosis to a JSON array string and
    passing it to DiagnosticParser.parse() must return a list whose first
    element is equivalent to the original object.

    **Validates: Requirements 2.7**
    """
    # Build a JSON array with 3 copies so the parser returns real results (not placeholders)
    entry = {
        "condition": diagnosis.condition,
        "probability": diagnosis.probability,
        "icd_code": diagnosis.icd_code,
    }
    serialized = json.dumps([entry, entry, entry])
    results, _pf = DiagnosticParser().parse(serialized)

    # The highest-probability entry should match (all three are identical, so first is fine)
    assert results[0].condition == diagnosis.condition
    assert results[0].probability == diagnosis.probability
    assert results[0].icd_code == diagnosis.icd_code


# ---------------------------------------------------------------------------
# 2.5  Property 7: DiagnosticParser is a pure function
# **Validates: Requirements 2.8**
# ---------------------------------------------------------------------------

@given(answer=st.text())
@h_settings(max_examples=100)
def test_parser_pure(answer: str) -> None:
    """Feature: code-quality, Property 7: DiagnosticParser is a pure function.

    Calling DiagnosticParser.parse() twice with the same argument must return
    equivalent lists.

    **Validates: Requirements 2.8**
    """
    p = DiagnosticParser()
    r1, pf1 = p.parse(answer)
    r2, pf2 = p.parse(answer)
    assert pf1 == pf2, "parse_failed flag must be deterministic"
    assert [(d.condition, d.probability, d.icd_code) for d in r1] == \
           [(d.condition, d.probability, d.icd_code) for d in r2], (
        "DiagnosticParser.parse() returned different results for the same input — "
        "it must be a pure, side-effect-free function."
    )


# ---------------------------------------------------------------------------
# 2.6  Unit tests for DiagnosticParser
# Requirements: 2.2, 2.3, 2.6
# ---------------------------------------------------------------------------

def _make_json_array(entries: list[dict]) -> str:
    return json.dumps(entries)


def test_parse_well_formed_3_entries_sorted_descending() -> None:
    """Well-formed JSON array of 3+ entries must be returned sorted by descending probability."""
    entries = [
        {"condition": "Malaria", "probability": 0.3, "icd_code": "B54"},
        {"condition": "Typhoid", "probability": 0.7, "icd_code": "A01.0"},
        {"condition": "Dengue", "probability": 0.5, "icd_code": "A90"},
    ]
    results, parse_failed = DiagnosticParser().parse(_make_json_array(entries))

    assert not parse_failed
    assert len(results) >= 3
    assert results[0].condition == "Typhoid"
    assert results[0].probability == 0.7
    assert results[1].condition == "Dengue"
    assert results[1].probability == 0.5
    assert results[2].condition == "Malaria"
    assert results[2].probability == 0.3


def test_parse_more_than_3_entries_sorted() -> None:
    """JSON array with 5 entries must be returned sorted by descending probability."""
    entries = [
        {"condition": "A", "probability": 0.1, "icd_code": None},
        {"condition": "B", "probability": 0.9, "icd_code": None},
        {"condition": "C", "probability": 0.5, "icd_code": None},
        {"condition": "D", "probability": 0.3, "icd_code": None},
        {"condition": "E", "probability": 0.7, "icd_code": None},
    ]
    results, parse_failed = DiagnosticParser().parse(_make_json_array(entries))

    assert not parse_failed
    assert len(results) == 5
    probs = [d.probability for d in results]
    assert probs == sorted(probs, reverse=True)


def test_parse_0_entries_returns_3_placeholders() -> None:
    """Empty JSON array must return 3 placeholder DifferentialDiagnosis objects."""
    results, parse_failed = DiagnosticParser().parse("[]")

    assert parse_failed
    assert len(results) == 3
    for d in results:
        assert d.probability == 0.0
        assert d.icd_code is None


def test_parse_1_entry_returns_3_placeholders() -> None:
    """JSON array with 1 entry must return 3 placeholder objects."""
    entries = [{"condition": "Malaria", "probability": 0.8, "icd_code": "B54"}]
    results, parse_failed = DiagnosticParser().parse(_make_json_array(entries))

    assert parse_failed
    assert len(results) == 3
    for d in results:
        assert d.probability == 0.0
        assert d.icd_code is None


def test_parse_2_entries_returns_3_placeholders() -> None:
    """JSON array with 2 entries must return 3 placeholder objects."""
    entries = [
        {"condition": "Malaria", "probability": 0.8, "icd_code": "B54"},
        {"condition": "Typhoid", "probability": 0.6, "icd_code": "A01.0"},
    ]
    results, parse_failed = DiagnosticParser().parse(_make_json_array(entries))

    assert parse_failed
    assert len(results) == 3
    for d in results:
        assert d.probability == 0.0
        assert d.icd_code is None


def test_parse_non_json_returns_3_placeholders() -> None:
    """Non-JSON input must return 3 placeholder objects."""
    results, parse_failed = DiagnosticParser().parse("This is not JSON at all.")

    assert parse_failed
    assert len(results) == 3
    for d in results:
        assert d.probability == 0.0
        assert d.icd_code is None


def test_parse_empty_string_returns_3_placeholders() -> None:
    """Empty string must return 3 placeholder objects."""
    results, parse_failed = DiagnosticParser().parse("")

    assert parse_failed
    assert len(results) == 3
    for d in results:
        assert d.probability == 0.0
        assert d.icd_code is None


def test_parse_clamps_probability_above_1() -> None:
    """Probability > 1.0 must be clamped to 1.0."""
    entries = [
        {"condition": "A", "probability": 1.5, "icd_code": None},
        {"condition": "B", "probability": 0.5, "icd_code": None},
        {"condition": "C", "probability": 0.3, "icd_code": None},
    ]
    results, parse_failed = DiagnosticParser().parse(_make_json_array(entries))

    assert not parse_failed
    assert all(0.0 <= d.probability <= 1.0 for d in results)
    # The clamped entry should be 1.0
    assert results[0].probability == 1.0


def test_parse_clamps_probability_below_0() -> None:
    """Probability < 0.0 must be clamped to 0.0."""
    entries = [
        {"condition": "A", "probability": -0.5, "icd_code": None},
        {"condition": "B", "probability": 0.5, "icd_code": None},
        {"condition": "C", "probability": 0.3, "icd_code": None},
    ]
    results, _pf = DiagnosticParser().parse(_make_json_array(entries))

    assert all(0.0 <= d.probability <= 1.0 for d in results)


def test_parse_nullifies_invalid_icd_code() -> None:
    """Invalid ICD-10 code must be set to None."""
    entries = [
        {"condition": "A", "probability": 0.8, "icd_code": "not-valid"},
        {"condition": "B", "probability": 0.5, "icd_code": "B54"},
        {"condition": "C", "probability": 0.3, "icd_code": "123"},
    ]
    results, _pf = DiagnosticParser().parse(_make_json_array(entries))

    # "not-valid" and "123" are invalid; "B54" is valid
    conditions_map = {d.condition: d for d in results}
    assert conditions_map["A"].icd_code is None
    assert conditions_map["B"].icd_code == "B54"
    assert conditions_map["C"].icd_code is None


def test_parse_valid_icd_codes_preserved() -> None:
    """Valid ICD-10 codes must be preserved as-is."""
    entries = [
        {"condition": "A", "probability": 0.8, "icd_code": "B54"},
        {"condition": "B", "probability": 0.5, "icd_code": "A01.0"},
        {"condition": "C", "probability": 0.3, "icd_code": "Z99.1234"},
    ]
    results, _pf = DiagnosticParser().parse(_make_json_array(entries))

    conditions_map = {d.condition: d for d in results}
    assert conditions_map["A"].icd_code == "B54"
    assert conditions_map["B"].icd_code == "A01.0"
    assert conditions_map["C"].icd_code == "Z99.1234"


# ---------------------------------------------------------------------------
# Property 8: Diagnostic parser failure signaling
# Feature: chat-diagnosis-improvements
# **Validates: Requirements 14.1, 14.4**
# ---------------------------------------------------------------------------

_locale_st = st.sampled_from(["fr-TG", "fr-BJ", "fr", "en"])

# Strategy: LLM answer with ≥3 valid entries (parse should succeed)
_success_answer_st = st.builds(
    lambda conditions, probs: _json_array(
        _make_entry(conditions[0], probs[0], None),
        _make_entry(conditions[1], probs[1], None),
        _make_entry(conditions[2], probs[2], None),
    ),
    conditions=st.lists(_condition_st, min_size=3, max_size=3),
    probs=st.lists(_valid_prob_st, min_size=3, max_size=3),
)

# Strategy: LLM answer with <3 valid entries (parse should fail)
_failure_answer_st = st.one_of(
    # Empty array
    st.just("[]"),
    # 1 entry
    st.builds(
        lambda c, p: _json_array(_make_entry(c, p, None)),
        c=_condition_st,
        p=_valid_prob_st,
    ),
    # 2 entries
    st.builds(
        lambda cs, ps: _json_array(
            _make_entry(cs[0], ps[0], None),
            _make_entry(cs[1], ps[1], None),
        ),
        cs=st.lists(_condition_st, min_size=2, max_size=2),
        ps=st.lists(_valid_prob_st, min_size=2, max_size=2),
    ),
    # Non-JSON
    st.text(min_size=0, max_size=100).filter(lambda s: "[" not in s),
)


@given(answer=_success_answer_st, locale=_locale_st)
@h_settings(max_examples=100)
def test_parser_failure_signaling_success(answer: str, locale: str) -> None:
    """Feature: chat-diagnosis-improvements, Property 8: Diagnostic parser failure signaling.

    When ≥3 valid diagnoses are extracted, parse_failed SHALL be False.

    **Validates: Requirements 14.1, 14.4**
    """
    results, parse_failed = DiagnosticParser().parse(answer, locale=locale)
    assert not parse_failed, (
        f"parse_failed should be False when ≥3 diagnoses extracted, got True for locale={locale!r}"
    )
    assert len(results) >= 3


@given(answer=_failure_answer_st, locale=_locale_st)
@h_settings(max_examples=100)
def test_parser_failure_signaling_failure(answer: str, locale: str) -> None:
    """Feature: chat-diagnosis-improvements, Property 8: Diagnostic parser failure signaling.

    When <3 valid diagnoses are extracted, parse_failed SHALL be True and
    placeholders SHALL use locale-appropriate text.

    **Validates: Requirements 14.1, 14.4**
    """
    results, parse_failed = DiagnosticParser().parse(answer, locale=locale)
    assert parse_failed, (
        f"parse_failed should be True when <3 diagnoses extracted, got False for input={answer!r}"
    )
    assert len(results) == 3

    expected_text = "Diagnostic indisponible" if locale.startswith("fr") else "Diagnosis unavailable"
    for d in results:
        assert d.condition == expected_text, (
            f"Expected placeholder text {expected_text!r} for locale={locale!r}, got {d.condition!r}"
        )
        assert d.probability == 0.0
        assert d.icd_code is None
