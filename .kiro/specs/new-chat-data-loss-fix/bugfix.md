# Bugfix Requirements Document

## Introduction

When a user clicks "New Chat" on the chat page, the current chat messages are immediately cleared from local state. The backend persists messages only after the SSE stream completes (not incrementally during streaming), so any in-progress or recently-completed conversation may not yet be saved when the user clicks "New Chat." Additionally, diagnostic results on the diagnose page are stored only in ephemeral component state and are lost on navigation or component unmount.

No data migration is required. The backend already persists both chat sessions and diagnosis sessions to MongoDB. The relevant backend endpoints:

- `GET /api/v1/chat/history/{session_id}` — retrieve a chat session's messages
- `GET /api/v1/chat/sessions` — list the user's chat sessions (paginated)
- `DELETE /api/v1/chat/sessions/{session_id}` — delete a chat session
- `GET /api/v1/diagnose/session/{session_id}` — retrieve a single diagnose session (returns `DiagnoseSession` with fields: `id`, `symptoms`, `diagnoses`, `prescription`, `alerts`, `createdAt`)
- `GET /api/v1/consultations/me` — list the user's consultations (paginated)

The API client (`packages/api-client`) currently only exposes `chat.getHistory()` and `chat.sendMessageStream()`. It does **not** expose `chat.listSessions()` or `chat.deleteSession()`. The `diagnose` namespace exposes `diagnose.getSession()` and `diagnose.listMyConsultations()` but no delete method.

**Backend persistence model**: Messages are written to MongoDB in a single `update_one` after the SSE stream completes — both user and assistant turns are pushed together on success, or only the user turn on mid-stream error. Messages are NOT saved incrementally during token streaming.

**Type mismatch note**: The diagnose page renders `DiagnosisResponse` (which includes `sessionId`, `confidenceScore`, `llmUsed`, `sources`, `warningsPresent`, `fallbackWarning`, `degradedWarning`, `parseFailed`, `agentContributions`, `evidenceCitations`). The `GET /api/v1/diagnose/session/{session_id}` endpoint returns `DiagnoseSession` (which includes `id`, `symptoms`, `diagnoses`, `prescription`, `alerts`, `createdAt`). Restored results will be partial — only `diagnoses` and `prescription` overlap. Fields like `confidenceScore`, `sources`, `evidenceCitations`, `agentContributions`, and warnings will not be available on restore.

**Not in scope** (separate specs): stream interruption indicators, source relevance filtering, and session history side panels.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN the user clicks "New Chat" while a chat session has messages THEN the system immediately clears all messages from local state via `setMessages([])` and clears the session ID from localStorage, without verifying that the backend has persisted the current session's messages — if the last message's stream completed, the data exists server-side but the local reference is destroyed; if a stream is still in progress, the data may be lost entirely

1.2 WHEN the user navigates away from the diagnose page after receiving diagnostic results (e.g., navigates to chat page and back) THEN the system loses all diagnostic results because they are stored only in ephemeral React component state (`useState`) with no persistence mechanism, even though the backend persisted the session server-side

### Expected Behavior (Correct)

2.1 WHEN the user clicks "New Chat" while a chat session has messages and no stream is in progress THEN the system SHALL verify the session exists on the backend via `GET /api/v1/chat/history/{session_id}` (with a 3-second timeout) before clearing local state, to confirm the conversation was persisted

2.2 WHEN the user clicks "New Chat" while a stream is actively in progress THEN the system SHALL abort the stream first, then skip the backend verification (since the backend may not have persisted yet) and clear local state immediately — accepting that the in-progress response may be lost

2.3 WHEN the backend verification succeeds (session exists with messages) THEN the system SHALL clear local state and start a fresh session; the previous session SHALL remain retrievable via the chat history API

2.4 WHEN the backend verification fails (network error, 404, or timeout) THEN the system SHALL display an error notification and SHALL NOT clear the current session's messages, allowing the user to retry or continue

2.5 WHILE the backend verification call is in flight THEN the system SHALL disable the "New Chat" button and display a brief loading indicator to prevent double-clicks

2.6 WHEN the user navigates away from the diagnose page after receiving diagnostic results THEN the system SHALL preserve the last diagnostic session ID in sessionStorage (namespaced by user ID to prevent cross-user collisions) so results can be restored on return

2.7 WHEN the user navigates from the diagnose page to the chat page and back THEN the system SHALL restore and display the previously obtained diagnostic results by fetching them from the backend via `GET /api/v1/diagnose/session/{session_id}` — note that restored results will be partial (only `diagnoses`, `prescription`, `alerts` available; `confidenceScore`, `sources`, `evidenceCitations`, `agentContributions`, warnings will not be shown)

