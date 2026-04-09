# Requirements Document

## Introduction

Add collapsible side panels to the Chat and Diagnose pages that display previously saved sessions. Users can list, load, and delete past chat conversations and diagnostic consultations directly from the main interface, without navigating to a separate history page.

**Not in scope**: search/filter within the session list (future enhancement).

## Glossary

- **Session_History_Panel**: A collapsible left-side panel component that displays a scrollable list of previously saved sessions (chat or diagnose) with preview information, load, and delete actions.
- **Chat_Page**: The main conversational Q&A page located at `apps/web/src/app/[locale]/chat/page.tsx`.
- **Diagnose_Page**: The symptom diagnosis page located at `apps/web/src/app/[locale]/diagnose/page.tsx`.
- **API_Client**: The shared HTTP client at `packages/api-client/index.ts` used by frontend pages to communicate with the backend.
- **Chat_Session_Summary**: A lightweight object containing `session_id`, `created_at`, `updated_at`, and `preview` (first message content) returned by `GET /api/v1/chat/sessions`.
- **Consultation**: A saved diagnostic result containing symptoms, diagnoses, prescription, and alerts, returned by `GET /api/v1/consultations/me`.
- **Active_Session**: The session currently loaded and displayed in the main content area (chat messages or diagnosis results).

## Requirements

### Requirement 1: Chat Session History Panel — Display

**User Story:** As a practitioner, I want to see a list of my past chat sessions in a side panel, so that I can quickly find and resume previous conversations.

#### Acceptance Criteria

1. THE Chat_Page SHALL render a Session_History_Panel on the left side of the page
2. THE Session_History_Panel SHALL display each Chat_Session_Summary with the preview text (first message) and the formatted date
3. THE Session_History_Panel SHALL sort sessions by most recent `updated_at` first
4. THE Session_History_Panel SHALL display a loading indicator while fetching sessions from the API_Client
5. IF the API_Client returns an error while fetching sessions, THEN THE Session_History_Panel SHALL display a localized error message
6. WHEN the Session_History_Panel contains no sessions, THE Session_History_Panel SHALL display a localized empty-state message

#### Implementation Notes

- Requires adding `chat.listSessions(skip, limit, signal)` to the API_Client, calling `GET /api/v1/chat/sessions` with `skip` and `limit` query parameters. The method SHALL return an object containing a `sessions` array of Chat_Session_Summary objects and SHALL propagate HTTP errors to the caller.

### Requirement 2: Chat Session History Panel — Load Session

**User Story:** As a practitioner, I want to click on a past session to load its full message history, so that I can review or continue the conversation.

#### Acceptance Criteria

1. WHEN a Chat_Session_Summary is clicked, THE Chat_Page SHALL call `apiClient.chat.getHistory(sessionId)` to fetch the full message history
2. WHEN the full message history is loaded, THE Chat_Page SHALL replace the current messages in the chat area with the loaded messages
3. WHEN a session is loaded, THE Chat_Page SHALL update the Active_Session identifier to the loaded session's ID
4. WHEN a session is loaded, THE Chat_Page SHALL persist the loaded session ID to localStorage
5. THE Session_History_Panel SHALL visually highlight the currently Active_Session entry
6. WHILE `getHistory` is in flight, THE Session_History_Panel SHALL show a loading indicator on the clicked entry and disable further entry clicks
7. IF `apiClient.chat.getHistory(sessionId)` returns an error, THEN THE Session_History_Panel SHALL display a localized error message and keep the previous Active_Session unchanged

### Requirement 3: Chat Session History Panel — Delete Session

**User Story:** As a practitioner, I want to delete a past chat session from the history panel, so that I can remove conversations I no longer need.

#### Acceptance Criteria

1. THE Session_History_Panel SHALL display a delete button on each Chat_Session_Summary entry
2. WHEN the delete button is clicked, THE Session_History_Panel SHALL display a confirmation prompt before proceeding
3. WHEN the user confirms deletion, THE Chat_Page SHALL call `apiClient.chat.deleteSession(sessionId)` to remove the session from the backend
4. WHEN the deletion succeeds, THE Session_History_Panel SHALL remove the deleted entry from the displayed list without re-fetching all sessions
5. WHEN the deleted session is the Active_Session, THE Chat_Page SHALL clear the chat area and start a new session
6. IF the API_Client returns an error during deletion, THEN THE Session_History_Panel SHALL display a localized error message

