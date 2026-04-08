# Bugfix Requirements Document

## Introduction

Chat response sources are not semantically correct. After cross-encoder reranking determines the most relevant chunks, the reranking scores are discarded and sources are built by sorting on stale vector search scores. Additionally, the LLM context is constructed from a different set of chunks than the ones cited as sources, causing a semantic mismatch between what the model reads and what the user sees as citations.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN chunks are reranked by the cross-encoder in `cross_encoder_rerank()` THEN the system discards the cross-encoder scores and retains only the original vector search scores in each chunk's `score` field

1.2 WHEN sources are built in `LlamaIndexPipeline.query()` THEN the system sorts chunks by the stale vector search `score` field instead of the cross-encoder relevance order, causing the top 5 sources to not be the most semantically relevant

1.3 WHEN the LLM context is constructed THEN the system uses `chunks[:3]` (first 3 by reranked position) while sources are built from `top_chunks` (top 5 by stale vector score), so the LLM may be grounded on different passages than what is cited to the user

1.4 WHEN `filter_by_similarity()` runs after cross-encoder reranking THEN the system filters by the original vector search scores, potentially discarding chunks that the cross-encoder ranked as highly relevant

1.5 WHEN the confidence score is calculated THEN the system computes the arithmetic mean over all chunks' stale vector scores rather than the scores of the chunks actually used as sources

### Expected Behavior (Correct)

2.1 WHEN chunks are reranked by the cross-encoder THEN the system SHALL store the cross-encoder score in each chunk (e.g. as a `ce_score` field) so downstream stages can use it

2.2 WHEN sources are built THEN the system SHALL sort chunks by the cross-encoder score (falling back to vector score when cross-encoder is unavailable) so the top 5 sources are the most semantically relevant

2.3 WHEN the LLM context and sources are constructed THEN the system SHALL use the same set of top-ranked chunks for both, so the cited sources match the passages the LLM was grounded on

2.4 WHEN `filter_by_similarity()` runs after cross-encoder reranking THEN the system SHALL filter by the cross-encoder score when available, so semantically relevant chunks are not incorrectly discarded

2.5 WHEN the confidence score is calculated THEN the system SHALL compute it from the scores of the chunks actually selected as sources, not from all retrieved chunks

### Unchanged Behavior (Regression Prevention)

3.1 WHEN the cross-encoder model is unavailable THEN the system SHALL CONTINUE TO fall back gracefully and return chunks in their pre-rerank order without crashing

3.2 WHEN no chunks are retrieved (empty result set) THEN the system SHALL CONTINUE TO call the LLM with general medical knowledge and return a response with no sources

3.3 WHEN a region pre-filter is applied THEN the system SHALL CONTINUE TO filter chunks by region before retrieval

3.4 WHEN a cached RAG response exists THEN the system SHALL CONTINUE TO return the cached response without re-running retrieval

3.5 WHEN BM25 and vector results are fused via RRF THEN the system SHALL CONTINUE TO merge both ranked lists correctly before reranking
