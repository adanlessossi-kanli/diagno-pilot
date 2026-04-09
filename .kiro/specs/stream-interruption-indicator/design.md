# Stream Interruption Indicator — Bugfix Design

## Overview

When the SSE stream from the backend ends abnormally (connection drop, network timeout, server crash) after tokens have been received but before a `done` event arrives, the `for await` loop in `ChatPage.handleSend` exits silently. The partial assistant message remains in state with no visual indicator that it is incomplete, and no sources are shown because sources are only delivered in the `done` event payload. This fix detects the silent-exit condition in `handleSend` and appends an i18n-translated interruption indicator to the message content, plus sets an `interrupted` flag so the UI can render a "Sources unavailable" notice.

## Glossary

- **Bug_Condition (C)**: The SSE stream ends without emitting a `done` or `error` event, the user did not abort, and the assistant message has content (tokens were received)
- **Property (P)**: The partial assistant message displays a visible interruption indicator appended to its content, and a "Sources unavailable" notice appears where sources would normally render
- **Preservation**: Normal `done` events, `error` events, user-initiated aborts, and pre-stream failures must all continue to behave identically to the current code
- **`handleSend`**: The async function in `apps/web/src/app/[locale]/chat/page.tsx` that sends a chat message, consumes the SSE stream via `for await`, and updates React state for each event
- **`parseSSEStream`**: The async generator in `packages/api-client/index.ts` that reads a `ReadableStream<Uint8Array>` and yields `StreamEvent` objects; it returns silently when the underlying stream ends
- **`StreamEvent`**: The discriminated union type (`token | done | error`) yielded by `parseSSEStream`

## Bug Details

### Bug Condition

The bug manifests when the SSE stream's underlying `ReadableStream` signals `done: true` (connection closed) before `parseSSEStream` has yielded a `done` or `error` event. In this case, the `for await` loop in `handleSend` exits normally, the `finally` block sets `streaming = false` and `loading = false`, and the partial assistant message is left in state as-is — with no interruption indicator and no sources.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type StreamOutcome
  OUTPUT: boolean

  RETURN input.streamEndedWithoutDoneEvent = true
     AND input.streamEndedWithoutErrorEvent = true
     AND input.userAborted = false
     AND input.assistantMessageContent <> ""
