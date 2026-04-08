# Chat Source Semantic Fix — Bugfix Design

## Overview

After cross-encoder reranking, the reranking scores are silently discarded. Every downstream consumer — source building, LLM context construction, similarity filtering, and confidence scoring — continues to operate on stale vector-search scores or arbitrary positional slices. The fix propagates cross-encoder scores through the pipeline so that a single, consistently-ranked chunk list drives sources, LLM grounding, filtering, and confidence.

## Glossary

- **Bug_Condition (C)**: The cross-encoder has reranked chunks (i.e. `cross_encoder_rerank` succeeded), yet downstream code sorts or filters by the original vector `score` field instead of the cross-encoder score.
- **Property (P)**: After reranking, sources, LLM context, similarity filtering, and confidence all use the cross-encoder ranking/scores.
- **Preservation**: When the cross-encoder is unavailable (fallback path), or when no chunks are retrieved, or when results are cached, existing behaviour must remain identical.
- **`cross_encoder_rerank()`**: Function in `backend/services/index_manager.py` that re-orders chunks using a cross-encoder model but currently discards the scores.
- **`filter_by_similarity()`**: Function in `backend/services/index_manager.py` that drops chunks below a cosine-score threshold — currently blind to cross-encoder scores.
- **`LlamaIndexPipeline.query()`**: Main RAG entry-point in `backend/services/llamaindex_pipeline.py` that builds sources from `top_chunks`, LLM context from `chunks[:3]`, and confidence from all `chunks`.

## Bug Details

### Bug Condition

The bug manifests when the cross-encoder successfully reranks chunks but its scores are not stored, causing every downstream stage to use stale vector-search scores or positional slices that no longer reflect semantic relevance.

**Formal Specification:**
```
FUNCTION isBugCondition(chunks, reranked_chunks)
  INPUT: chunks      — list of chunk dicts returned by hybrid retrieval
         reranked_chunks — list of chunk dicts after cross_encoder_rerank()
  OUTPUT: boolean

  RETURN cross_encoder_succeeded(reranked_chunks)
         AND reranked_chunks[i] has NO "ce_score" field for any i
         AND downstream_sorts_by(reranked_chunks, key="score")
END FUNCTION
```

Three sub-conditions cause observable defects:

1. **Source / LLM divergence**: Sources are built from `sorted(chunks, key=score)[:5]` while LLM context uses `chunks[:3]`. After reranking the positional order differs from the score order, so the two sets diverge.
2. **Similarity filter on wrong score**: `filter_by_similarity` compares `chunk["score"]` (vector score) against the threshold, potentially dropping chunks the cross-encoder ranked highly.
3. **Confidence on wrong population**: Confidence averages `score` over *all* chunks instead of the scores of the 5 chunks actually shown as sources.

### Examples

- **Example 1 — Source divergence**: Cross-encoder ranks chunk A as #1 (ce_score 0.92) but its vector score is 0.55. Chunk B has vector score 0.88 but ce_score 0.31. Current code picks B as the top source; correct code picks A.
- **Example 2 — LLM/source mismatch**: After reranking, `chunks[0:3]` = [A, C, D] (positional). `sorted(chunks, key=score)[:5]` = [B, E, A, C, F] (vector score). The LLM reads A, C, D but the user sees B, E, A, C, F as citations.
- **Example 3 — Filter drops relevant chunk**: Chunk G has vector score 0.38 (below threshold 0.5) but ce_score 0.87. `filter_by_similarity` drops G even though the cross-encoder considers it highly relevant.
- **Example 4 — Confidence inflation**: Confidence averages vector scores of all 5+ chunks (e.g. 0.82) instead of the ce_scores of the 5 source chunks (e.g. 0.61), giving the user a misleadingly high confidence.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- When the cross-encoder is unavailable (import error, model failure), the system falls back gracefully and returns chunks in their pre-rerank order without crashing (Req 3.1)
- When no chunks are retrieved, the system calls the LLM with general medical knowledge and returns a response with no sources (Req 3.2)
- Region pre-filtering continues to work before retrieval (Req 3.3)
- Cached RAG responses are returned without re-running retrieval (Req 3.4)
- BM25 + vector RRF fusion continues to merge ranked lists correctly before reranking (Req 3.5)

