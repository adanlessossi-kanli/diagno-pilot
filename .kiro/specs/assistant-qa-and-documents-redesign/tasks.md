# Implementation Plan: Assistant Q&A and Documents Redesign

## Overview

This plan implements the redesign of the Assistant Q&A chat page (LLM-only, no RAG, with Topic Guard) and the Documents page (three-panel layout with Document Chat using LlamaIndex RAG pipeline, sidebar for upload/list/download, and session history). Tasks are ordered by the dependency map: backend foundations first, then frontend changes, then integration and polish.

## Tasks

- [x] 1. Database migration script and Pydantic models
  - [x] 1.1 Create the migration script `backend/scripts/migrate_redesign.py`
    - Implement `async def migrate()` that: (1) deletes all documents from `chat_sessions`, (2) creates indexes on `document_chat_sessions` (`session_id` unique, `user_id + updated_at`), (3) creates index on `topic_guard_feedback` (`user_id + timestamp`)
    - Script must be idempotent — running multiple times produces the same result
    - Log the number of deleted sessions
    - Add `if __name__ == "__main__"` block to run via `python -m backend.scripts.migrate_redesign`
    - _Requirements: 10.1, 10.2, 10.3_

  - [x] 1.2 Write property test for migration idempotence
    - **Property 11: Migration Script Idempotence**
    - Use Hypothesis to generate random initial collection sizes (0–100), run migration 1–3 times, verify 0 documents remain and no errors on subsequent runs
    - **Validates: Requirements 10.2**

  - [x] 1.3 Add new Pydantic models to `backend/models/` or inline in routers
    - `DocumentChatRequest(message: str, session_id: str | None)`
    - `DocumentDownloadResponse(url: str, expires_in: int, filename: str, content_disposition: str)`
    - `DocumentChatSessionListResponse` and `DocumentChatHistoryResponse` following existing patterns
    - `TopicGuardFeedbackRequest(question: str, response: str)`
    - _Requirements: 7.1, 7.4, 11.2, 13.3_

- [x] 2. Modify ChatService for LLM-only Q&A with Topic Guard
  - [x] 2.1 Update `backend/services/chat_service.py` to use LLMRouter directly
    - Change constructor to accept `LLMRouter` instead of `LlamaIndexPipeline`
    - Add `ASSISTANT_QA_SYSTEM_PROMPT` constant with Topic Guard instructions (accepted medical topics, `[TOPIC_GUARD_REFUSAL]` marker, language detection)
    - Modify `send_message_stream()` to call `self._llm.generate_stream()` directly (no RAG retrieval)
    - Persist `sources: []` (empty array) for every assistant turn in MongoDB
    - _Requirements: 1.1, 1.4, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [x] 2.2 Write property tests for Topic Guard classification
    - **Property 1: Topic Guard Classification**
    - Generate random medical and non-medical question strings. Mock LLMRouter. Verify non-medical questions produce `[TOPIC_GUARD_REFUSAL]` prefix; medical questions produce substantive answers.
    - **Validates: Requirements 2.3, 2.4, 2.5**

  - [x] 2.3 Write property test for Topic Guard refusal language matching
    - **Property 2: Topic Guard Refusal Language Matching**
    - Generate non-medical questions in FR/EN. Verify refusal language matches input language.
    - **Validates: Requirement 2.6**

  - [x] 2.4 Write property test for Q&A empty sources persistence
    - **Property 3: Q&A Chat Persists Empty Sources Array**
    - Generate random messages, mock LLM. Verify MongoDB document contains `sources: []` for each assistant turn.
    - **Validates: Requirements 1.4**

  - [x] 2.5 Update ChatService initialization in `backend/main.py` (or app startup)
    - Wire `ChatService` to `LLMRouter` instead of `LlamaIndexPipeline`
    - Ensure existing chat router endpoints still work with the modified service
    - _Requirements: 1.1_

