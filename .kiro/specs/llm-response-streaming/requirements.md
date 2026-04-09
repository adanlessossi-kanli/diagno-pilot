# Requirements Document

## Introduction

Diagno-Pilot's chat interface currently waits for the full LLM response before displaying anything to the user, resulting in poor perceived latency. Users stare at a "thinking" animation for the entire generation time (often several seconds). This feature replaces the existing non-streaming chat endpoint with a Server-Sent Events (SSE) streaming endpoint, so tokens appear incrementally as they are generated. The old non-streaming endpoint and its client-side caller are removed. The SSE infrastructure already exists in the codebase (`sse-starlette`, `EventSourceResponse`) via the MCP servers, and both LLM providers (MedicalQwen3-Reasoning-4B and GPT-5) support OpenAI-compatible streaming.

## Glossary

- **Streaming_Endpoint**: The FastAPI endpoint (`POST /api/v1/chat/message`) that replaces the existing non-streaming endpoint and returns an `EventSourceResponse` delivering assistant tokens incrementally via Server-Sent Events.
- **LLM_Client**: The `_LLMClient` class in `backend/services/llm_router.py` that makes HTTP POST requests to OpenAI-compatible `/chat/completions` endpoints.
- **LLM_Router**: The `LLMRouter` class that routes generation requests to the primary model (MedicalQwen3-Reasoning-4B) with GPT-5 fallback, including circuit breaker and retry logic.
- **Chat_Service**: The `ChatService` class in `backend/services/chat_service.py` that manages multi-turn chat sessions, history persistence, and RAG pipeline orchestration.
- **RAG_Pipeline**: The `LlamaIndexPipeline` class that retrieves relevant document chunks and generates grounded answers via the LLM_Router.
- **SSE_Stream**: A Server-Sent Events connection delivering a sequence of JSON events from the Streaming_Endpoint to the frontend.
- **Stream_Event**: A single SSE message in the stream, carrying either a token chunk, metadata (sources, llm_used), or a terminal signal.
- **API_Client**: The TypeScript `createApiClient` module in `packages/api-client/index.ts` that the frontend uses to communicate with the backend.
- **Chat_UI**: The React chat page component (`apps/web/src/app/[locale]/chat/page.tsx`) that renders messages and handles user input.
- **MessageBubble**: The React component that renders a single chat message in the Chat_UI.
- **ThinkingBubble**: The React component that displays a "thinking" animation while waiting for the assistant response.

## Requirements

### Requirement 1: LLM Client Streaming Support

**User Story:** As a backend developer, I want the LLM_Client to support streaming responses from OpenAI-compatible endpoints, so that tokens can be forwarded incrementally instead of waiting for the full response.

#### Acceptance Criteria

1. WHEN the LLM_Client receives a streaming request, THE LLM_Client SHALL send the HTTP POST to `/chat/completions` with `stream: true` in the payload and return an async iterator of token strings.
2. WHEN the LLM endpoint returns a streaming response with `data: [DONE]` as the terminal signal, THE LLM_Client SHALL stop iterating and close the HTTP connection.
3. WHEN the LLM endpoint returns a chunk with an empty `delta.content` field, THE LLM_Client SHALL skip that chunk and continue iterating without yielding.
4. IF the HTTP connection to the LLM endpoint fails or times out during streaming, THEN THE LLM_Client SHALL raise an `LLMUnavailableError` so the LLM_Router can attempt fallback.
5. THE LLM_Client SHALL preserve the existing non-streaming `generate` method unchanged so that non-streaming callers are unaffected.

### Requirement 2: LLM Router Streaming with Fallback

**User Story:** As a backend developer, I want the LLM_Router to support streaming generation with the same primary/fallback logic, so that streaming requests benefit from the same resilience as non-streaming requests.

#### Acceptance Criteria