END FUNCTION
```

### Examples

- **Connection drop mid-stream**: User asks "What is the treatment for malaria?", receives tokens "The recommended treatment is", then the server drops the connection. The message displays "The recommended treatment is" with no indicator that it is incomplete. Expected: message displays "The recommended treatment is\n\n[Response interrupted]" and a "Sources unavailable" notice appears below.
- **Network timeout**: User asks a question, receives 3 tokens, then the network times out. The partial message appears complete. Expected: interruption indicator appended, sources unavailable notice shown.
- **Server crash**: Backend process crashes after emitting several tokens. The stream closes. The partial message appears complete. Expected: interruption indicator appended, sources unavailable notice shown.
- **Edge case — stream ends after tokens but before any content is meaningful**: User receives a single space character " " as the only token. The message has content (non-empty string). Expected: interruption indicator is still appended because `content !== ""`.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- When the SSE stream completes normally with a `done` event, the message is finalized with the full answer and sources are displayed — no interruption indicator is shown. Note: the `done` event replaces `content` entirely with `event.answer` (not appending to the token-concatenated content), so the finalized content is always the backend's authoritative answer.
- When the SSE stream receives an `error` event, the placeholder assistant message is removed and the error is displayed with retry capability
- When the user aborts (clicks "New Chat") and the placeholder is still empty, the empty message is silently removed (the `catch` block filters out messages where `m.content === ''`)
- When the user aborts after tokens have been received, the partial message remains in state as-is — no interruption indicator is added because the abort throws `AbortError` which is caught in the `catch` block, bypassing the post-loop interruption detection entirely. This is correct: user-initiated aborts are excluded from the bug condition.
- When a pre-stream error occurs (HTTP 401, network failure before stream starts), the existing error handling with redirect/retry logic continues to work
- The `ThinkingBubble` display logic remains unchanged
- The streaming cursor behavior remains unchanged

**Scope:**
All inputs that do NOT involve an abnormal stream termination (stream ending without `done`/`error` while content exists and user didn't abort) should be completely unaffected by this fix. This includes:
- Normal `done` event completions
- `error` event handling
- User-initiated aborts via "New Chat" (both empty and non-empty placeholders)
- HTTP errors before streaming starts (401, 500, network failures)
- Empty placeholder cleanup on abort

## Hypothesized Root Cause

Based on the code analysis, the root cause is clear:

1. **No post-loop completion check in `handleSend`**: The `for await (const event of stream)` loop in `handleSend` handles `token`, `done`, and `error` events inside the loop body. When the stream ends without emitting `done` or `error` (i.e., `parseSSEStream` returns because the underlying `ReadableStream` signals `done: true`), the loop exits normally and falls through to the `finally` block. There is no code after the loop to detect that the stream ended without a terminal event.

2. **`parseSSEStream` returns silently on stream end**: In `packages/api-client/index.ts`, when `reader.read()` returns `{ done: true }`, the generator breaks out of the loop and returns. It does not yield any special "stream ended" event. This is correct behavior for the parser — the detection should happen at the consumer level.

3. **No `interrupted` flag on `ChatMessage`**: The `ChatMessage` type has no field to track whether a message was interrupted, so the `MessageBubble` component has no way to render a "Sources unavailable" notice even if the interruption were detected.

## Correctness Properties

Property 1: Bug Condition — Interrupted Stream Shows Indicator

_For any_ stream outcome where the bug condition holds (stream ends without `done`/`error` event, user didn't abort, assistant message has content), the fixed `handleSend` function SHALL append the translated interruption indicator (`chat.responseInterrupted`) to the assistant message content and set the message's `interrupted` flag to `true`, causing the UI to display a "Sources unavailable" notice.

**Validates: Requirements 2.1, 2.2**

Property 2: Preservation — Normal Completion Unchanged

_For any_ stream outcome where the bug condition does NOT hold (normal `done` event, `error` event, user abort, pre-stream failure), the fixed code SHALL produce exactly the same message state and UI behavior as the original code, preserving all existing functionality including source display, error handling, retry capability, and placeholder cleanup.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `apps/web/src/app/[locale]/chat/page.tsx`

**Function**: `handleSend`

**Specific Changes**:

1. **Add a `receivedDone` tracking variable**: Before the `for await` loop, initialize a `let receivedDone = false` flag. Set it to `true` inside the `done` event handler. Also set it to `true` inside the `error` event handler — this is necessary because when an `error` event fires, the placeholder message is removed from state entirely (`prev.filter(m => m.id !== assistantMsgId)`), so even if the post-loop check runs, there would be no message to append to. Setting the flag prevents a no-op state update on a removed message.

2. **Add post-loop interruption detection**: After the `for await` loop exits (but still inside the `try` block, before the `catch`), check: if `receivedDone` is `false`, the stream ended abnormally. Additionally verify the assistant message still exists in state and has non-empty content (to avoid acting on a message that was already removed by an error event). In that case, update the assistant message in state by appending `\n\n${t('responseInterrupted')}` to its content and setting `interrupted: true` on the message object. Note: this code must be placed after the `for await` loop but before the `catch` block — if the stream throws an exception (e.g., `AbortError`), the loop exits via the `catch` path and the post-loop code is never reached, which is the correct behavior.

3. **Extend `ChatMessage` usage with `interrupted` flag**: Define a local extended type (e.g., `type LocalChatMessage = ChatMessage & { interrupted?: boolean }`) and use it for the component's `messages` state. This does NOT require changing the shared `ChatMessageSchema` in `packages/types` — the Zod schema defines the wire format and should not include UI-only flags. All `useState<ChatMessage[]>` references in `ChatPage` become `useState<LocalChatMessage[]>`.

4. **Update `MessageBubble` to show "Sources unavailable"**: In `MessageBubble`, after the existing `SourcesPanel` conditional (`!isUser && message.sources && message.sources.length > 0`), add a new conditional: when `message.interrupted === true && (!message.sources || message.sources.length === 0)`, render a "Sources unavailable" notice using `t('sourcesUnavailable')`. This renders in the same DOM position where `SourcesPanel` would normally appear, styled as a subtle informational notice (e.g., `text-xs text-gray-500 italic`).

5. **Add i18n keys**: Add `chat.responseInterrupted` and `chat.sourcesUnavailable` to both `packages/i18n/locales/en.json` and `packages/i18n/locales/fr.json`.

**File**: `packages/i18n/locales/en.json`

**Changes**:
- Add `"responseInterrupted": "[Response interrupted]"` to the `chat` section
- Add `"sourcesUnavailable": "Sources unavailable — response was interrupted before sources could be delivered."` to the `chat` section

**File**: `packages/i18n/locales/fr.json`

**Changes**:
- Add `"responseInterrupted": "[Réponse interrompue]"` to the `chat` section
- Add `"sourcesUnavailable": "Sources indisponibles — la réponse a été interrompue avant que les sources puissent être transmises."` to the `chat` section

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write tests that simulate an SSE stream ending after tokens but before a `done` event. Use a mock async generator that yields tokens then returns without yielding `done`. Run these tests on the UNFIXED code to observe that the partial message has no interruption indicator.

**Test Cases**:
1. **Stream drops after tokens**: Mock stream yields `[token("Hello"), token(" world")]` then returns. Assert the displayed message does NOT end with the interruption indicator (will pass on unfixed code, confirming the bug exists).
2. **Stream drops after single token**: Mock stream yields `[token("Partial")]` then returns. Assert no interruption indicator (confirms bug).
3. **Stream drops with sources expected**: Mock stream yields tokens then returns without `done`. Assert no "Sources unavailable" notice (confirms bug).

**Expected Counterexamples**:
- The assistant message content equals exactly the concatenated tokens with no appended indicator
- No "Sources unavailable" notice is rendered
- The message appears identical to a completed message (indistinguishable from normal completion)

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  result := handleSend_fixed(input)
  message := getDisplayedAssistantMessage(result)
  ASSERT message.content ENDS WITH translatedInterruptionIndicator(locale)
  ASSERT message.interrupted = true
  ASSERT sourcesUnavailableNoticeIsDisplayed(message)
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT handleSend_original(input) = handleSend_fixed(input)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many test cases automatically across the input domain (varying numbers of tokens, different source configurations, different error messages)
- It catches edge cases that manual unit tests might miss (e.g., empty token content, very long streams)
- It provides strong guarantees that behavior is unchanged for all non-buggy inputs

**Test Plan**: Observe behavior on UNFIXED code first for normal `done` events, `error` events, and abort scenarios, then write property-based tests capturing that behavior.

**Test Cases**:
1. **Normal done preservation**: Generate random token sequences followed by a `done` event with random sources. Verify the message is finalized with the `done` answer and sources, with no interruption indicator.
2. **Error event preservation**: Generate random error messages with random `retryable` flags. Verify the placeholder is removed and the error is displayed with retry capability when retryable.
3. **Abort preservation**: Simulate user abort during streaming. Verify empty placeholders are cleaned up silently.
4. **Pre-stream failure preservation**: Simulate HTTP 401 and 500 errors before streaming starts. Verify redirect and retry behavior.

### Unit Tests

- Test that `handleSend` appends interruption indicator when stream ends without `done`/`error`
- Test that `MessageBubble` renders "Sources unavailable" when `interrupted` is `true`
- Test that `MessageBubble` does NOT render "Sources unavailable" when `interrupted` is `false` or absent
- Test that the interruption indicator uses the correct i18n key
- Test edge case: stream yields zero tokens then ends (empty placeholder should be cleaned up, not marked interrupted)

### Property-Based Tests

- Generate random token sequences (1–50 tokens of random content) and simulate stream interruption; verify the final message always ends with the interruption indicator and has `interrupted: true`
- Generate random complete stream sequences (tokens + done with random sources); verify no interruption indicator is present and sources are displayed correctly
- Generate random error events; verify placeholder removal and error display are unchanged

### Integration Tests

- Test full chat flow: send message → receive tokens → stream drops → verify interruption indicator visible and "Sources unavailable" notice rendered
- Test full chat flow: send message → receive tokens → `done` event → verify no interruption indicator and sources panel works
- Test that after an interrupted message, the user can send a new message and receive a normal response