- [x] 3. Checkpoint — Ensure all backend Q&A tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Create DocumentChatService and backend document chat endpoints
  - [x] 4.1 Create `backend/services/document_chat_service.py`
    - Implement `DocumentChatService` with `COLLECTION = "document_chat_sessions"`
    - Constructor accepts `AsyncIOMotorDatabase` and `LlamaIndexPipeline`
    - Implement `send_message_stream()` — loads session history, calls `self._rag.query_stream()`, persists user + assistant turns with sources (including highlight/bbox data)
    - Implement `get_history()`, `get_history_paginated()`, `list_sessions()`, `delete_session()` following the same pattern as `ChatService`
    - _Requirements: 5.3, 5.7, 7.1, 7.2, 7.4, 7.5, 7.6_

  - [x] 4.2 Write property test for Document Chat session persistence round-trip
    - **Property 7: Document Chat Session Persistence Round-Trip**
    - Generate random sequences of 1–10 messages. Send via service, retrieve, verify order, content, and sources preserved.
    - **Validates: Requirements 5.3, 7.5**

  - [x] 4.3 Write property test for DocumentSource completeness
    - **Property 9: DocumentSource Completeness with Highlight Data**
    - Generate random queries against a seeded index. Verify all required fields (documentId, title, source, excerpt, page, highlight with bbox) are present.
    - **Validates: Requirements 7.2, 7.4**

  - [x] 4.4 Add document chat endpoints to `backend/routers/documents.py`
    - `POST /documents/chat` — SSE streaming endpoint, rate limited 60/min, roles: admin, medecin, infirmière
    - `GET /documents/chat/sessions` — list user's document chat sessions
    - `GET /documents/chat/history/{session_id}` — get paginated session messages
    - `DELETE /documents/chat/sessions/{session_id}` — delete a session (HTTP 204)
    - `GET /documents/{id}/download` — presigned S3 URL with `Content-Disposition: attachment` and filename
    - Wire `DocumentChatService` dependency
    - _Requirements: 7.1, 7.2, 7.3, 7.5, 11.2_

  - [x] 4.5 Wire `DocumentChatService` in app startup (`backend/main.py` or equivalent)
    - Initialize `DocumentChatService` with database and `LlamaIndexPipeline` instance
    - Store in `app.state.doc_chat_service` for dependency injection
    - Add `get_doc_chat_service()` dependency function in documents router
    - _Requirements: 7.1_

  - [x] 4.6 Write property test for role-based access control
    - **Property 10: Role-Based Access Control**
    - Generate random roles from the full set. Verify admin/medecin/infirmière get 200, others get 403.
    - **Validates: Requirements 7.3, 11.3, 12.1, 12.2**

- [x] 5. Add feedback endpoint to chat router
  - [x] 5.1 Add `POST /api/v1/chat/feedback` endpoint to `backend/routers/chat.py`
    - Accept `TopicGuardFeedbackRequest` (question, response)
    - Persist to `topic_guard_feedback` MongoDB collection with user_id and timestamp
    - Rate limited 30/min, require authentication (all roles)
    - _Requirements: 13.2, 13.3, 13.4, 13.5_

  - [x] 5.2 Write property test for feedback endpoint authentication
    - **Property 12: Feedback Endpoint Authentication**
    - Generate random roles. Verify all authenticated roles succeed, unauthenticated returns 401.
    - **Validates: Requirements 13.4**

- [x] 6. Checkpoint — Ensure all backend tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Add i18n translation keys
  - [x] 7.1 Add new translation keys to `packages/i18n/locales/fr.json` and `packages/i18n/locales/en.json`
    - Add `documentChat` namespace (title, placeholder, send, newSession, thinking, noDocuments, errorSend, errorSendRetry, retry, loadingHistory, sources, noInfoFound)
    - Add `documentSidebar` namespace (uploadTitle, documentTitle, documentSource, selectSource, documentFile, upload, uploading, uploadSuccess, errorUpload, documents, noDocuments, loadingDocuments, errorFetch, errorDelete, confirmDelete, download, errorDownload)
    - Add `topicGuard` namespace (feedbackButton, feedbackSent, feedbackError)
    - Add `sessionHistory.migratedEmpty` key
    - _Requirements: 9.1, 9.2, 9.3, 10.4_

