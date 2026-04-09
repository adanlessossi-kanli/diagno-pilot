# New Chat Data Loss Fix — Bugfix Design

## Overview

Two data-loss bugs exist in the frontend. First, clicking "New Chat" on the chat page immediately clears local state (`setMessages([])`) and removes the session ID from localStorage without verifying that the backend has persisted the conversation. Because the backend writes messages to MongoDB only after the SSE stream completes (not incrementally), a race condition can destroy the user's only reference to a conversation. Second, diagnostic results on the diagnose page live exclusively in ephemeral `useState` — navigating away and back loses all results even though the backend already persisted them via `POST /api/v1/diagnose/symptoms`.

The fix strategy is purely frontend:
1. Make `handleNewSession` async — verify session persistence via `GET /api/v1/chat/history/{session_id}` before clearing state (with a 3-second timeout). Skip verification when aborting an active stream.
2. Store the last diagnose session ID in `sessionStorage` (namespaced by user ID) and restore partial results from `GET /api/v1/diagnose/session/{session_id}` on mount.

No backend changes are required.

## Glossary

- **Bug_Condition (C)**: The condition that triggers data loss — (1) clicking "New Chat" when messages exist, or (2) navigating away from the diagnose page when results are present
- **Property (P)**: The desired behavior — (1) session existence is confirmed before clearing (or stream is aborted and cleared immediately), or an error is shown; (2) diagnostic results survive navigation round-trips (partial restore)
- **Preservation**: Existing behaviors that must remain unchanged — empty-session "New Chat", SSE streaming, symptom submission, session restore on page load, abort-on-unmount
- **handleNewSession**: The function in `apps/web/src/app/[locale]/chat/page.tsx` that resets chat state when "New Chat" is clicked
- **DiagnosePage**: The component in `apps/web/src/app/[locale]/diagnose/page.tsx` that manages symptom submission and diagnosis display
- **DiagnosisResponse**: The type returned by `POST /api/v1/diagnose/symptoms` — includes `sessionId`, `diagnoses`, `confidenceScore`, `llmUsed`, `sources`, `warningsPresent`, `fallbackWarning`, `degradedWarning`, `parseFailed`, `agentContributions`, `evidenceCitations`
- **DiagnoseSession**: The type returned by `GET /api/v1/diagnose/session/{session_id}` — includes `id`, `symptoms`, `diagnoses`, `prescription`, `alerts`, `createdAt`. Does NOT include `confidenceScore`, `sources`, `evidenceCitations`, `agentContributions`, `llmUsed`, or warning fields
- **sessionStorage**: Browser storage scoped to the tab lifetime, used to persist the last diagnose session ID across in-tab navigations

## Bug Details

### Bug Condition

Two distinct bug conditions exist:

**Bug 1 — Chat Data Loss on "New Chat"**

The bug manifests when the user clicks "New Chat" while the current session contains messages. The `handleNewSession` function synchronously clears messages and the localStorage session ID without checking whether the backend has persisted the session. If the stream just completed, the data exists server-side but the local reference is destroyed. If a stream is still in progress, the abort fires but the user turn may not yet be persisted.

**Formal Specification:**
```
FUNCTION isBugCondition_ChatDataLoss(input)
  INPUT: input of type NewChatAction { sessionId: string, messages: ChatMessage[], streamInProgress: boolean }
  OUTPUT: boolean

  RETURN input.messages.length > 0
END FUNCTION
```

**Bug 2 — Diagnostic Data Loss on Navigation**

The bug manifests when the user navigates away from the diagnose page after receiving diagnostic results. Results are stored only in React component state (`useState<DiagnosisResponse | null>(null)`) with no persistence mechanism. On unmount, all results are lost.

**Formal Specification:**
```
FUNCTION isBugCondition_DiagnoseDataLoss(input)
  INPUT: input of type DiagnoseNavigation { results: DiagnosisResponse | null, sessionId: string | null, navigatesAway: boolean }
  OUTPUT: boolean

  RETURN input.results IS NOT null
         AND input.sessionId IS NOT null
         AND input.navigatesAway = true
END FUNCTION
```

### Examples