#### Implementation Notes

- Requires adding `chat.deleteSession(sessionId, signal)` to the API_Client, calling `DELETE /api/v1/chat/sessions/{session_id}`. The method SHALL include the CSRF token header and SHALL propagate HTTP errors (including 404) to the caller.

### Requirement 4: Diagnose Consultation History Panel — Display

**User Story:** As a practitioner, I want to see a list of my past diagnostic consultations in a side panel, so that I can quickly review previous results.

#### Acceptance Criteria

1. THE Diagnose_Page SHALL render a Session_History_Panel on the left side of the page
2. THE Session_History_Panel SHALL display each Consultation with the primary diagnosis condition name and the formatted date
3. THE Session_History_Panel SHALL sort consultations by most recent `createdAt` first
4. THE Session_History_Panel SHALL display a loading indicator while fetching consultations from the API_Client
5. IF the API_Client returns an error while fetching consultations, THEN THE Session_History_Panel SHALL display a localized error message
6. WHEN the Session_History_Panel contains no consultations, THE Session_History_Panel SHALL display a localized empty-state message

### Requirement 5: Diagnose Consultation History Panel — Load Consultation

**User Story:** As a practitioner, I want to click on a past consultation to load its full diagnostic results, so that I can review the diagnoses, probabilities, sources, and prescriptions.

#### Acceptance Criteria

1. WHEN a Consultation entry is clicked, THE Diagnose_Page SHALL call `apiClient.diagnose.getSession(sessionId)` to fetch the full diagnostic session
2. WHEN the full diagnostic session is loaded, THE Diagnose_Page SHALL display the loaded diagnoses, probabilities, sources, and prescriptions in the results area
3. THE Session_History_Panel SHALL visually highlight the currently displayed Consultation entry
4. WHILE `getSession` is in flight, THE Session_History_Panel SHALL show a loading indicator on the clicked entry and disable further entry clicks
5. IF `apiClient.diagnose.getSession(sessionId)` returns an error, THEN THE Session_History_Panel SHALL display a localized error message and keep the previous displayed consultation unchanged

### Requirement 6: Diagnose Consultation History Panel — Delete Consultation

**User Story:** As a practitioner, I want to hide a past consultation from the history panel, so that I can declutter results I no longer need.

#### Acceptance Criteria

1. THE Session_History_Panel SHALL display a hide button (eye-off icon) on each Consultation entry
2. WHEN the hide button is clicked, THE Session_History_Panel SHALL immediately remove the entry from the displayed list (no confirmation needed — action is reversible on reload)
3. WHEN the hidden consultation is the currently displayed result, THE Diagnose_Page SHALL clear the results area
4. THE hidden consultation SHALL reappear in the list on next page load (since no backend `DELETE /api/v1/consultations/{id}` endpoint exists — this is client-side only)

#### Implementation Notes

- Use "hide" semantics (eye-off icon, "Hide" label) instead of "delete" to set correct user expectations — the action is temporary and reversible on reload. No confirmation dialog is needed since the action is non-destructive.
- Store hidden consultation IDs in a `Set` in component state; filter them out of the rendered list. The set resets on unmount/page navigation.
- When a backend `DELETE` endpoint is added in the future, this can be upgraded to true deletion with a confirmation prompt (matching the chat panel pattern from Req 3).

### Requirement 7: Session History Panel — Collapse and Expand

**User Story:** As a practitioner, I want to collapse and expand the session history panel on both pages, so that I can maximize the main content area when I do not need the history.

#### Acceptance Criteria

