# Implementation Plan

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - confidence_score Not Populated From Chunk Scores
  - **IMPORTANT**: Write this property-based test BEFORE implementing the fix
  - **CRITICAL**: This test MUST FAIL on unfixed code — failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior — it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate `DocumentSource.confidence_score` is `None` despite chunks having valid `ce_score`/`score` values
  - **Scoped PBT Approach**: Use Hypothesis to generate chunk dicts with `ce_score` and/or `score` fields (floats >= 0.3 to pass threshold). Scope to the concrete bug: `DocumentSource` construction omits `confidence_score`
  - **Test file**: `backend/tests/test_confidence_score_bug.py`
  - **Test infrastructure**: Reuse the `_make_pipeline` pattern from `backend/tests/test_pipeline_stream.py` — mock `_embedder`, `_index`, `_llm`, and `cache_service`
  - **Property**: For all chunk dicts where `ce_score` or `score` is present and >= `SOURCE_RELEVANCE_THRESHOLD`, the resulting `DocumentSource.confidence_score` SHALL equal `float(chunk.get("ce_score", chunk.get("score", 0.0)))` and SHALL NOT be `None`
  - **Test both paths**: Test `query()` and `query_stream()` — both have the same bug in their `DocumentSource(...)` list comprehension
  - **Also test fallback**: Generate chunks with only `score` (no `ce_score`) to verify fallback behavior
  - Run test on UNFIXED code
  - **EXPECTED OUTCOME**: Test FAILS (confidence_score is None for all sources — this proves the bug exists)
  - Document counterexamples found (e.g., "chunk with ce_score=0.85 produces DocumentSource with confidence_score=None")
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 2.1_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Above-Threshold Sources and Empty Retrievals Unchanged
  - **IMPORTANT**: Follow observation-first methodology
  - **Test file**: `backend/tests/test_confidence_score_preservation.py` (backend) and optionally inline in the bug test file for frontend filter logic
  - **Observe on UNFIXED code**:
    - Observe: `query_stream()` with chunks all having `ce_score >= 0.3` returns all sources in the `done` event (count matches chunk count)
    - Observe: `query_stream()` with no chunks returns empty `sources` list
    - Observe: `query()` with all above-threshold chunks returns all sources
    - Observe: Frontend filter with all `confidence_score >= 0.3` returns the full list unchanged
    - Observe: Frontend filter with `confidence_score == null` (legacy cached data) retains the source
  - **Property-based tests**:
    - Generate random lists of `DocumentSource` objects where all `confidence_score >= 0.3` — verify frontend filter returns the full list unchanged (identity)
    - Generate random lists with `confidence_score = None` mixed in — verify filter retains `None`-scored sources (backward compat)
    - Generate chunk lists where all scores >= 0.3 — verify `query()`/`query_stream()` returns same number of sources as chunks (no sources dropped)
    - Generate empty chunk lists — verify empty sources list returned
  - Run tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.5_

- [x] 3. Fix for confidence_score not populated on DocumentSource objects

  - [x] 3.1 Add `confidence_score` to `DocumentSource` construction in `query()`
    - In `backend/services/llamaindex_pipeline.py`, locate the `sources = [DocumentSource(...) for c in top_chunks]` list comprehension in `query()` (~line 200)
    - Add `confidence_score=float(c.get("ce_score", c.get("score", 0.0)))` to the `DocumentSource(...)` constructor call
    - This reuses the same score expression already used for sorting and threshold filtering
    - _Bug_Condition: isBugCondition(input) where source.confidence_score IS NULL AND chunk has ce_score or score_
    - _Expected_Behavior: source.confidence_score = float(chunk.get("ce_score", chunk.get("score", 0.0))) for every DocumentSource_
    - _Preservation: All above-threshold sources continue to appear; empty retrievals return empty sources list_
    - _Requirements: 1.1, 2.1, 3.1, 3.2_

  - [x] 3.2 Add `confidence_score` to `DocumentSource` construction in `query_stream()`
    - In `backend/services/llamaindex_pipeline.py`, locate the identical `sources = [DocumentSource(...) for c in top_chunks]` list comprehension in `query_stream()` (~line 350)
    - Add `confidence_score=float(c.get("ce_score", c.get("score", 0.0)))` to the `DocumentSource(...)` constructor call
    - Identical change to 3.1 — both methods have the same bug
    - _Bug_Condition: isBugCondition(input) where source.confidence_score IS NULL AND chunk has ce_score or score_
    - _Expected_Behavior: source.confidence_score = float(chunk.get("ce_score", chunk.get("score", 0.0))) for every DocumentSource_
    - _Preservation: Streaming done event sources carry populated scores; cached responses include scores_
    - _Requirements: 1.1, 2.1, 3.4_

  - [x] 3.3 Add defense-in-depth filter in `SourcesPanel` component
    - In `apps/web/src/app/[locale]/chat/page.tsx`, in the `SourcesPanel` component
    - Add filter before the `if (sources.length === 0) return null;` guard: `const filtered = sources.filter(s => s.confidence_score == null || s.confidence_score >= 0.3);`
    - The `== null` loose equality intentionally matches both `null` and `undefined` for backward compat with legacy cached data
    - Replace `sources` with `filtered` in the count display `({filtered.length})` and the `.map()` rendering loop
    - Update the early return to use `filtered`: `if (filtered.length === 0) return null;`
    - _Bug_Condition: Frontend renders sources without checking confidence_score_
    - _Expected_Behavior: Only sources with confidence_score >= 0.3 or null/undefined are rendered; panel hidden when all filtered out_
    - _Preservation: Sources with confidence_score >= 0.3 continue to render as CitationChip components; diagnose page unaffected (chat-only filter)_
    - _Requirements: 2.2, 2.3, 3.5, 3.6_

  - [x] 3.4 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - confidence_score Populated From Chunk Scores
    - **IMPORTANT**: Re-run the SAME test from task 1 — do NOT write a new test
    - The test from task 1 encodes the expected behavior (confidence_score equals chunk's ce_score/score)
    - When this test passes, it confirms the expected behavior is satisfied
    - Run bug condition exploration test from step 1: `pytest backend/tests/test_confidence_score_bug.py -v`
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed — confidence_score is now populated)
    - _Requirements: 2.1_

  - [x] 3.5 Verify preservation tests still pass
    - **Property 2: Preservation** - Above-Threshold Sources and Empty Retrievals Unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 2 — do NOT write new tests
    - Run preservation property tests from step 2: `pytest backend/tests/test_confidence_score_preservation.py -v`
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions — above-threshold sources still displayed, empty retrievals still return empty list)
    - Confirm all tests still pass after fix (no regressions)

- [x] 4. Checkpoint - Ensure all tests pass
  - Run full test suite: `pytest backend/tests/test_confidence_score_bug.py backend/tests/test_confidence_score_preservation.py backend/tests/test_pipeline_stream.py -v`
  - Verify all existing tests in `test_pipeline_stream.py` still pass (no regressions to streaming behavior)
  - Ensure all tests pass, ask the user if questions arise