**Scope:**
All inputs where the cross-encoder is NOT available, or where no chunks are retrieved, or where a cached response exists, should be completely unaffected by this fix. This includes:
- Queries that hit the Redis cache
- Queries that return zero chunks
- Queries processed when the cross-encoder model fails to load
- Region and source_filter pre-filtering logic

## Hypothesized Root Cause

Based on code analysis, the root causes are:

1. **`cross_encoder_rerank()` discards scores**: The function calls `cross_encoder.predict(pairs)` to obtain `ce_scores` but only uses them for sorting via `sorted(zip(ce_scores, chunks), ...)`. The scores are never written back onto the chunk dicts, so they vanish after the function returns.

2. **`filter_by_similarity()` is score-type unaware**: It unconditionally reads `chunk["score"]` (the vector search score). After reranking, this field is stale and no longer represents the best available relevance signal.

3. **Source building sorts on stale `score`**: `LlamaIndexPipeline.query()` does `sorted(chunks, key=lambda c: float(c.get("score", 0.0)), reverse=True)[:5]` — this re-sorts by vector score, undoing the cross-encoder ordering.

4. **LLM context uses a different slice**: LLM context is built from `chunks[:3]` (positional after reranking) while sources come from the re-sorted top 5. The two sets can be completely disjoint.

5. **Confidence averages the wrong population**: Confidence is computed as `mean(c["score"] for c in chunks)` — all chunks, all vector scores — instead of the scores of the 5 source chunks.

## Correctness Properties

Property 1: Bug Condition — Sources and LLM context use cross-encoder ranking

_For any_ query where the cross-encoder successfully reranks chunks (isBugCondition returns true), the fixed pipeline SHALL build sources and LLM context from the same top-ranked chunk list ordered by cross-encoder score, and confidence SHALL be computed from the scores of those source chunks.

**Validates: Requirements 2.1, 2.2, 2.3, 2.5**

Property 2: Preservation — Fallback and non-reranked paths unchanged

_For any_ query where the cross-encoder is unavailable or no chunks are retrieved (isBugCondition returns false), the fixed pipeline SHALL produce the same sources, LLM context, and confidence as the original pipeline, preserving all existing fallback and caching behaviour.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `backend/services/index_manager.py`

**Function**: `cross_encoder_rerank()`

**Specific Changes**:
1. **Store ce_score on each chunk**: After `cross_encoder.predict(pairs)`, write `chunk["ce_score"] = float(score)` for each `(score, chunk)` pair before returning the sorted list.

**Function**: `filter_by_similarity()`

**Specific Changes**:
2. **Prefer ce_score when available**: Change the filter to read `chunk.get("ce_score", chunk.get("score", 1.0))` so that when a cross-encoder score exists it is used for threshold comparison.

---

**File**: `backend/services/llamaindex_pipeline.py`

**Function**: `LlamaIndexPipeline.query()`

**Specific Changes**:
3. **Unify source and LLM chunk selection**: Sort chunks by `ce_score` (falling back to `score`) and take the top `min(top_k, 5)` as `top_chunks`. Use this single list for both source building and LLM context construction.
4. **Fix LLM context to use `top_chunks`**: Replace `for c in chunks[:3]` with `for c in top_chunks[:3]` so the LLM reads the same passages cited as sources.
5. **Fix confidence to use source scores**: Compute confidence as the mean of `ce_score` (or `score`) over `top_chunks` only, not over all `chunks`.

---

**File**: `backend/models/document.py`

**Specific Changes**:
6. **No model changes required**: `DocumentSource` already has a `confidence_score` field. `RAGResponse` already has `confidence_score`. The `ce_score` lives on the internal chunk dict, not on the Pydantic models.

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Construct chunk lists where vector scores and cross-encoder scores produce different orderings. Run them through the unfixed `cross_encoder_rerank()` and `LlamaIndexPipeline.query()` to observe that sources diverge from LLM context and that confidence is computed on stale scores.