1. THE Session_History_Panel SHALL include a toggle button that collapses the panel to a narrow icon-only strip
2. WHEN the Session_History_Panel is collapsed, THE host page (Chat_Page or Diagnose_Page) SHALL expand the main content area to fill the available width
3. WHEN the toggle button is clicked while the panel is collapsed, THE Session_History_Panel SHALL expand to its full width
4. THE Session_History_Panel SHALL default to the expanded state on initial page load
5. THE Session_History_Panel SHALL automatically collapse on viewports narrower than 768px (matching the app's existing `md:` Tailwind breakpoint used in NavBar)
6. WHEN the viewport is narrower than 768px, THE toggle button SHALL remain visible and functional — the user MAY manually expand the panel on narrow viewports, and it SHALL render as an overlay on top of the main content (not pushing it aside) to avoid layout breakage. WHEN the panel is expanded as an overlay, clicking the backdrop SHALL collapse the panel (matching the NavBar mobile drawer pattern).
7. THE collapse state SHALL NOT persist across page navigations — each page load starts expanded (or auto-collapsed on narrow viewports)

### Requirement 8: Session History Panel — Pagination

**User Story:** As a practitioner with many past sessions, I want the session list to load incrementally, so that the panel remains responsive.

#### Acceptance Criteria

1. THE Session_History_Panel SHALL initially fetch the first 20 sessions (or consultations)
2. WHEN the user scrolls to the bottom of the session list, THE Session_History_Panel SHALL fetch the next page of results (infinite scroll)
3. WHEN all sessions have been loaded, THE Session_History_Panel SHALL stop fetching and display no loading indicator
4. THE Session_History_Panel SHALL display a loading indicator at the bottom of the list while fetching the next page

### Requirement 9: Session History Panel — Refresh Behavior

**User Story:** As a practitioner, I want the session list to stay current as I use the application, so that new sessions appear without manual refresh.

#### Acceptance Criteria

1. THE Session_History_Panel SHALL fetch the session list on initial mount
2. WHEN the `done` SSE event is received after sending a chat message (on Chat_Page), THE Session_History_Panel SHALL upsert the session at the top of the list using the `session_id` from the event and the user message content as preview — if the session already exists in the list, it SHALL be moved to the top with its `updated_at` refreshed; if it is new, it SHALL be prepended
3. WHEN a new diagnosis is submitted and the response is received (on Diagnose_Page), THE Session_History_Panel SHALL prepend the new consultation to the top of the list using the primary diagnosis condition name as preview
4. WHEN the user clicks "New Chat" (on Chat_Page) and the previous session had messages, THE Session_History_Panel SHALL keep the previous session in the list (it is already there from AC 2) — no additional prepend is needed since the new empty session has no history entry until a message is sent
5. WHEN the user deletes a session, THE Session_History_Panel SHALL remove it from the list immediately (optimistic update)

### Requirement 10: Internationalization

**User Story:** As a practitioner using the application in French or English, I want all session history panel text to be translated, so that the interface is consistent with the rest of the application.

#### Acceptance Criteria

1. THE Session_History_Panel SHALL use `next-intl` translation keys for all user-visible text including panel title, empty state, loading state, error messages, delete confirmation, and toggle button labels
2. THE i18n package SHALL include French and English translations for all Session_History_Panel text keys
3. THE Session_History_Panel SHALL display text in the locale selected by the user

### Requirement 11: Layout Non-Interference

**User Story:** As a practitioner, I want the session history panel to coexist with the existing chat and diagnose functionality without breaking the current layout or behavior.

#### Acceptance Criteria

1. THE Session_History_Panel SHALL not interfere with the existing chat message input, streaming, or patient context functionality on the Chat_Page
2. THE Session_History_Panel SHALL not interfere with the existing symptom input, diagnosis submission, or prescription functionality on the Diagnose_Page
3. THE Chat_Page and Diagnose_Page SHALL remain fully functional when the Session_History_Panel is collapsed
4. THE Session_History_Panel SHALL be visible to all authenticated roles that can access the host page (including `guest` on Chat_Page) — the panel uses the same role-gated endpoints as the host page, so no additional role checks are needed

### Requirement 12: Accessibility

**User Story:** As a practitioner using assistive technology, I want the session history panel to be fully keyboard-navigable and screen-reader friendly, so that I can use it without a mouse.

#### Acceptance Criteria

1. THE Session_History_Panel toggle button SHALL have an `aria-expanded` attribute reflecting the current collapse state and an `aria-label` describing the action (e.g., "Collapse session history" / "Expand session history")
2. THE session list SHALL be rendered as a `role="listbox"` with each entry as `role="option"`, and the Active_Session entry SHALL have `aria-selected="true"`
3. THE session list SHALL support arrow-key navigation between entries, with `Enter` to load and `Delete` key to trigger delete/hide
4. WHEN a session is deleted or hidden, keyboard focus SHALL move to the next entry in the list (or the previous entry if the last item was removed)
5. WHEN a session is successfully loaded or deleted, THE Session_History_Panel SHALL announce the result via an `aria-live="polite"` region (consistent with the existing `Toast` component pattern)
6. THE delete confirmation prompt (chat panel) SHALL trap focus within the dialog and return focus to the triggering delete button on cancel