- [x] 8. Extend `@diagno-pilot/api-client` with Document Chat methods
  - [x] 8.1 Add new methods to the documents namespace in `packages/api-client/index.ts`
    - `documents.chatStream(sessionId, message, signal)` — SSE streaming following the same pattern as `chat.sendMessageStream()`
    - `documents.listChatSessions(skip?, limit?)` — GET `/documents/chat/sessions`
    - `documents.getChatHistory(sessionId, signal?)` — GET `/documents/chat/history/{sessionId}`
    - `documents.deleteChatSession(sessionId)` — DELETE `/documents/chat/sessions/{sessionId}`
    - `documents.getDownloadUrl(documentId)` — GET `/documents/{id}/download`
    - _Requirements: 5.2, 5.4, 11.2_

- [x] 9. Modify chat page — remove sources, add Topic Guard detection and feedback
  - [x] 9.1 Update `apps/web/src/app/[locale]/chat/page.tsx`
    - Remove `SourcesPanel` rendering from `MessageBubble` (remove the component and its import)
    - Remove `CitationChip` import and rendering from the chat page
    - Ignore `sources` array from `done` SSE events (do not render any citation UI)
    - Detect `[TOPIC_GUARD_REFUSAL]` marker in assistant message content — strip the marker from displayed text
    - Show "This is a medical question" feedback button below refusal messages (using `topicGuard.feedbackButton` i18n key)
    - On feedback button click, call `POST /api/v1/chat/feedback` with the original question and refusal response
    - Show feedback confirmation or error toast
    - _Requirements: 1.2, 1.3, 2.4, 13.1, 13.2, 13.5_

  - [x] 9.2 Write unit tests for chat page changes
    - Test that `SourcesPanel` and `CitationChip` are not rendered for assistant messages
    - Test that `[TOPIC_GUARD_REFUSAL]` marker is detected and stripped from display
    - Test that feedback button appears on refusal messages and triggers API call
    - _Requirements: 1.2, 1.3, 13.1_

