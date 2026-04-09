# Source Relevance Filtering Bugfix Design

## Overview

The `LlamaIndexPipeline` constructs `DocumentSource` objects from retrieved chunks in both `query()` and `query_stream()`, but never populates the `confidence_score` field despite the chunk data containing valid `ce_score` (cross-encoder) or `score` (vector similarity) values. The backend already filters chunks below `SOURCE_RELEVANCE_THRESHOLD` (0.3), so irrelevant sources are excluded — but the score itself is lost.

The fix is two-layered:
1. **Backend (primary)**: Populate `confidence_score` on each `DocumentSource` from the chunk's `ce_score` (preferred) or fallback `score` during construction in both `query()` and `query_stream()`.
2. **Frontend (defense-in-depth)**: Add a filter in `SourcesPanel` to drop sources with `confidence_score < 0.3` before rendering, and hide the panel entirely if all sources are filtered out.

## Glossary

- **Bug_Condition (C)**: Any `DocumentSource` in a `RAGResponse` where `confidence_score` is `None` despite the originating chunk having a valid `ce_score` or `score` value
- **Property (P)**: Every `DocumentSource` constructed from a chunk SHALL have `confidence_score` populated with the chunk's `ce_score` (or fallback `score`); the frontend SHALL only render sources with `confidence_score >= 0.3`
- **Preservation**: All existing behaviors for above-threshold sources, empty retrievals, cached responses, `CitationChip` rendering, and diagnose page sources must remain unchanged
- **`LlamaIndexPipeline`**: The class in `backend/services/llamaindex_pipeline.py` that orchestrates retrieval, re-ranking, source construction, and LLM generation
- **`DocumentSource`**: Pydantic model in `backend/models/document.py` (and Zod schema `DocumentSourceSchema` in `packages/types/index.ts`) representing a cited source with fields including `confidence_score: float | None`
- **`SourcesPanel`**: React component in `apps/web/src/app/[locale]/chat/page.tsx` that renders expandable citation chips for a message's sources
- **`SOURCE_RELEVANCE_THRESHOLD`**: Config setting in `backend/core/config.py` (default `0.3`) used to filter chunks before including them as sources
- **`ce_score`**: Cross-encoder re-ranking score assigned to chunks by the retrieval pipeline; preferred over raw vector `score`

## Bug Details

### Bug Condition

The bug manifests when the `LlamaIndexPipeline` constructs `DocumentSource` objects from retrieved chunks. The `DocumentSource(...)` constructor call in both `query()` and `query_stream()` does not include a `confidence_score` argument, so the field defaults to `None` per the Pydantic model definition (`confidence_score: float | None = None`). The chunk's `ce_score` or `score` value is available at construction time (it is used for sorting and threshold filtering on the adjacent lines) but is simply never passed through.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type RAGResponse (containing sources: list[DocumentSource], originating from chunks with scores)
  OUTPUT: boolean

  RETURN EXISTS source IN input.sources
         WHERE source.confidence_score IS NULL
         AND correspondingChunk(source).ce_score IS NOT NULL
             OR correspondingChunk(source).score IS NOT NULL