- User sends 5 messages in session "session-abc", clicks "New Chat" → messages vanish from UI, session ID removed from localStorage. The conversation is unreachable even though it exists in MongoDB.
- User sends a message, stream completes with "done" event, user immediately clicks "New Chat" → backend has persisted the session, but the user sees an empty chat with no way back.
- User clicks "New Chat" during an active stream → `AbortController.abort()` fires, backend may not have persisted yet. The fix skips verification in this case and clears immediately (accepting potential data loss for the in-progress response).
- User submits symptoms on diagnose page, receives 3 diagnoses with session ID "diag-xyz", navigates to chat page, navigates back → results area is empty, user must re-submit symptoms.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Clicking "New Chat" when the current session has zero messages must continue to generate a new session ID and reset state without any backend call
- SSE streaming, token appending, and "done" event finalization must work identically
- Symptom submission via `POST /api/v1/diagnose/symptoms` and result display must work identically
- Session restore from localStorage on chat page load via `GET /api/v1/chat/history/{session_id}` must work identically
- `AbortController.abort()` on unmount or "New Chat" must continue to cancel in-progress streams (the abort itself is unchanged; only the post-abort flow changes)
- The assistant's streamed response with sources must continue to display correctly after the "done" event

**Scope:**
All inputs that do NOT involve (1) clicking "New Chat" with existing messages or (2) navigating away from the diagnose page with results should be completely unaffected by this fix.

## Hypothesized Root Cause

Based on the bug description and code analysis, the root causes are:

1. **Synchronous state clearing without backend verification (Chat)**: `handleNewSession()` in `chat/page.tsx` calls `clearStoredSessionId()`, `setMessages([])`, and generates a new session ID in a single synchronous block. There is no `await` on any backend call to verify the session was persisted. The backend persists messages only after the SSE stream's `done` event (in `ChatService.send_message_stream`), so there is a window where the session exists server-side but the frontend has already discarded its reference.

2. **No persistence layer for diagnostic results (Diagnose)**: `DiagnosePage` in `diagnose/page.tsx` stores results in `useState<DiagnosisResponse | null>(null)`. The `DiagnosisResponse` includes a `sessionId` field that could be used to re-fetch results from `GET /api/v1/diagnose/session/{session_id}`, but this is never stored anywhere persistent. When the component unmounts on navigation, the state is garbage-collected.

3. **Missing sessionStorage bridge**: The diagnose page receives a `sessionId` in the API response but never writes it to `sessionStorage` or any other persistence mechanism. On remount, there is no stored ID to use for re-fetching.

## Correctness Properties

Property 1: Bug Condition — Chat session verified before clearing (non-streaming)

_For any_ "New Chat" action where the current session has messages and no stream is in progress, the fixed `handleNewSession` function SHALL verify the session exists on the backend via `GET /api/v1/chat/history/{session_id}` (with a 3-second timeout) before clearing local state. If the backend confirms the session exists, local state SHALL be cleared and a new session started. If the backend call fails (network error, 404, or timeout), an error notification SHALL be displayed and local state SHALL NOT be cleared.

**Validates: Requirements 2.1, 2.3, 2.4, 2.5**

Property 1b: Bug Condition — Active stream abort and clear

_For any_ "New Chat" action where the current session has messages and a stream IS in progress, the fixed `handleNewSession` function SHALL abort the stream and clear local state immediately without backend verification (since the backend may not have persisted the in-progress response yet).

**Validates: Requirement 2.2**

Property 2: Bug Condition — Diagnostic results survive navigation (partial restore)

_For any_ navigation away from the diagnose page where results exist, the fixed diagnose page SHALL persist the session ID to `sessionStorage` (namespaced by user ID) so that on remount, partial results can be restored from the backend via `GET /api/v1/diagnose/session/{session_id}`. Restored results will include `diagnoses`, `prescription`, and `alerts` but NOT `confidenceScore`, `sources`, `evidenceCitations`, `agentContributions`, `llmUsed`, or warning fields.

**Validates: Requirements 2.6, 2.7**

Property 3: Preservation — Empty session "New Chat" unchanged

_For any_ "New Chat" action where the current session has zero messages, the fixed `handleNewSession` function SHALL produce the same result as the original function — generating a new session ID and resetting state without any backend interaction.

**Validates: Requirement 3.1**

Property 4: Preservation — Chat streaming behavior unchanged

_For any_ chat message send action, the fixed code SHALL produce exactly the same SSE streaming behavior, token appending, "done" event finalization, error handling, and retry flow as the original code.

**Validates: Requirements 3.2, 3.4, 3.5, 3.6**

Property 5: Preservation — Diagnose submission behavior unchanged

_For any_ symptom submission on the diagnose page, the fixed code SHALL call the same `POST /api/v1/diagnose/symptoms` endpoint and display results in the same manner as the original code.

**Validates: Requirement 3.3**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `apps/web/src/app/[locale]/chat/page.tsx`

**Function**: `handleNewSession`

