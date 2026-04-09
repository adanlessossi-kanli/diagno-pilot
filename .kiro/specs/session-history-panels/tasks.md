# Implementation Plan: Session History Panels

## Overview

Add collapsible session history side panels to the Chat and Diagnose pages. Implementation proceeds bottom-up: types/schemas first, then API client methods, then shared UI components, then page-level integration for Chat, then Diagnose, and finally wiring refresh behaviors and accessibility polish.

## Tasks

- [x] 1. Create MongoDB compound index for chat session listing
  - [x] 1.1 Add compound index `{ user_id: 1, updated_at: -1 }` to `chat_sessions` in `backend/main.py` startup
    - Add alongside the existing TTL index on `chat_sessions.updated_at` (~line 116)
    - Use `background=True` and name `user_id_1_updated_at_-1`
    - This index supports the `list_sessions` query which filters by `user_id` and sorts by `updated_at` desc
    - The `consultations` collection already has the equivalent `(user_id, created_at)` index
    - _Requirements: 1.3, 8.1_

  - [x] 1.2 Create migration script `backend/scripts/migrate_chat_sessions_add_user_index.py`
    - Follow the existing pattern from `migrate_users_add_email_index.py`: idempotent, standalone-runnable via `python -m backend.scripts.migrate_chat_sessions_add_user_index`
    - Create the same `{ user_id: 1, updated_at: -1 }` compound index
    - No data backfill needed — all existing documents already have `user_id` and `updated_at` fields
    - _Requirements: 1.3, 8.1_

- [x] 2. Add Zod schemas and API client methods for chat sessions
  - [x] 2.1 Create `ChatSessionSummarySchema` and `ChatSessionListResponseSchema` Zod schemas in `packages/types/index.ts`
    - Add `ChatSessionSummarySchema` with fields: `sessionId` (string), `createdAt` (string nullable), `updatedAt` (string nullable), `preview` (string nullable)
    - Add `ChatSessionListResponseSchema` with field: `sessions` (array of `ChatSessionSummarySchema`)
    - Export both schemas and their inferred TypeScript types
    - _Requirements: 1.1, 1.2_

  - [x] 2.2 Add `chat.listSessions()` and `chat.deleteSession()` methods to `packages/api-client/index.ts`
    - `listSessions(skip?: number, limit?: number, signal?: AbortSignal)` calls `GET /api/v1/chat/sessions?skip={skip}&limit={limit}` and passes `ChatSessionListResponseSchema` to `parseResponse` for snake_case → camelCase normalization
    - `deleteSession(sessionId: string, signal?: AbortSignal)` calls `DELETE /api/v1/chat/sessions/{session_id}` with CSRF headers via the existing `del` helper
    - Import `ChatSessionListResponseSchema` from `@diagno-pilot/types`
    - _Requirements: 1 (impl note), 3 (impl note)_

  - [x] 2.3 Write unit tests for `chat.listSessions` and `chat.deleteSession`
    - Test that `listSessions` passes the Zod schema and normalizes keys correctly
    - Test that `deleteSession` includes CSRF header and handles 404 errors
    - _Requirements: 1 (impl note), 3 (impl note)_

- [x] 3. Add i18n translations for session history panel
  - [x] 3.1 Add `sessionHistory` namespace to `packages/i18n/locales/en.json` and `packages/i18n/locales/fr.json`
    - Add all keys defined in the design: `title`, `chatTitle`, `diagnoseTitle`, `empty`, `emptyDiagnose`, `loading`, `loadingMore`, `errorFetch`, `errorLoad`, `errorDelete`, `errorHide`, `delete`, `hide`, `confirmDeleteTitle`, `confirmDeleteMessage`, `cancel`, `confirm`, `collapse`, `expand`, `sessionLoaded`, `sessionDeleted`, `sessionHidden`
    - Use the exact English and French strings from the design document
    - _Requirements: 10.1, 10.2, 10.3_

