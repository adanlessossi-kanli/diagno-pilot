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

### Requirement 6: Diagnose Consultation History Panel — Delete Consultation

**User Story:** As a practitioner, I want to delete a past consultation from the history panel, so that I can remove results I no longer need.

#### Acceptance Criteria

1. THE Session_History_Panel SHALL display a delete button on each Consultation entry
2. WHEN the delete button is clicked, THE Session_History_Panel SHALL display a confirmation prompt before proceeding
3. WHEN the user confirms deletion, THE Session_History_Panel SHALL remove the entry from the local displayed list only (client-side removal), since no backend `DELETE /api/v1/diagnose/session/{session_id}` endpoint exists
4. WHEN the deleted consultation is the currently displayed result, THE Diagnose_Page SHALL clear the results area
5. THE deleted consultation SHALL reappear in the list on next page load (since it is not deleted server-side) — this is a known limitation documented in the UI via a tooltip or footnote

### Requirement 7: Session History Panel — Collapse and Expand

**User Story:** As a practitioner, I want to collapse and expand the session history panel on both pages, so that I can maximize the main content area when I do not need the history.

#### Acceptance Criteria

1. THE Session_History_Panel SHALL include a toggle button that collapses the panel to a narrow icon-only strip
2. WHEN the Session_History_Panel is collapsed, THE host page (Chat_Page or Diagnose_Page) SHALL expand the main content area to fill the available width
3. WHEN the toggle button is clicked while the panel is collapsed, THE Session_History_Panel SHALL expand to its full width
4. THE Session_History_Panel SHALL default to the expanded state on initial page load
5. THE Session_History_Panel SHALL automatically collapse on viewports narrower than 768px
6. THE collapse state SHALL NOT persist across page navigations — each page load starts expanded (or auto-collapsed on narrow viewports)

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
2. WHEN the user sends a new chat message (on Chat_Page) or submits a new diagnosis (on Diagnose_Page), THE Session_History_Panel SHALL prepend the new/updated session to the top of the list without re-fetching all sessions
3. WHEN the user clicks "New Chat" (on Chat_Page), THE Session_History_Panel SHALL prepend the newly created session entry (if the previous session had messages)
4. WHEN the user deletes a session, THE Session_History_Panel SHALL remove it from the list immediately (optimistic update)

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