1. WHEN a streaming generation request is made, THE LLM_Router SHALL attempt the primary model first and yield token chunks from the primary LLM_Client streaming response.
2. IF the primary model fails or its circuit breaker is open *before any tokens have been yielded*, THEN THE LLM_Router SHALL fall back to the GPT-5 model and yield token chunks from the fallback LLM_Client streaming response.
3. IF the primary model fails *after* one or more tokens have already been yielded, THEN THE LLM_Router SHALL NOT attempt a fallback and SHALL instead raise an error so the Streaming_Endpoint can emit an `error` event to the client.
4. WHEN falling back to GPT-5 during streaming, THE LLM_Router SHALL strip PHI from the context using the BAA_Controller before initiating the fallback stream.
5. IF both the primary and fallback models fail during a streaming request, THEN THE LLM_Router SHALL raise an HTTP 503 error with `{"error": "llm_unavailable", "code": "LLM_UNAVAILABLE", "retryable": true}`.
6. THE LLM_Router SHALL record Prometheus metrics (duration, request count) for streaming requests using the same labels as non-streaming requests.

### Requirement 3: RAG Pipeline Streaming Support

**User Story:** As a backend developer, I want the RAG_Pipeline to support a streaming query mode, so that document retrieval happens first and then LLM generation streams incrementally.

#### Acceptance Criteria

1. WHEN a streaming query is made, THE RAG_Pipeline SHALL perform document retrieval and context assembly synchronously (non-streamed), then yield token chunks from the LLM_Router streaming generation.
2. THE RAG_Pipeline SHALL yield source metadata (document sources, confidence score, llm_used, fallback_used) as a separate final event after all token chunks have been yielded.
3. WHEN a cached RAG response exists for the query, THE RAG_Pipeline SHALL return the cached response as a single chunk followed by the terminal event, bypassing LLM streaming.
4. THE RAG_Pipeline SHALL cache the fully assembled response after streaming completes, using the same cache key and TTL as non-streaming queries.

### Requirement 4: Streaming Chat Endpoint

**User Story:** As a frontend developer, I want the chat message endpoint to return an SSE stream, so that the frontend can receive assistant tokens incrementally.

#### Acceptance Criteria

1. THE Streaming_Endpoint SHALL accept POST requests at `/api/v1/chat/message` (replacing the former non-streaming endpoint) with the same request body schema (`ChatMessageRequest`).
2. THE Streaming_Endpoint SHALL return an `EventSourceResponse` with `Content-Type: text/event-stream`.
3. WHEN tokens are generated, THE Streaming_Endpoint SHALL emit SSE events with `event: token` and `data` containing a JSON object with a `content` field holding the token text.
4. WHEN all tokens have been emitted, THE Streaming_Endpoint SHALL emit a final SSE event with `event: done` and `data` containing a JSON object with `answer` (the full assembled response text), `session_id`, `sources`, `llm_used`, `fallback_warning`, and `warnings_present` fields.
5. IF an error occurs during streaming, THEN THE Streaming_Endpoint SHALL emit an SSE event with `event: error` and `data` containing a JSON object with `error` and `retryable` fields, then close the stream.
6. THE Streaming_Endpoint SHALL enforce the same authentication and rate-limiting rules as the former non-streaming endpoint.
7. THE Streaming_Endpoint SHALL persist both the user turn and the complete assembled assistant turn to MongoDB after streaming completes, identical to the former non-streaming behavior.

### Requirement 5: Chat Service Streaming Method

**User Story:** As a backend developer, I want the Chat_Service to provide a streaming send_message method, so that the streaming endpoint can orchestrate session management and streaming generation.

#### Acceptance Criteria

1. WHEN a streaming message request is received, THE Chat_Service SHALL load session history, invoke the RAG_Pipeline in streaming mode, and yield token chunks and the final metadata event.
2. THE Chat_Service SHALL persist the user turn and the fully assembled assistant turn to MongoDB after the stream completes.
3. THE Chat_Service SHALL create a new session if `session_id` is None, consistent with the current session creation behavior.
4. IF the streaming generation fails mid-stream, THEN THE Chat_Service SHALL persist the user turn but omit the assistant turn from the session history.

### Requirement 6: Frontend API Client Streaming Support

**User Story:** As a frontend developer, I want the API_Client to provide a method for consuming the SSE streaming endpoint, so that the Chat_UI can process tokens as they arrive.