- [x] 4. Implement shared UI components
  - [x] 4.1 Create `ConfirmDialog` component at `apps/web/src/components/ConfirmDialog.tsx`
    - Implement props: `open`, `title`, `message`, `confirmLabel`, `cancelLabel`, `onConfirm`, `onCancel`
    - Use `role="alertdialog"` and `aria-modal="true"`
    - Implement focus trapping: on open, focus the cancel button; trap Tab/Shift+Tab within the dialog; on cancel, return focus to the triggering element
    - Close on Escape key press
    - Render a backdrop overlay
    - _Requirements: 3.2, 12.6_

  - [x] 4.2 Create `SessionHistoryPanel` component at `apps/web/src/components/SessionHistoryPanel.tsx`
    - Implement the full `SessionHistoryPanelProps` interface from the design
    - Render collapsible panel with toggle button (`aria-expanded`, `aria-label`)
    - Render session entries as `role="listbox"` with `role="option"` items
    - Highlight active entry with `aria-selected="true"`
    - Implement keyboard navigation: ArrowUp/ArrowDown to move focus, Enter to select, Delete to trigger delete/hide
    - Implement infinite scroll via `IntersectionObserver` on a sentinel element at the bottom of the list
    - Show loading, error, and empty states
    - Show `ConfirmDialog` when `deleteMode === 'confirm'` and delete button is clicked
    - For `deleteMode === 'instant'`, call `onDelete` immediately (eye-off icon, "Hide" label)
    - Include `aria-live="polite"` region for `announceMessage`
    - Display `operationError` as an inline transient error message
    - Auto-collapse on viewports < 768px using `matchMedia`; render as overlay on narrow viewports
    - Default to expanded state on mount
    - Panel width: `w-72` when expanded, ~48px when collapsed
    - After deletion, move focus to `min(deletedIndex, entries.length - 2)` entry
    - _Requirements: 1.1–1.6, 2.5–2.7, 3.1–3.4, 4.1–4.6, 5.3–5.5, 6.1–6.2, 7.1–7.7, 8.1–8.4, 12.1–12.5_

  - [x] 4.3 Write property test: Entry display contains preview and formatted date (Property 1)
    - **Property 1: Entry display contains preview and formatted date**
    - Generate random arrays of `SessionEntry` objects with non-empty `preview` and valid ISO date strings
    - Assert each rendered entry contains its `preview` text and a formatted date
    - **Validates: Requirements 1.2, 4.2**

  - [x] 4.4 Write property test: Panel preserves input entry order (Property 2)
    - **Property 2: Panel preserves input entry order**
    - Generate random arrays of `SessionEntry` objects
    - Assert rendered list order matches input array order
    - **Validates: Requirements 1.3, 4.3**

  - [x] 4.5 Write property test: Exactly one entry is marked active or none when null (Property 3)
    - **Property 3: Exactly one entry is marked active (or none when activeId is null)**
    - Generate non-empty arrays and pick a random `activeId` from the entries or `null`
    - When `activeId` matches an entry: assert exactly one `aria-selected="true"` element exists and its ID matches `activeId`
    - When `activeId` is `null`: assert zero entries have `aria-selected="true"`
    - **Validates: Requirements 2.5, 5.3, 12.2**

  - [x] 4.6 Write property test: Toggle collapse is a round-trip and aria-expanded reflects state (Property 7)
    - **Property 7: Toggle collapse is a round-trip and aria-expanded reflects state**
    - Generate random initial collapse states
    - Assert toggling inverts state and `aria-expanded` matches; double-toggle restores original
    - **Validates: Requirements 7.3, 12.1**

  - [x] 4.7 Write property test: Arrow key navigation moves focus correctly (Property 8)
    - **Property 8: Arrow key navigation moves focus correctly**
    - Generate lists of length > 1 and random starting focus index
    - Assert ArrowDown moves to `min(i+1, n-1)`, ArrowUp moves to `max(i-1, 0)`, focused entry has `tabindex="0"`
    - **Validates: Requirements 12.3**

  - [x] 4.8 Write property test: Focus moves to correct entry after deletion (Property 9)
    - **Property 9: Focus moves to correct entry after deletion**
    - Generate lists of length > 1 and random deletion index
    - Assert focus moves to `min(deletedIndex, n-2)` after deletion
    - **Validates: Requirements 12.4**

  - [x] 4.9 Write property test: Removing an entry preserves all other entries in order (Property 4)
    - **Property 4: Removing an entry preserves all other entries in order**
    - Test list removal logic: generate arrays and a random ID to remove
    - Assert removed ID is absent, all others present, relative order preserved
    - **Validates: Requirements 3.4, 6.2, 9.5**

  - [x] 4.10 Write property test: Upsert places session at top of list (Property 5)
    - **Property 5: Upsert places session at top of list**
    - Test upsert logic with existing and new session IDs
    - Assert upserted session is at index 0; list length unchanged for existing, +1 for new
    - **Validates: Requirements 9.2**

  - [x] 4.11 Write property test: Prepend places new entry at index 0 (Property 6)
    - **Property 6: Prepend places new entry at index 0**
    - Test prepend logic: generate arrays and a new entry
    - Assert new entry is at index 0, list length is original + 1, all previous entries maintain order
    - **Validates: Requirements 9.3**