**Specific Changes**:
1. **Make handleNewSession async**: Convert from synchronous to async function so it can `await` the backend verification call.

2. **Add a `verifying` state**: Add `const [verifying, setVerifying] = useState(false)` to track when the verification call is in flight. Disable the "New Chat" button and show a brief loading indicator while `verifying` is true.

3. **Branch on stream-in-progress**: Check the `streaming` state variable:
   - If `streaming === true`: Abort the stream via `abortControllerRef.current?.abort()`, then clear state immediately (same as current behavior). Skip backend verification because the backend may not have persisted the in-progress response yet.
   - If `streaming === false` and `messages.length > 0`: Proceed with backend verification (step 4).
   - If `messages.length === 0`: Proceed directly with current synchronous behavior — no backend call needed.

4. **Add backend verification with timeout**: Call `apiClient.chat.getHistory(sessionId)` wrapped in a 3-second timeout (using `AbortController` with `setTimeout`). If the call succeeds and returns a session with messages, proceed with clearing. If it fails (network error, 404, or timeout), set an error state to display a notification and do NOT clear messages.

5. **Error notification**: Use the existing `setError()` state to display the error in the existing error banner area. Use a new i18n key like `chat.newSessionVerifyFailed`.

---

**File**: `apps/web/src/app/[locale]/diagnose/page.tsx`

**Function**: Component body (state management and effects)