#### Acceptance Criteria

1. THE API_Client SHALL expose a `sendMessageStream` method that sends a POST request to `/api/v1/chat/message` and returns an async iterable of parsed Stream_Event objects.
2. WHEN a `token` event is received from the SSE_Stream, THE API_Client SHALL yield an object with `type: "token"` and `content` containing the token text.
3. WHEN a `done` event is received from the SSE_Stream, THE API_Client SHALL yield an object with `type: "done"` and the metadata fields (`answer`, `session_id`, `sources`, `llm_used`, `fallback_warning`, `warnings_present`), then stop iteration.
4. WHEN an `error` event is received from the SSE_Stream, THE API_Client SHALL yield an object with `type: "error"`, `error` message, and `retryable` flag, then stop iteration.
5. THE API_Client SHALL support an `AbortSignal` parameter to allow the Chat_UI to cancel an in-progress stream.

### Requirement 7: Chat UI Streaming Display

**User Story:** As a user, I want to see the assistant's response appear token by token in the chat interface, so that I perceive faster response times.

#### Acceptance Criteria

1. WHEN the user sends a message, THE Chat_UI SHALL call the `sendMessageStream` method on the API_Client and begin rendering tokens incrementally in a MessageBubble as they arrive.
2. WHILE tokens are streaming, THE Chat_UI SHALL display a streaming indicator (e.g., a blinking cursor) at the end of the partially rendered message instead of the ThinkingBubble.
3. WHEN the `done` event is received, THE Chat_UI SHALL finalize the message by removing the streaming indicator and attaching the source citations from the metadata.
4. WHEN the user scrolls up during streaming, THE Chat_UI SHALL stop auto-scrolling until the user scrolls back to the bottom.
5. IF an `error` event is received during streaming, THEN THE Chat_UI SHALL display the error message and offer a retry button if the error is retryable.
6. WHEN the user clicks "New Session" or navigates away during an active stream, THE Chat_UI SHALL abort the in-progress stream using the AbortSignal.

### Requirement 8: SSE Event Format

**User Story:** As a developer, I want a well-defined SSE event format for the streaming protocol, so that the frontend and backend have a clear contract.

#### Acceptance Criteria

1. THE Streaming_Endpoint SHALL format token events as: `event: token\ndata: {"content": "<token_text>"}\n\n`.
2. THE Streaming_Endpoint SHALL format the done event as: `event: done\ndata: {"answer": "<full_text>", "session_id": "<id>", "sources": [...], "llm_used": "<model>", "fallback_warning": "<msg>|null", "warnings_present": <bool>}\n\n`.
3. THE Streaming_Endpoint SHALL format error events as: `event: error\ndata: {"error": "<message>", "retryable": <bool>}\n\n`.
4. FOR ALL Stream_Event types, the `data` field SHALL be valid JSON (parseable by `JSON.parse` without error).

### Requirement 9: Legacy Non-Streaming Endpoint Removal

**User Story:** As a developer, I want the old non-streaming chat endpoint and its client-side caller removed, so that there is a single streaming code path to maintain.

#### Acceptance Criteria

1. THE existing non-streaming `POST /api/v1/chat/message` handler (`send_message` in `backend/routers/chat.py`) SHALL be removed and replaced by the Streaming_Endpoint at the same path.
2. THE `ChatMessageResponse` Pydantic model SHALL be removed from `backend/routers/chat.py` since the response is now delivered as an SSE stream.
3. THE API_Client SHALL remove the existing `sendMessage` method and replace it with `sendMessageStream` as the sole method for sending chat messages.
4. THE non-streaming `send_message` method on Chat_Service SHALL be removed; the streaming variant SHALL be the only public send method.
5. THE non-streaming `query` method on RAG_Pipeline and the non-streaming `generate` method on LLM_Router SHALL be preserved, as they are used by non-chat callers (e.g., the diagnose pipeline).
6. THE `README.md` "API — Endpoints principaux" section SHALL be updated to annotate `POST /api/v1/chat/message` as returning an SSE stream (`text/event-stream`) instead of a JSON response.
