# Bugfix Requirements Document

## Introduction

When the chat assistant responds with source citations, the `DocumentSource` objects lack their relevance scores despite the backend having computed them. The backend `LlamaIndexPipeline` already filters sources below `SOURCE_RELEVANCE_THRESHOLD` (0.3) before returning them, so truly irrelevant sources are already excluded. However, the `confidence_score` field on each `DocumentSource` is not populated from the chunk's retrieval score, which prevents the frontend from applying any additional filtering or displaying relevance information.

The primary fix is backend-only: populate `confidence_score` on `DocumentSource` objects. A secondary frontend defense-in-depth filter is added to guard against edge cases where borderline sources slip through.

**Backend filtering already in place**: Both `query()` and `query_stream()` in `backend/services/llamaindex_pipeline.py` filter sources using `SOURCE_RELEVANCE_THRESHOLD = 0.3` (configurable in `backend/core/config.py`). Sources below this threshold are already excluded from the response.

**Affected pages**: The chat page uses `SourcesPanel` with `CitationChip` components. The diagnose page renders sources differently (inline list in the results section) but receives sources from the same backend pipeline. Both pages would benefit from populated `confidence_score` values, though the frontend filter is only applied in the chat `SourcesPanel` for now.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN the `LlamaIndexPipeline` constructs `DocumentSource` objects from retrieved chunks in `query()` and `query_stream()` THEN the system does not populate the `confidence_score` field on each `DocumentSource`, leaving it as `None` despite the chunk having a valid `ce_score` or `score` value

1.2 WHEN the frontend `SourcesPanel` component receives `message.sources` from a `done` SSE event THEN the system renders all sources without checking any relevance score, so if the backend threshold is lowered or a borderline source passes through, it will be displayed without question

### Expected Behavior (Correct)

2.1 WHEN the `LlamaIndexPipeline` constructs `DocumentSource` objects from retrieved chunks in `query()` and `query_stream()` THEN the system SHALL populate the `confidence_score` field on each `DocumentSource` with the chunk's `ce_score` (or fallback `score`) value — this is the primary fix

2.2 WHEN the frontend `SourcesPanel` component receives `message.sources` from a `done` SSE event THEN the system SHALL filter out any sources whose `confidence_score` is below `0.3` (matching the backend `SOURCE_RELEVANCE_THRESHOLD`) before rendering them — this is a defense-in-depth fallback

2.3 WHEN all sources in a response have `confidence_score` below the frontend display threshold THEN the system SHALL hide the sources panel entirely (display no sources)

### Unchanged Behavior (Regression Prevention)

3.1 WHEN all retrieved chunks have scores above `SOURCE_RELEVANCE_THRESHOLD` THEN the system SHALL CONTINUE TO display all sources in the `SourcesPanel` as citation chips (no sources filtered out)

3.2 WHEN no chunks are retrieved (empty retrieval) THEN the system SHALL CONTINUE TO return an empty `sources` list and hide the sources panel

3.3 WHEN the backend `SOURCE_RELEVANCE_THRESHOLD` filtering removes all chunks THEN the system SHALL CONTINUE TO return an empty `sources` list in the `done` SSE event

3.4 WHEN a cached RAG response is served THEN the system SHALL CONTINUE TO return the cached sources with their original `confidence_score` values intact

3.5 WHEN the `SourcesPanel` is expanded and all displayed sources are above the threshold THEN the system SHALL CONTINUE TO render `CitationChip` components with document title, excerpt, and page information

3.6 WHEN the diagnose page displays sources in its inline results list THEN the system SHALL CONTINUE TO render all sources returned by the backend (frontend filtering is chat-only for now)

---

## Bug Condition

```pascal
FUNCTION isBugCondition(X)
  INPUT: X of type ChatResponse (containing sources: list[DocumentSource])
  OUTPUT: boolean
  
  // Returns true when any source has a missing confidence_score
  // (the primary bug — score not populated from chunk data)
  RETURN EXISTS source IN X.sources WHERE source.confidence_score IS NULL
END FUNCTION
```

## Property Specification

```pascal
// Property: Fix Checking — confidence_score population (primary fix)
FOR ALL X WHERE isBugCondition(X) DO
  sources ← buildDocumentSources'(X.chunks)
  FOR EACH (source, chunk) IN zip(sources, X.chunks) DO
    ASSERT source.confidence_score = chunk.ce_score OR source.confidence_score = chunk.score
    ASSERT source.confidence_score IS NOT NULL
  END FOR
END FOR

// Property: Fix Checking — frontend filtering (defense-in-depth)
FOR ALL responses R DO
  displayed ← filterSources'(R.sources, 0.3)
  FOR EACH source IN displayed DO
    ASSERT source.confidence_score >= 0.3
  END FOR
END FOR
```

## Preservation Goal

```pascal
// Property: Preservation Checking
FOR ALL X WHERE NOT isBugCondition(X) DO
  // All sources already have valid confidence_score
  ASSERT buildDocumentSources(X.chunks) = buildDocumentSources'(X.chunks)
  ASSERT filterSources(X.sources) = filterSources'(X.sources)
END FOR
```
