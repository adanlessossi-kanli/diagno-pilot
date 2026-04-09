# Implementation Plan: LLM Response Streaming

## Overview

Replace the non-streaming `POST /api/v1/chat/message` endpoint with an SSE streaming endpoint. Implementation follows the data flow bottom-up: LLM client → router → RAG pipeline → chat service → endpoint → API client → chat UI → legacy removal → README update. Each layer adds a `*_stream` method while preserving existing non-streaming methods for non-chat callers.

## Tasks

- [x] 1. Implement `_LLMClient.generate_stream()` and streaming data classes
  - [x] 1.1 Add `StreamChunk` dataclass to `backend/services/llm_router.py`
    - Define `StreamChunk` with fields: `token: str | None`, `error: str | None`, `fallback_used: bool`, `llm_used: str`
    - _Requirements: 2.1_

  - [x] 1.2 Add `StreamEvent` dataclass to `backend/services/llamaindex_pipeline.py`
    - Define `StreamEvent` with fields: `type` ("token" | "done" | "error"), `content`, `answer`, `sources`, `llm_used`, `fallback_used`, `confidence_score`, `error`, `retryable`
    - Import `DocumentSource` for the `sources` field type
    - _Requirements: 3.2, 4.3, 4.4_

  - [x] 1.3 Implement `_LLMClient.generate_stream()` method
    - Use `httpx.AsyncClient.stream()` context manager with `stream: true` in payload
    - Parse SSE lines via `response.aiter_lines()`
    - Yield non-empty `delta.content` strings, skip empty deltas
    - Stop on `data: [DONE]`
    - Raise `LLMUnavailableError` on connection failure or timeout
    - No `RetryPolicy` — retries handled at router level
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

  - [x] 1.4 Write property test for `_LLMClient.generate_stream()` — Property 1: LLM Client Stream Parsing
    - **Property 1: LLM Client Stream Parsing**
    - Generate random sequences of SSE lines (valid tokens, empty deltas, `[DONE]`). Mock `httpx.AsyncClient` to return the sequence. Verify the async iterator yields exactly the non-empty tokens in order.
    - Use Hypothesis with `@settings(max_examples=100)`
    - Tag: `# Feature: llm-response-streaming, Property 1: LLM Client Stream Parsing`
    - **Validates: Requirements 1.1, 1.2, 1.3**

  - [x] 1.5 Write unit tests for `_LLMClient.generate_stream()`
    - Test connection error raises `LLMUnavailableError`
    - Test timeout raises `LLMUnavailableError`
    - Test happy path with a few token chunks
    - _Requirements: 1.4_

- [x] 2. Implement `LLMRouter.generate_stream()` with fallback logic
  - [x] 2.1 Implement `LLMRouter.generate_stream()` method
    - Check `_primary_cb` circuit breaker state before starting stream
    - If circuit open, skip to fallback immediately
    - If closed, call `_primary.generate_stream()` and track tokens yielded
    - Record success/failure on circuit breaker manually after iterator completes or raises
    - Yield `StreamChunk` objects with `token` and `llm_used` fields
    - Record Prometheus metrics for both success and failure paths
    - _Requirements: 2.1, 2.6_

  - [x] 2.2 Implement pre-token fallback path in `LLMRouter.generate_stream()`
    - If primary fails before any tokens yielded: strip PHI via `BAA_Controller`, fall back to GPT-5
    - If primary circuit is open: skip directly to fallback with PHI stripping
    - If both models fail: raise `HTTPException(503)` with `LLM_UNAVAILABLE` body
    - _Requirements: 2.2, 2.4, 2.5_

  - [x] 2.3 Implement mid-stream error handling in `LLMRouter.generate_stream()`
    - If primary fails after tokens yielded: yield `StreamChunk(error=...)`, do NOT fallback
    - _Requirements: 2.3_

  - [x] 2.4 Write property test for pre-token fallback — Property 2: Pre-Token Fallback with PHI Stripping
    - **Property 2: Pre-Token Fallback with PHI Stripping**
    - Generate random prompts/contexts. Mock primary to raise `LLMUnavailableError`. Verify `BAA_Controller.strip_phi` is called and fallback client's `generate_stream` is invoked with sanitized context.
    - Use Hypothesis with `@settings(max_examples=100)`
    - Tag: `# Feature: llm-response-streaming, Property 2: Pre-Token Fallback with PHI Stripping`
    - **Validates: Requirements 2.2, 2.4**

  - [x] 2.5 Write property test for mid-stream error — Property 3: No Mid-Stream Fallback
    - **Property 3: No Mid-Stream Fallback**
    - Generate a random positive number of tokens (1–50). Mock primary to yield that many tokens then raise. Verify fallback is never called and an error chunk is yielded.
    - Use Hypothesis with `@settings(max_examples=100)`
    - Tag: `# Feature: llm-response-streaming, Property 3: No Mid-Stream Fallback`
    - **Validates: Requirement 2.3**

  - [x] 2.6 Write unit tests for `LLMRouter.generate_stream()`
    - Test happy path yields primary tokens with correct `llm_used`
    - Test both-fail raises HTTP 503
    - Test Prometheus metrics are recorded
    - _Requirements: 2.1, 2.5, 2.6_