### Unchanged Behavior (Regression Prevention)

3.1 WHEN the user clicks "New Chat" and there are no messages in the current session THEN the system SHALL CONTINUE TO generate a new session ID and reset state without attempting any backend interaction

3.2 WHEN the user sends a message in the chat THEN the system SHALL CONTINUE TO stream the response via SSE and display messages with real-time token appending as before

3.3 WHEN the user submits symptoms on the diagnose page THEN the system SHALL CONTINUE TO call the `POST /api/v1/diagnose/symptoms` endpoint and display results in the same manner

3.4 WHEN the user restores a chat session from localStorage on page load THEN the system SHALL CONTINUE TO fetch and display the session's message history from the backend via `GET /api/v1/chat/history/{session_id}`

3.5 WHEN the user clicks "New Chat" while a stream is in progress THEN the system SHALL CONTINUE TO abort the stream via AbortController — the fix changes the post-abort behavior (skip verification, clear immediately) but the abort itself is unchanged

3.6 WHEN the assistant's streamed response completes successfully with a "done" SSE event THEN the system SHALL CONTINUE TO display the full response and all sources as before


---

## Bug Condition Derivation

### Bug Condition 1 — Chat Data Loss on "New Chat"

```pascal
FUNCTION isBugCondition_ChatDataLoss(X)
  INPUT: X of type NewChatAction { sessionId: string, messages: ChatMessage[], streamInProgress: boolean }
  OUTPUT: boolean

  // Bug triggers when "New Chat" is clicked and there are existing messages
  RETURN X.messages.length > 0
END FUNCTION
```

**Counterexample:** User has 5 messages in session "session-abc", clicks "New Chat" → all 5 messages are lost from the UI, and the user has no way to return to that conversation.

### Property 1 — Chat Fix Checking

```pascal
// Fix Checking: Session existence is verified before clearing local state (non-streaming case)
FOR ALL X WHERE isBugCondition_ChatDataLoss(X) AND NOT X.streamInProgress DO
  backendSession ← backend.getHistory(X.sessionId, timeout=3s)
  IF backendSession EXISTS AND backendSession.messages.length > 0 THEN
    result ← handleNewSession'(X)
    ASSERT result.localMessages = []
    ASSERT result.sessionId ≠ X.sessionId
  ELSE
    // Backend doesn't have the session — block the clear
    ASSERT result.errorDisplayed = true
    ASSERT result.localMessages = X.messages
  END IF
END FOR

// Fix Checking: Active stream case — abort and clear immediately
FOR ALL X WHERE isBugCondition_ChatDataLoss(X) AND X.streamInProgress DO
  result ← handleNewSession'(X)
  ASSERT result.streamAborted = true
  ASSERT result.localMessages = []
  ASSERT result.sessionId ≠ X.sessionId
END FOR
```

### Bug Condition 2 — Diagnostic Data Loss on Navigation

```pascal
FUNCTION isBugCondition_DiagnoseDataLoss(X)
  INPUT: X of type DiagnoseState { results: DiagnosisResponse | null, sessionId: string | null, userId: string, navigatesAway: boolean }
  OUTPUT: boolean

  // Bug triggers when user navigates away while diagnostic results exist
  RETURN X.results ≠ null AND X.sessionId ≠ null AND X.navigatesAway
END FUNCTION
```

**Counterexample:** User submits symptoms, receives 3 diagnoses with session ID "diag-xyz", navigates to chat page, navigates back → results area is empty, user must re-submit.

### Property 2 — Diagnose Fix Checking

```pascal
// Fix Checking: Diagnostic results survive navigation round-trip (partial restore)
FOR ALL X WHERE isBugCondition_DiagnoseDataLoss(X) DO
  navigateAway()
  storedKey ← sessionStorage.getItem('diagno-pilot-diagnose-session-' + X.userId)
  ASSERT storedKey = X.sessionId
  navigateBack()
  restoredSession ← fetchFromBackend(X.sessionId)  // Returns DiagnoseSession, not DiagnosisResponse
  ASSERT restoredSession ≠ null
    AND restoredSession.diagnoses.length = X.results.diagnoses.length
END FOR
```

### Preservation Goals

```pascal
// Preservation 1: Non-buggy "New Chat" (empty session) behaves identically
FOR ALL X WHERE NOT isBugCondition_ChatDataLoss(X) DO
  ASSERT handleNewSession(X) = handleNewSession'(X)
END FOR

// Preservation 2: Non-buggy navigation (no results) behaves identically
FOR ALL X WHERE NOT isBugCondition_DiagnoseDataLoss(X) DO
  ASSERT diagnosePage(X) = diagnosePage'(X)
END FOR
```