- [x] 5. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Integrate session history panel into Chat page
  - [x] 6.1 Add session list state and fetching logic to `apps/web/src/app/[locale]/chat/page.tsx`
    - Add state: `sessions`, `sessionsLoading`, `sessionsError`, `sessionsHasMore`, `sessionsPage`, `selectingId`, `operationError`, `announceMessage`
    - Fetch sessions on mount via `apiClient.chat.listSessions(0, 20)`
    - Implement `handleLoadMore` to fetch next page and append to `sessions`
    - Set `sessionsHasMore = false` when the returned page has fewer items than `limit` (i.e., `sessions.length < 20`), since the chat endpoint has no `total` count
    - Map `ChatSessionSummary` to `SessionEntry`: `{ id: s.sessionId, preview: s.preview ?? '—', date: s.updatedAt ?? s.createdAt ?? '' }`
    - _Requirements: 1.1–1.6, 8.1–8.4, 9.1_

  - [x] 6.2 Implement session load handler on Chat page
    - On select: set `selectingId`, call `apiClient.chat.getHistory(id)`, replace `messages`, update `sessionId` state and localStorage, clear `selectingId`, set `announceMessage`
    - On error: clear `selectingId`, set `operationError`, keep previous messages unchanged
    - _Requirements: 2.1–2.7_

  - [x] 6.3 Implement session delete handler on Chat page
    - On delete: optimistically remove entry from `sessions` (save snapshot), call `apiClient.chat.deleteSession(id)`
    - On success: set `announceMessage`; if deleted session is active, clear messages and start new session (clear localStorage, generate new session ID)
    - On error: restore snapshot, set `operationError`
    - _Requirements: 3.1–3.6, 9.5_

  - [x] 6.4 Implement SSE upsert for session list on Chat page
    - In the `done` SSE event handler: upsert session at top of `sessions` list using `session_id` from event and user message content as preview
    - If session already exists, move to top with refreshed `updatedAt`; if new, prepend
    - Deduplicate by session ID when merging with pagination results
    - _Requirements: 9.2, 9.4_

  - [x] 6.5 Wire `SessionHistoryPanel` into Chat page layout
    - Wrap existing layout in a horizontal flex container (`flex h-screen`)
    - Place `SessionHistoryPanel` on the left, main content on the right (`flex-1`)
    - Pass all state and handlers as props
    - Use `deleteMode="confirm"`, `panelTitle` from `t('sessionHistory.chatTitle')`, `deleteLabel` from `t('sessionHistory.delete')`
    - _Requirements: 1.1, 7.1–7.7, 11.1, 11.3_

  - [x] 6.6 Write unit tests for Chat page session history integration
    - Test loading state shown while fetching sessions
    - Test error state displayed on fetch failure
    - Test empty state when no sessions
    - Test clicking entry loads session and updates localStorage
    - Test deleting active session clears chat and starts new session
    - Test SSE done event upserts session in list
    - _Requirements: 1.4, 1.5, 1.6, 2.1, 2.4, 3.5, 9.2_

