# Implementation Plan

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** — Cross-Encoder Scores Discarded and Sources Misordered
  - **CRITICAL**: This test MUST FAIL on unfixed code — failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior — it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the bug exists
  - **Scoped PBT Approach**: Generate chunk lists where vector `score` order ≠ cross-encoder order; scope to cases where `cross_encoder_rerank` succeeds
  - Test file: `backend/tests/test_chat_source_semantic_bug.py`
  - Using Hypothesis, generate lists of chunk dicts with random `score` values and a mock cross-encoder that assigns different `ce_score` values
  - Property assertions (expected behavior — will fail on unfixed code):
    1. After `cross_encoder_rerank(query, chunks)`, every returned chunk has a `"ce_score"` key (validates Req 2.1)
    2. `filter_by_similarity()` retains chunks whose `ce_score` ≥ threshold even if `score` < threshold (validates Req 2.4)
    3. In `LlamaIndexPipeline.query()`, sources are ordered by `ce_score` descending, not by stale `score` (validates Req 2.2)
    4. LLM context chunks are a subset of the source chunks (validates Req 2.3)
    5. Confidence equals the mean of `ce_score` values of the source chunks (validates Req 2.5)
  - Run test on UNFIXED code
  - **EXPECTED OUTCOME**: Test FAILS (this is correct — it proves the bug exists)
  - Document counterexamples found (e.g. "chunk with ce_score 0.92 but vector score 0.55 is not the top source")
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 2.4, 2.5_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** — Fallback and Non-Reranked Paths Unchanged
  - **IMPORTANT**: Follow observation-first methodology
  - Test file: `backend/tests/test_chat_source_semantic_preservation.py`
  - Observe behavior on UNFIXED code for non-buggy inputs (cross-encoder unavailable, no chunks, cached responses):
    - Observe: `cross_encoder_rerank(query, chunks)` returns chunks unchanged when cross-encoder import fails
    - Observe: `filter_by_similarity(chunks)` filters by `score` field when no `ce_score` is present
    - Observe: `LlamaIndexPipeline.query()` returns no-source LLM response when chunks list is empty
    - Observe: cached responses are returned without re-running retrieval
  - Write Hypothesis property-based tests capturing observed behavior:
    1. For all chunk lists where cross-encoder is unavailable, `cross_encoder_rerank` returns the input list unchanged (validates Req 3.1)
    2. For all chunk lists without `ce_score`, `filter_by_similarity` filters identically to original (by `score` field) (validates Req 3.1, 3.5)
    3. For empty chunk retrieval, pipeline returns answer with `sources=[]` and `confidence_score=None` (validates Req 3.2)
    4. Region pre-filtering continues to work (validates Req 3.3)
  - Run tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (this confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 3. Fix cross-encoder score propagation and source/LLM alignment

  - [x] 3.1 Store `ce_score` on each chunk in `cross_encoder_rerank()`
    - File: `backend/services/index_manager.py`, function `cross_encoder_rerank()`
    - After `cross_encoder.predict(pairs)`, write `chunk["ce_score"] = float(score)` for each `(score, chunk)` pair before sorting and returning
    - The returned list must be sorted by `ce_score` descending (existing sort logic) AND each chunk must carry the `ce_score` field
    - _Bug_Condition: isBugCondition(chunks, reranked_chunks) — cross_encoder succeeds AND chunks have NO ce_score field_
    - _Expected_Behavior: all returned chunks have ce_score field with float value from cross-encoder_
    - _Preservation: when cross-encoder is unavailable, return chunks unchanged (no ce_score added)_
    - _Requirements: 2.1_

  - [x] 3.2 Update `filter_by_similarity()` to prefer `ce_score`
    - File: `backend/services/index_manager.py`, function `filter_by_similarity()`
    - Change filter to read `chunk.get("ce_score", chunk.get("score", 1.0))` so cross-encoder score is used for threshold comparison when available
    - When `ce_score` is absent, behavior is identical to original (falls back to `score`)
    - _Bug_Condition: filter uses stale vector score after cross-encoder reranking_
    - _Expected_Behavior: filter uses ce_score when present, score otherwise_
    - _Preservation: chunks without ce_score are filtered by score identically to original_
    - _Requirements: 2.4_

  - [x] 3.3 Unify source and LLM chunk selection in `LlamaIndexPipeline.query()`
    - File: `backend/services/llamaindex_pipeline.py`, function `query()`
    - Sort chunks by `ce_score` (falling back to `score`) and take top `min(top_k, 5)` as `top_chunks`
    - Build sources from `top_chunks`
    - Build LLM context from `top_chunks[:3]` instead of `chunks[:3]`
    - Compute confidence as `mean(chunk.get("ce_score", chunk.get("score", 0.0)) for chunk in top_chunks)` instead of averaging all chunks' stale vector scores
    - _Bug_Condition: sources sorted by stale score, LLM context from positional slice, confidence from all chunks_
    - _Expected_Behavior: single top_chunks list drives sources, LLM context, and confidence; all use ce_score when available_
    - _Preservation: when ce_score absent, sorting falls back to score — identical to original for non-reranked paths_
    - _Requirements: 2.2, 2.3, 2.5_

  - [x] 3.4 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** — Cross-Encoder Scores Propagated and Sources Correctly Ordered
    - **IMPORTANT**: Re-run the SAME test from task 1 — do NOT write a new test
    - The test from task 1 encodes the expected behavior
    - When this test passes, it confirms the expected behavior is satisfied
    - Run bug condition exploration test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [x] 3.5 Verify preservation tests still pass
    - **Property 2: Preservation** — Fallback and Non-Reranked Paths Unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 2 — do NOT write new tests
    - Run preservation property tests from step 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
    - Confirm all tests still pass after fix (no regressions)

- [x] 4. Checkpoint — Ensure all tests pass
  - Run full test suite to confirm no regressions
  - Ensure both Property 1 (bug condition) and Property 2 (preservation) tests pass
  - Ask the user if questions arise