- [x] 3. Checkpoint
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implement `LlamaIndexPipeline.query_stream()`
  - [x] 4.1 Implement `LlamaIndexPipeline.query_stream()` method
    - Perform cache lookup first; if cached, yield full answer as single token event then done event with metadata, without calling `LLMRouter.generate_stream()`
    - Perform document retrieval synchronously (same as `query()`)
    - Build LLM context (same logic as `query()`)
    - Call `LLMRouter.generate_stream()` and yield `StreamEvent(type="token")` for each chunk
    - Accumulate full answer text during streaming
    - After streaming: cache assembled `RAGResponse`, yield `StreamEvent(type="done")` with answer, sources, metadata
    - On error: yield `StreamEvent(type="error")`
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

  - [x] 4.2 Write property test for stream event ordering — Property 4: Stream Event Ordering
    - **Property 4: Stream Event Ordering**
    - Generate random token sequences. Mock the LLM router. Collect all yielded events. Verify all `token` events precede the single terminal event.
    - Use Hypothesis with `@settings(max_examples=100)`
    - Tag: `# Feature: llm-response-streaming, Property 4: Stream Event Ordering`
    - **Validates: Requirements 3.2**

  - [x] 4.3 Write property test for cache hit — Property 5: Cache Hit Streaming
    - **Property 5: Cache Hit Streaming**
    - Generate random `RAGResponse` objects. Pre-populate the cache. Verify the stream yields one token event with the cached answer and one done event with matching metadata, and `generate_stream` is not called.
    - Use Hypothesis with `@settings(max_examples=100)`
    - Tag: `# Feature: llm-response-streaming, Property 5: Cache Hit Streaming`
    - **Validates: Requirements 3.3**

  - [x] 4.4 Write unit tests for `LlamaIndexPipeline.query_stream()`
    - Test retrieval + streaming integration
    - Test cache write after completion
    - Test error event on retrieval failure
    - _Requirements: 3.1, 3.4_

- [x] 5. Implement `ChatService.send_message_stream()`
  - [x] 5.1 Implement `ChatService.send_message_stream()` method
    - Create session if `session_id` is None
    - Load and cap history at 20 messages
    - Delegate to `RAG_Pipeline.query_stream()`
    - Yield all `StreamEvent`s from the pipeline
    - After `done` event: persist user turn + assembled assistant turn to MongoDB
    - On mid-stream error: persist user turn only, omit assistant turn
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [x] 5.2 Write unit tests for `ChatService.send_message_stream()`
    - Test new session creation
    - Test history loading and capping
    - Test mid-stream error persists user turn only
    - Test successful stream persists both turns
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

- [x] 6. Implement streaming endpoint and SSE serialization
  - [x] 6.1 Implement `POST /api/v1/chat/message` streaming endpoint in `backend/routers/chat.py`
    - Return `EventSourceResponse` wrapping an async generator
    - Convert `StreamEvent(type="token")` → `event: token`, `data: {"content": "..."}`
    - Convert `StreamEvent(type="done")` → `event: done`, `data: {"answer": ..., "session_id": ..., "sources": ..., "llm_used": ..., "fallback_warning": ..., "warnings_present": ...}`
    - Convert `StreamEvent(type="error")` → `event: error`, `data: {"error": ..., "retryable": ...}`
    - Same auth (`require_role`) and rate limiting (`60/minute`) as current endpoint
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 8.1, 8.2, 8.3, 8.4_

  - [x] 6.2 Write property test for SSE serialization — Property 6: SSE Event Serialization
    - **Property 6: SSE Event Serialization**
    - Generate random `StreamEvent` instances (all three types). Serialize to SSE format. Parse the `data:` line as JSON. Verify all required fields are present and values match.
    - Use Hypothesis with `@settings(max_examples=100)`
    - Tag: `# Feature: llm-response-streaming, Property 6: SSE Event Serialization`
    - **Validates: Requirements 4.3, 4.4, 8.1, 8.2, 8.3, 8.4**

  - [x] 6.3 Write unit tests for streaming endpoint
    - Test auth enforcement (401)
    - Test rate limiting (429)
    - Test request validation (422)
    - Test full SSE stream integration with mocked ChatService
    - _Requirements: 4.1, 4.5, 4.6_