**Specific Changes**:
1. **Define sessionStorage key with user namespace**: Use `'diagno-pilot-diagnose-session-' + user?.id` as the key. If no user is available (shouldn't happen on this page), fall back to a generic key.

2. **Store session ID in sessionStorage on successful diagnosis**: After `setResults(response)` in `handleSubmit`, also write `response.sessionId` to sessionStorage under the namespaced key.

3. **Add useEffect to restore partial results on mount**: On component mount, check sessionStorage for a stored session ID. If found, call `apiClient.diagnose.getSession(sessionId)` to fetch the `DiagnoseSession`. Map the `DiagnoseSession` fields to the subset of `DiagnosisResponse` that can be restored:
   - `diagnoses` → map each `DifferentialDiagnosis` to the page's expected format
   - `prescription` → available if present
   - `alerts` → available
   - `confidenceScore`, `sources`, `evidenceCitations`, `agentContributions`, `llmUsed`, `warningsPresent`, `fallbackWarning`, `degradedWarning`, `parseFailed` → set to `null`/`undefined`/`false`/empty as appropriate
   - Display a subtle notice (e.g., "Some details unavailable — showing restored results") using i18n key `diagnose.restoredPartial`

4. **Clear sessionStorage on new submission**: When the user submits new symptoms, clear the old session ID from sessionStorage before making the API call (it will be replaced by the new one on success).

5. **Handle fetch errors gracefully**: If the `getSession` call fails on mount (session expired, network error), silently clear the stored session ID and show the empty form — do not block the user.

### Type Mapping: DiagnoseSession → DiagnosisResponse (partial)

```typescript
function mapSessionToPartialResponse(session: DiagnoseSession): DiagnosisResponse {
  return {
    sessionId: session.id,
    diagnoses: session.diagnoses, // DifferentialDiagnosis[] — same shape
    // Fields NOT available from DiagnoseSession:
    confidenceScore: undefined,
    llmUsed: undefined,
    sources: [],
    warningsPresent: false,
    fallbackWarning: undefined,
    degradedWarning: undefined,
    parseFailed: false,
    agentContributions: [],
    evidenceCitations: [],
  };
}
```

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write component tests using Vitest + React Testing Library that simulate the bug conditions. Run these tests on the UNFIXED code to observe failures and understand the root cause.

**Test Cases**:
1. **Chat: New Chat with messages**: Render ChatPage with mocked messages, click "New Chat", assert that `getHistory` was NOT called — will PASS on unfixed code, confirming the bug (no verification happens)
2. **Chat: New Chat during stream**: Render ChatPage, start a stream, click "New Chat" before "done" event, assert messages are cleared without verification — will PASS on unfixed code
3. **Diagnose: Navigate away with results**: Render DiagnosePage, submit symptoms, unmount component, remount, assert results are NOT restored — will PASS on unfixed code, confirming no persistence
4. **Diagnose: Session ID not stored**: After successful diagnosis, check sessionStorage for session ID — will be absent on unfixed code, confirming the bug

**Expected Counterexamples**:
- `handleNewSession` clears state synchronously without any async backend call
- DiagnosePage never writes to sessionStorage
- Possible causes: missing async verification in handleNewSession, missing sessionStorage write in handleSubmit

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**
```
// Non-streaming case
FOR ALL input WHERE isBugCondition_ChatDataLoss(input) AND NOT input.streamInProgress DO
  result := handleNewSession_fixed(input)
  backendSession := GET /api/v1/chat/history/{input.sessionId} (timeout 3s)
  IF backendSession EXISTS THEN
    ASSERT result.localMessages = []
    ASSERT result.sessionId ≠ input.sessionId
  ELSE
    ASSERT result.errorDisplayed = true
    ASSERT result.localMessages = input.messages
  END IF
END FOR

// Active stream case
FOR ALL input WHERE isBugCondition_ChatDataLoss(input) AND input.streamInProgress DO
  result := handleNewSession_fixed(input)
  ASSERT result.streamAborted = true
  ASSERT result.localMessages = []
  ASSERT result.sessionId ≠ input.sessionId
END FOR

// Diagnose navigation case
FOR ALL input WHERE isBugCondition_DiagnoseDataLoss(input) DO
  navigateAway()
  navigateBack()
  restoredResults := fetchFromBackend(input.sessionId)
  ASSERT restoredResults IS NOT null
  ASSERT restoredResults.diagnoses.length = input.results.diagnoses.length
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition_ChatDataLoss(input) DO
  ASSERT handleNewSession_original(input) = handleNewSession_fixed(input)
END FOR

FOR ALL input WHERE NOT isBugCondition_DiagnoseDataLoss(input) DO
  ASSERT diagnosePage_original(input) = diagnosePage_fixed(input)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many test cases automatically across the input domain
- It catches edge cases that manual unit tests might miss
- It provides strong guarantees that behavior is unchanged for all non-buggy inputs

**Test Plan**: Observe behavior on UNFIXED code first for non-bug inputs (empty session "New Chat", message sending, symptom submission), then write property-based tests capturing that behavior.

**Test Cases**:
1. **Empty Session New Chat Preservation**: Verify that clicking "New Chat" with zero messages generates a new session ID and resets state without any backend call — same behavior before and after fix
2. **SSE Streaming Preservation**: Verify that sending a message produces the same streaming behavior, token appending, and "done" finalization before and after fix
3. **Diagnose Submission Preservation**: Verify that submitting symptoms calls the same endpoint and displays results identically before and after fix
4. **Session Restore Preservation**: Verify that loading the chat page with a stored session ID fetches and displays history identically before and after fix

### Unit Tests

- Test `handleNewSession` with messages present (no stream): verify `getHistory` is called, state cleared on success, error shown on failure
- Test `handleNewSession` with messages present (stream active): verify stream aborted, state cleared immediately, no `getHistory` call
- Test `handleNewSession` with zero messages: verify no backend call, state reset immediately
- Test `handleNewSession` when `getHistory` returns 404: verify error displayed, messages preserved
- Test `handleNewSession` when `getHistory` throws network error: verify error displayed, messages preserved
- Test `handleNewSession` when `getHistory` times out (>3s): verify error displayed, messages preserved
- Test "New Chat" button is disabled while `verifying` is true
- Test diagnose page stores session ID in sessionStorage (namespaced by user ID) after successful submission
- Test diagnose page restores partial results from backend on mount when sessionStorage has a session ID
- Test diagnose page shows "restored partial" notice when displaying restored results
- Test diagnose page handles getSession failure gracefully (clears sessionStorage, shows empty form)
- Test diagnose page clears old sessionStorage on new submission
- Test diagnose page sessionStorage key includes user ID

### Property-Based Tests

- Generate random message arrays (0 to N messages) and verify `handleNewSession` only calls backend when messages.length > 0 and streaming === false (preservation boundary)
- Generate random DiagnosisResponse objects with varying numbers of diagnoses and verify round-trip through sessionStorage + getSession restores equivalent diagnoses data
- Generate random sequences of submit/navigate-away/navigate-back actions and verify results are always recoverable when a session ID exists

### Integration Tests

- Full chat flow: send message → wait for "done" → click "New Chat" → verify backend has session → verify new empty session
- Full chat flow (stream active): send message → click "New Chat" before "done" → verify stream aborted → verify state cleared immediately
- Full diagnose flow: submit symptoms → receive results → navigate to chat → navigate back → verify partial results restored with notice
- Chat error flow: send message → click "New Chat" → mock getHistory to fail → verify error shown and messages preserved
- Chat timeout flow: send message → click "New Chat" → mock getHistory to hang → verify timeout after 3s → verify error shown
- Diagnose error flow: submit symptoms → navigate away → mock getSession to fail on return → verify empty form shown gracefully
