# Bugfix Requirements Document

## Introduction

When an assistant's streamed SSE response is interrupted before the `done` event is received (due to connection drop, network timeout, or abnormal stream termination), the chat page displays a truncated message with no visual indication that it is incomplete. Additionally, because source citations are only delivered in the `done` event payload, an interrupted stream always results in missing sources with no notice to the user. This bug causes users to mistake partial, potentially inaccurate responses for complete answers.

Note: The abort case (user clicks "New Chat" during streaming) is excluded from this spec. When the user aborts, the entire messages array is cleared immediately, so the partial message is never visible long enough for an indicator to matter. That flow is handled by the `new-chat-data-loss-fix` spec.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN the SSE stream ends abnormally (connection drop, network timeout) after tokens have been received but before a `done` event arrives THEN the system displays the partially-streamed assistant message as if it were a complete response with no visual indicator of interruption

1.2 WHEN the SSE stream is interrupted before the `done` event delivers source citations THEN the system displays no sources section and provides no indication that sources were expected but could not be delivered

### Expected Behavior (Correct)

2.1 WHEN the SSE stream ends abnormally after tokens have been received but before a `done` event arrives THEN the system SHALL append a visible interruption indicator to the end of the partial assistant message content, using the i18n translation key `chat.responseInterrupted` (e.g., "[Response interrupted]" in English, "[Réponse interrompue]" in French)

2.2 WHEN the SSE stream is interrupted before the `done` event delivers source citations and the assistant message contains content THEN the system SHALL display a "Sources unavailable" notice inline below the message content (in the same position where `SourcesPanel` would normally render), using the i18n translation key `chat.sourcesUnavailable`

2.3 THE i18n package (`packages/i18n`) SHALL include French and English translations for the `chat.responseInterrupted` and `chat.sourcesUnavailable` keys

### Unchanged Behavior (Regression Prevention)

3.1 WHEN the SSE stream completes normally with a `done` event THEN the system SHALL CONTINUE TO finalize the message with the full answer and display source citations as before, with no interruption indicator

3.2 WHEN the SSE stream receives an `error` event THEN the system SHALL CONTINUE TO remove the placeholder assistant message and display the error with retry capability as before

3.3 WHEN the SSE stream is aborted by the user and no tokens have been received (empty placeholder) THEN the system SHALL CONTINUE TO silently remove the empty placeholder message as before

3.4 WHEN the SSE stream is aborted by the user after tokens have been received (non-empty placeholder) THEN the system SHALL CONTINUE TO leave the partial message in state as-is — no interruption indicator is added because the user intentionally aborted (this case is excluded from the bug condition by `userAborted = false`)

3.5 WHEN a non-streaming error occurs (e.g., HTTP 401, network failure before stream starts) THEN the system SHALL CONTINUE TO handle the error with existing retry and redirect logic as before

---

### Bug Condition (Formal)

```pascal
FUNCTION isBugCondition(X)
  INPUT: X of type StreamOutcome
  OUTPUT: boolean

  // Returns true when the stream ends without a 'done' or 'error' event
  // while the assistant message already has content (tokens received)
  // Excludes user-initiated aborts (handled by new-chat-data-loss-fix spec)
  RETURN X.streamEndedWithoutDoneEvent = true
     AND X.streamEndedWithoutErrorEvent = true
     AND X.userAborted = false
     AND X.assistantMessageContent <> ""
END FUNCTION
```

### Property Specification (Fix Checking)

```pascal
// Property: Fix Checking — Interrupted stream indicator
FOR ALL X WHERE isBugCondition(X) DO
  message ← getDisplayedAssistantMessage(X)
  ASSERT message.content ENDS WITH translatedInterruptionIndicator(X.locale)
  ASSERT message.showsSourcesUnavailableNotice = true
END FOR
```

### Preservation Goal

```pascal
// Property: Preservation Checking — Normal streams unchanged
FOR ALL X WHERE NOT isBugCondition(X) DO
  ASSERT F(X) = F'(X)
END FOR
```

This ensures that for all non-buggy inputs (normal `done` events, `error` events, empty-placeholder aborts, non-empty-placeholder aborts, pre-stream failures), the fixed code behaves identically to the original.