- [x] 7. Checkpoint
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Implement frontend `API_Client.sendMessageStream()`
  - [x] 8.1 Add `StreamEvent` TypeScript type to `packages/api-client/index.ts`
    - Define discriminated union type: `{ type: "token"; content: string } | { type: "done"; answer: string; session_id: string; sources: DocumentSource[]; llm_used: string; fallback_warning: string | null; warnings_present: boolean } | { type: "error"; error: string; retryable: boolean }`
    - _Requirements: 6.2, 6.3, 6.4_

  - [x] 8.2 Implement `sendMessageStream()` async generator method in `packages/api-client/index.ts`
    - Send POST to `/api/v1/chat/message` with `credentials: 'include'` and CSRF header
    - Read response body as `ReadableStream`, parse SSE lines manually
    - Yield parsed `StreamEvent` objects for token, done, and error events
    - Support `AbortSignal` for cancellation
    - Stop iteration after `done` or `error` event
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [x] 8.3 Write property test for frontend SSE parsing — Property 7: Frontend SSE Parse Round-Trip
    - **Property 7: Frontend SSE Parse Round-Trip**
    - Generate random SSE text streams with token, done, and error events. Parse with the client's SSE parser. Verify yielded `StreamEvent` objects match the original event data.
    - Use fast-check with Vitest
    - Tag: `// Feature: llm-response-streaming, Property 7: Frontend SSE Parse Round-Trip`
    - **Validates: Requirements 6.2, 6.3**

  - [x] 8.4 Write unit tests for `sendMessageStream()`
    - Test AbortSignal cancellation
    - Test error event handling
    - Test happy path token-by-token iteration
    - _Requirements: 6.1, 6.5_

- [x] 9. Update Chat UI for streaming display
  - [x] 9.1 Update `handleSend()` in `apps/web/src/app/[locale]/chat/page.tsx` to use streaming
    - Switch from `apiClient.chat.sendMessage()` to `apiClient.chat.sendMessageStream()`
    - Store an `AbortController` ref, created per-send, cleaned up on completion
    - On each `token` event: append content to the streaming `MessageBubble`
    - On `done` event: remove streaming indicator, attach sources, finalize message
    - On `error` event: show error banner with retry button if `retryable`
    - _Requirements: 7.1, 7.3, 7.5_

  - [x] 9.2 Add streaming indicator and auto-scroll behavior
    - Replace `ThinkingBubble` with streaming `MessageBubble` + blinking cursor CSS animation after first token arrives
    - Auto-scroll pauses when user scrolls up; resumes when user scrolls to bottom
    - _Requirements: 7.2, 7.4_

  - [x] 9.3 Implement stream abort on navigation and new session
    - "New Session" and navigation abort the stream via `AbortController.abort()`
    - _Requirements: 7.6_

  - [x] 9.4 Write unit tests for Chat UI streaming behavior
    - Test token-by-token rendering
    - Test streaming indicator appears and disappears
    - Test done event finalizes message with sources
    - Test scroll behavior (pause on scroll up, resume on scroll to bottom)
    - Test retry on error event
    - Test abort on navigation
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

- [x] 10. Remove legacy non-streaming code
  - [x] 10.1 Remove `ChatMessageResponse` model and old `send_message` endpoint from `backend/routers/chat.py`
    - Delete the `ChatMessageResponse` Pydantic model
    - Delete the old `send_message` endpoint handler (replaced by streaming endpoint in task 6.1)
    - _Requirements: 9.1, 9.2_

  - [x] 10.2 Remove `ChatService.send_message()` non-streaming method from `backend/services/chat_service.py`
    - Delete the `send_message` method; `send_message_stream` is now the only public send method
    - _Requirements: 9.4_

  - [x] 10.3 Remove `sendMessage` method from `packages/api-client/index.ts`
    - Delete the `sendMessage` method from the `chat` namespace
    - `sendMessageStream` is now the sole method for sending chat messages
    - _Requirements: 9.3_

  - [x] 10.4 Write smoke tests for legacy removal and backward compatibility
    - Verify `ChatMessageResponse`, `sendMessage`, `ChatService.send_message` no longer exist
    - Verify `LLMRouter.generate()` and `LlamaIndexPipeline.query()` still work for diagnose pipeline
    - Verify `POST /api/v1/chat/message` returns `text/event-stream`
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

- [x] 11. Update README endpoint documentation
  - [x] 11.1 Update `README.md` "API — Endpoints principaux" section
    - Annotate `POST /api/v1/chat/message` as returning SSE stream (`text/event-stream`) instead of JSON
    - _Requirements: 9.6_

- [x] 12. Final checkpoint
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document (Properties 1–7)
- Unit tests validate specific examples and edge cases
- Backend uses Python (Hypothesis for PBT), frontend uses TypeScript (fast-check for PBT)
- The non-streaming `generate()` on `LLMRouter` and `query()` on `LlamaIndexPipeline` are preserved for the diagnose pipeline