END FUNCTION
```

### Examples

- **Example 1**: `query()` retrieves 3 chunks with `ce_score` values `[0.85, 0.72, 0.45]`. All pass the 0.3 threshold. The 3 `DocumentSource` objects are returned with `confidence_score = None` instead of `[0.85, 0.72, 0.45]`.
- **Example 2**: `query_stream()` retrieves 2 chunks with `score` values `[0.60, 0.35]` (no `ce_score`). Both pass the 0.3 threshold. The 2 `DocumentSource` objects are returned with `confidence_score = None` instead of `[0.60, 0.35]`.
- **Example 3**: A chunk with `ce_score = 0.31` barely passes the backend threshold. The `DocumentSource` is returned with `confidence_score = None`. If the frontend had a defense-in-depth filter, it could not evaluate this borderline source because the score is missing.
- **Edge case**: No chunks retrieved — `sources` is empty, no `DocumentSource` objects are constructed. Bug condition does not apply (no sources to have missing scores).

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- All sources with `confidence_score >= 0.3` must continue to appear in the `SourcesPanel` as `CitationChip` components with document title, excerpt, and page information
- Empty retrieval (no chunks) must continue to return an empty `sources` list and hide the sources panel
- When the backend `SOURCE_RELEVANCE_THRESHOLD` filtering removes all chunks, the `done` SSE event must continue to carry an empty `sources` list
- Cached `RAGResponse` objects must continue to be served with their original `confidence_score` values intact (the cache stores serialized `RAGResponse` which will now include populated scores). **Backward compatibility note**: cached responses written *before* the fix will have `confidence_score = None` on their `DocumentSource` objects. The frontend filter's `== null` guard keeps these sources visible — they are not incorrectly filtered out. These old cache entries will naturally expire (5 min TTL) and be replaced with correctly-populated entries.
- The diagnose page's inline source rendering must continue to display all sources returned by the backend (the frontend filter is chat-only, applied in `SourcesPanel`)
- `CitationChip` rendering logic (tooltip from section/page, popup on click) must remain unchanged

**Scope:**
All inputs that do NOT involve the `DocumentSource` construction path (i.e., no chunks retrieved, cached responses already serialized with scores, diagnose page rendering) should be completely unaffected by this fix. This includes:
- Mouse/keyboard interactions with `CitationChip` and `CitationPopup`
- The `RAGResponse.confidence_score` field (arithmetic mean of retained chunk scores, distinct from the per-source `DocumentSource.confidence_score`) — already correctly computed. Note: `RAGResponse` also has a legacy `confidence: float | None` field which is unused; the active field is `confidence_score`.
- The `StreamEvent` backend model and SSE serialization
- The `SOURCE_RELEVANCE_THRESHOLD` filtering logic itself (it already works correctly)

## Hypothesized Root Cause

Based on the code analysis, the root cause is definitively identified (not merely hypothesized):

1. **Missing `confidence_score` argument in `DocumentSource` construction**: In both `query()` and `query_stream()`, the list comprehension that builds `DocumentSource` objects passes `document_id`, `title`, `source`, `section`, `excerpt`, and `page` — but omits `confidence_score`. The chunk's score is available in the same scope (used for sorting on the preceding line and for threshold filtering on the following line) but is never assigned to the `DocumentSource`. The pattern to look for is the `sources = [DocumentSource(...) for c in top_chunks]` list comprehension in each method.

2. **No frontend safety net**: The `SourcesPanel` component renders all sources from `message.sources` without inspecting `confidence_score`. While the backend threshold currently prevents low-score sources from reaching the frontend, there is no defense-in-depth if the threshold is lowered or a borderline source slips through.

3. **Score is computed but discarded**: The expression `float(c.get("ce_score", c.get("score", 0.0)))` appears three times in each method (sort key, threshold filter, mean calculation) but is never stored on the `DocumentSource` itself. This is a classic "computed but not persisted" oversight.

## Correctness Properties

Property 1: Bug Condition - confidence_score Population

_For any_ chunk dict with a valid `ce_score` or `score` value that passes the `SOURCE_RELEVANCE_THRESHOLD` filter, the fixed `DocumentSource` construction SHALL set `confidence_score` to `float(chunk.get("ce_score", chunk.get("score", 0.0)))`, ensuring `confidence_score` is never `None` for sources derived from scored chunks.

**Validates: Requirements 1.1, 2.1**

Property 2: Preservation - Above-Threshold Sources Display Unchanged

_For any_ list of `DocumentSource` objects where all `confidence_score` values are `>= 0.3`, the frontend filter SHALL return the entire list unchanged, preserving the count and order of displayed sources and ensuring no sources are incorrectly removed.

**Validates: Requirements 3.1, 3.5**

Property 3: Frontend Filter - Below-Threshold Sources Excluded

_For any_ list of `DocumentSource` objects with mixed `confidence_score` values, the frontend filter SHALL return only those with `confidence_score >= 0.3`, and SHALL return an empty list (hiding the panel) when all scores are below `0.3`.

**Validates: Requirements 2.2, 2.3**

## Fix Implementation

### Changes Required

**File**: `backend/services/llamaindex_pipeline.py`

**Function**: `query()` (line ~200) and `query_stream()` (line ~350)

**Specific Changes**:

1. **Add `confidence_score` to `DocumentSource` construction in `query()`**: In the list comprehension that builds `sources` from `top_chunks`, add the argument `confidence_score=float(c.get("ce_score", c.get("score", 0.0)))` to the `DocumentSource(...)` call. This reuses the same score expression already used for sorting and filtering.

2. **Add `confidence_score` to `DocumentSource` construction in `query_stream()`**: Apply the identical change to the parallel list comprehension in `query_stream()`.

3. **No model changes needed**: The `DocumentSource` Pydantic model already declares `confidence_score: float | None = None`, and the `DocumentSourceSchema` Zod schema already includes `confidence_score: z.number().optional()`. The `StreamEvent` model carries a `sources: list[DocumentSource]` field that passes `DocumentSource` objects through to the SSE serialization — the populated `confidence_score` will flow through automatically. No schema changes are required anywhere.

**File**: `apps/web/src/app/[locale]/chat/page.tsx`

**Function**: `SourcesPanel` component

**Specific Changes**:

4. **Add confidence_score filter in `SourcesPanel`**: Before the existing `if (sources.length === 0) return null;` guard, filter the `sources` array: `const filtered = sources.filter(s => s.confidence_score == null || s.confidence_score >= 0.3);`. The `== null` check uses JavaScript's loose equality which matches both `null` and `undefined` — this is intentional because the Zod schema declares `confidence_score: z.number().optional()`, so absent values are `undefined` (not `null`). Sources with missing `confidence_score` (e.g., from older cached responses serialized before the fix) are kept to avoid breaking existing data. Then use `filtered` for the rest of the component.

5. **Update count and rendering to use filtered list**: The sources count display `({sources.length})` and the `.map()` rendering loop should both operate on the `filtered` array instead of the raw `sources` prop.

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm the root cause analysis that `confidence_score` is not populated during `DocumentSource` construction.

**Test Plan**: Write tests that construct chunk dicts with `ce_score` and `score` values, run them through the `DocumentSource` construction logic in `query()` and `query_stream()`, and assert that `confidence_score` is populated. Leverage the existing test infrastructure in `backend/tests/test_pipeline_stream.py` which already mocks `_embedder`, `_index`, `_llm`, and `cache_service` dependencies and sets `SOURCE_RELEVANCE_THRESHOLD`. Run these tests on the UNFIXED code to observe failures.

**Test Cases**:
1. **query() score population test**: Call `query()` with mocked chunks having `ce_score` values, verify `DocumentSource.confidence_score` is set (will fail on unfixed code — score is `None`)
2. **query_stream() score population test**: Call `query_stream()` with mocked chunks having `ce_score` values, verify the `done` event's sources have `confidence_score` set (will fail on unfixed code)
3. **Fallback score test**: Call `query()` with chunks having only `score` (no `ce_score`), verify `confidence_score` falls back to `score` (will fail on unfixed code)
4. **Mixed score test**: Call `query()` with chunks where some have `ce_score` and others only `score`, verify each `DocumentSource` gets the correct value (will fail on unfixed code)

**Expected Counterexamples**:
- `DocumentSource.confidence_score` is `None` for all constructed sources despite chunks having valid `ce_score`/`score` values
- Root cause confirmed: the `DocumentSource(...)` constructor call omits the `confidence_score` keyword argument

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**
```
FOR ALL chunks WHERE chunk has ce_score OR score DO
  source := buildDocumentSource_fixed(chunk)
  expected_score := float(chunk.get("ce_score", chunk.get("score", 0.0)))
  ASSERT source.confidence_score == expected_score
  ASSERT source.confidence_score IS NOT NULL
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**
```
FOR ALL source_lists WHERE ALL sources have confidence_score >= 0.3 DO
  filtered := frontendFilter(source_lists, 0.3)
  ASSERT filtered == source_lists  // no sources removed
  ASSERT len(filtered) == len(source_lists)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many combinations of chunk scores to verify confidence_score is always correctly populated
- It generates many source lists with various confidence_score distributions to verify the frontend filter preserves above-threshold sources
- It catches edge cases like `confidence_score` exactly equal to `0.3`, `None` values from legacy cached data, and empty source lists

**Test Plan**: Observe behavior on UNFIXED code first for above-threshold sources and empty retrievals, then write property-based tests capturing that behavior.

**Test Cases**:
1. **Above-threshold preservation**: Generate random source lists where all `confidence_score >= 0.3`, verify the frontend filter returns the full list unchanged
2. **Empty sources preservation**: Verify that empty source lists pass through the filter unchanged and the panel remains hidden
3. **CitationChip rendering preservation**: Verify that `CitationChip` components render correctly with sources that now include `confidence_score` values
4. **Cached response preservation**: Verify that cached `RAGResponse` objects with populated `confidence_score` values are served correctly

### Unit Tests

- Test `DocumentSource` construction with `ce_score` present → `confidence_score` equals `ce_score`
- Test `DocumentSource` construction with only `score` (no `ce_score`) → `confidence_score` equals `score`
- Test `DocumentSource` construction with neither score → `confidence_score` equals `0.0`
- Test frontend filter with mixed scores → only `>= 0.3` retained
- Test frontend filter with all scores `>= 0.3` → all retained
- Test frontend filter with all scores `< 0.3` → empty list, panel hidden
- Test frontend filter with `confidence_score = null` → source retained (backward compatibility)

### Property-Based Tests

- Generate random chunk dicts with `ce_score` and/or `score` fields, verify `confidence_score` is always populated correctly on the resulting `DocumentSource`
- Generate random lists of `DocumentSource` objects with various `confidence_score` values, verify the frontend filter correctly partitions them at the 0.3 threshold
- Generate random source lists where all scores are above threshold, verify the filter is identity (preservation)

### Integration Tests

- Test full `query()` flow with mocked retrieval returning scored chunks, verify the `RAGResponse.sources` all have `confidence_score` populated
- Test full `query_stream()` flow, verify the `done` `StreamEvent` carries sources with `confidence_score` populated
- Test that cached responses (written after the fix) include `confidence_score` and are served correctly on cache hit
- Test the chat page end-to-end: send a message, receive sources with scores, verify `SourcesPanel` renders only above-threshold sources