- [x] 7. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Integrate session history panel into Diagnose page
  - [x] 8.1 Add consultation list state and fetching logic to `apps/web/src/app/[locale]/diagnose/page.tsx`
    - Add state: `consultations`, `consultationsLoading`, `consultationsError`, `consultationsHasMore`, `consultationsPage`, `hiddenIds` (Set), `selectingId`, `operationError`, `announceMessage`
    - Fetch consultations on mount via `apiClient.diagnose.listMyConsultations(1, 20)`
    - Implement `handleLoadMore` to fetch next page and append
    - Compute `consultationsHasMore` from `loadedCount < response.total` (the consultations endpoint returns `PaginatedResponse` with a `total` field)
    - Map `Consultation` to `SessionEntry`: `{ id: c.id, preview: c.diagnoses[0]?.condition ?? '', date: c.createdAt }`
    - Filter out `hiddenIds` from rendered entries
    - _Requirements: 4.1–4.6, 8.1–8.4, 9.1_

  - [x] 8.2 Implement consultation load handler on Diagnose page
    - On select: set `selectingId`, call `apiClient.diagnose.getSession(id)`, display results using `mapSessionToPartialResponse`, clear `selectingId`, set `announceMessage`
    - On error: clear `selectingId`, set `operationError`, keep previous results unchanged
    - _Requirements: 5.1–5.5_

  - [x] 8.3 Implement consultation hide handler on Diagnose page
    - On hide: add ID to `hiddenIds` Set (no backend call, no confirmation)
    - If hidden consultation is currently displayed, clear results area
    - Set `announceMessage` for screen reader announcement
    - _Requirements: 6.1–6.4_

  - [x] 8.4 Implement new diagnosis prepend on Diagnose page
    - After successful `handleSubmit`, prepend new consultation to `consultations` list using `response.sessionId` and primary diagnosis as preview
    - _Requirements: 9.3_

  - [x] 8.5 Wire `SessionHistoryPanel` into Diagnose page layout
    - Wrap existing layout in a horizontal flex container
    - Place `SessionHistoryPanel` on the left, main content on the right (`flex-1`)
    - Pass all state and handlers as props
    - Use `deleteMode="instant"`, `panelTitle` from `t('sessionHistory.diagnoseTitle')`, `deleteLabel` from `t('sessionHistory.hide')`
    - _Requirements: 4.1, 7.1–7.7, 11.2, 11.3_

  - [x] 8.6 Write unit tests for Diagnose page session history integration
    - Test loading state shown while fetching consultations
    - Test error state displayed on fetch failure
    - Test empty state when no consultations
    - Test clicking entry loads consultation results
    - Test hide button removes entry from list without confirmation
    - Test hidden consultation reappears on remount
    - Test new diagnosis prepends to list
    - _Requirements: 4.4, 4.5, 4.6, 5.1, 6.1, 6.2, 6.4, 9.3_

- [x] 9. Update project documentation
  - [x] 9.1 Add chat session endpoints to `README.md` endpoint listing
    - Add `GET /api/v1/chat/sessions` and `DELETE /api/v1/chat/sessions/{session_id}` after the existing `GET /api/v1/chat/history/{session_id}` line
    - _Requirements: N/A (documentation)_

  - [x] 9.2 Fix `GET /api/v1/chat/sessions` response example in `docs/api-reference.md`
    - Replace the current response example (which shows raw MongoDB projection with `messages` array) with the actual `ChatSessionListResponse` shape: `{ "sessions": [{ "session_id": "...", "created_at": "...", "updated_at": "...", "preview": "..." }] }`
    - _Requirements: N/A (documentation)_

- [x] 10. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate the 9 correctness properties from the design document using `fast-check`
- Unit tests validate specific examples and edge cases using `vitest`
- The `ChatSessionListResponseSchema` Zod schema is critical for `normalizeKeys` to run on the `listSessions` response