**Test Cases**:
1. **ce_score discarded test**: Call `cross_encoder_rerank()` with known chunks, assert `ce_score` key exists on returned chunks (will fail on unfixed code)
2. **Source ordering test**: Provide chunks where vector score order ≠ ce_score order, assert sources follow ce_score order (will fail on unfixed code)
3. **Source/LLM divergence test**: Provide 6+ chunks with conflicting orderings, assert sources and LLM context chunks overlap (will fail on unfixed code)
4. **Similarity filter test**: Provide a chunk with low vector score but high ce_score, assert it survives `filter_by_similarity` (will fail on unfixed code)

**Expected Counterexamples**:
- `cross_encoder_rerank()` returns chunks without `ce_score` field
- Sources sorted by vector score differ from cross-encoder order
- `filter_by_similarity` drops chunks the cross-encoder ranked highly
- Confidence value differs from mean of source chunk scores

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed functions produce the expected behavior.

**Pseudocode:**
```
FOR ALL (query, chunks) WHERE cross_encoder_succeeds(query, chunks) DO
  reranked := cross_encoder_rerank_fixed(query, chunks)
  ASSERT all(chunk HAS "ce_score" for chunk in reranked)

  filtered := filter_by_similarity_fixed(reranked)
  ASSERT all(chunk["ce_score"] >= threshold for chunk in filtered)

  response := pipeline_query_fixed(query, chunks)
  source_ids := {s.document_id for s in response.sources}
  llm_context_ids := {extract_id(c) for c in llm_context_chunks}
  ASSERT source_ids ⊇ llm_context_ids
  ASSERT response.confidence_score == mean(top_chunk_scores)
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed functions produce the same result as the original functions.

**Pseudocode:**
```
FOR ALL (query, chunks) WHERE NOT cross_encoder_succeeds(query, chunks) DO
  ASSERT cross_encoder_rerank_original(query, chunks) == cross_encoder_rerank_fixed(query, chunks)
  ASSERT filter_by_similarity_original(chunks) == filter_by_similarity_fixed(chunks)
  ASSERT pipeline_query_original(query) == pipeline_query_fixed(query)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many test cases automatically across the input domain
- It catches edge cases that manual unit tests might miss
- It provides strong guarantees that behavior is unchanged for all non-buggy inputs

**Test Plan**: Observe behavior on UNFIXED code first for queries where the cross-encoder is unavailable, then write property-based tests capturing that behavior.

**Test Cases**:
1. **Fallback preservation**: Verify that when cross-encoder import fails, `cross_encoder_rerank` returns chunks unchanged on both old and new code
2. **Empty chunks preservation**: Verify that when no chunks are retrieved, `query()` returns the same no-source LLM response
3. **Cache preservation**: Verify that cached responses are returned identically without re-running retrieval
4. **filter_by_similarity fallback**: Verify that chunks without `ce_score` are filtered by `score` identically to the original code

### Unit Tests

- Test `cross_encoder_rerank()` stores `ce_score` on each returned chunk
- Test `filter_by_similarity()` uses `ce_score` when present, falls back to `score` when absent
- Test source building sorts by `ce_score` when available
- Test LLM context and sources use the same chunk list
- Test confidence is computed from source chunk scores only

### Property-Based Tests

- Generate random chunk lists with random vector and ce_scores; verify sources are always ordered by ce_score when present
- Generate random chunk lists without ce_score; verify `filter_by_similarity` behaves identically to original
- Generate random queries with cross-encoder disabled; verify pipeline output matches original exactly

### Integration Tests

- End-to-end test: query with mocked cross-encoder returning known scores, verify response sources match expected order
- End-to-end test: query with cross-encoder unavailable, verify graceful fallback
- End-to-end test: query returning zero chunks, verify LLM-only response with no sources