- [x] 10. Rewrite Documents page with three-panel layout
  - [x] 10.1 Create `DocumentSidebar` component
    - Upload form (title, source, file picker, submit button) with file format validation (PDF, DOCX, TXT, CSV only)
    - Document list with title, source, date, download button, and delete button (admin only for delete)
    - Download flow: call `apiClient.documents.getDownloadUrl()`, create temporary `<a>` element with `download` attribute, programmatically click to trigger browser download, remove element from DOM
    - Progress indicator with elapsed time during upload
    - Error/success messages for upload, fetch, delete, and download operations
    - Empty state message when no documents
    - Scrollable list with `overflow-y-auto` and `overflow-x-hidden`
    - All text uses `next-intl` translation keys from `documentSidebar` namespace
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 4.1, 4.2, 4.3, 4.4, 4.5, 9.2, 11.1, 11.2, 11.4_

  - [x] 10.2 Write property tests for file format validation (fast-check)
    - **Property 4: File Format Validation**
    - Generate random file extensions. Verify acceptance iff extension (case-insensitive) is in `{pdf, docx, txt, csv}`.
    - **Validates: Requirements 3.3**

  - [x] 10.3 Write property tests for document list updates (fast-check)
    - **Property 5: Document List Update on Upload** — Generate random document arrays + new document. Verify list grows by 1.
    - **Property 6: Document List Update on Delete** — Generate random document arrays + random index. Verify deletion removes exactly one.
    - **Validates: Requirements 3.2, 4.2**

  - [x] 10.4 Create `DocumentChat` component
    - Chat interface with message input, send button, and message bubbles
    - SSE streaming via `apiClient.documents.chatStream()` with `AbortController`
    - Render `CitationChip` components from `done` event sources array
    - Session management: create new sessions, switch between sessions via `SessionHistoryPanel`
    - Error handling: show error message + retry button for retryable errors, "[Response interrupted]" for stream drops
    - Smart auto-scroll (scroll to bottom unless user scrolled up)
    - Streaming cursor animation while tokens arrive
    - All text uses `next-intl` translation keys from `documentChat` namespace
    - _Requirements: 5.1, 5.2, 5.4, 5.5, 5.6, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 9.1_

  - [x] 10.5 Write property test for Citation Chips rendering (fast-check)
    - **Property 8: Citation Chips Rendered for Non-Empty Sources**
    - Generate random sources arrays of length 0–10. Verify chip count matches sources length.
    - **Validates: Requirements 6.1**

  - [x] 10.6 Write property test for highlight bbox positioning (fast-check)
    - **Property 13: Highlight BBox Positioning**
    - Generate random bbox coordinates and page dimensions. Verify computed pixel positions correspond to correct location.
    - **Validates: Requirements 6.4**

  - [x] 10.7 Write property test for SSE stream completeness (fast-check)
    - **Property 14: Document Chat SSE Stream Completeness**
    - Simulate SSE streams with random token sequences. Verify concatenation of all `token.content` values equals `done.answer`. Verify `done` event includes `session_id` and `sources` array.
    - **Validates: Requirements 5.2, 5.5, 7.1**

  - [x] 10.8 Write property test for stream abort safety (fast-check)
    - **Property 15: Document Chat Stream Abort Safety**
    - Simulate in-progress SSE streams aborted via AbortController. Verify no error message is displayed and empty placeholder messages are removed.
    - **Validates: Requirements 5.6**

  - [x] 10.9 Rewrite `apps/web/src/app/[locale]/documents/page.tsx` with three-panel layout
    - Compose `SessionHistoryPanel` (left), `DocumentChat` (center), `DocumentSidebar` (right)
    - Responsive layout with Tailwind CSS: sidebar `w-[25%] min-w-[280px] max-w-[380px]`, chat `flex-1`, session panel `w-[200px]`
    - Mobile (<768px): sidebar hidden by default (`hidden md:flex`), toggle button, fixed overlay with backdrop
    - Access control: verify user role on load, redirect unauthorized roles (`pharmacien`, `guest`) to home page
    - Disable chat input if auth token expired/missing with re-authentication prompt
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 12.1, 12.2, 12.3_

  - [x] 10.10 Write unit tests for Documents page
    - Test responsive layout at different viewports
    - Test access control redirect for unauthorized roles
    - Test DocumentChat SSE streaming (simulate token/done/error events)
    - Test DocumentSidebar upload form, empty/error states
    - _Requirements: 8.1, 12.1, 12.2_

- [x] 11. Checkpoint — Ensure all frontend and backend tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 12. Update README.md
  - [x] 12.1 Update `README.md`
    - Update "Chat Q&A RAG" feature description to reflect LLM-only mode with Topic Guard (no sources, medical-topic restriction)
    - Add "Chat Documents RAG" feature bullet describing Document Chat with citations
    - Add new endpoints to the API section: `POST /documents/chat`, `GET /documents/{id}/download`, `POST /chat/feedback`, `GET /documents/chat/sessions`, `GET /documents/chat/history/{id}`, `DELETE /documents/chat/sessions/{id}`
    - Update roles table: add Document Chat access for `medecin`, `infirmière`, `admin`
    - Add migration subsection for `python -m backend.scripts.migrate_redesign` with warning about permanent session deletion
    - _Requirements: 1.1, 7.3, 10.1_

- [x] 13. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document (P1–P15)
- Unit tests validate specific examples and edge cases
- Backend uses Python (pytest + Hypothesis), frontend uses TypeScript (Vitest + fast-check)
