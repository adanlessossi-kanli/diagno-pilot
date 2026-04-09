# Implementation Plan

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** — Silent Stream Interruption Shows No Indicator
  - **CRITICAL**: This test MUST FAIL on unfixed code — failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior — it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the bug exists
  - **Scoped PBT Approach**: Scope the property to the concrete failing case — mock `parseSSEStream` to yield 1–N token events then return without yielding `done` or `error`, with `AbortSignal` not aborted
  - Create test file `apps/web/src/__tests__/stream-interruption.bug.test.tsx`
  - Mock `apiClient.chat.sendMessageStream` to return an async generator that yields `{ type: 'token', content: tokenContent }` for each generated token string, then returns (no `done`, no `error`)
  - Mock `useTranslations` to return a `t` function where `t('responseInterrupted')` returns `"[Response interrupted]"` and `t('sourcesUnavailable')` returns `"Sources unavailable — response was interrupted before sources could be delivered."`
  - Use `fast-check` to generate `fc.array(fc.string({ minLength: 1 }), { minLength: 1, maxLength: 20 })` as the token sequence
  - Property assertion: after `handleSend` completes, the final assistant message content ENDS WITH `"\n\n[Response interrupted]"` (from `isBugCondition` → `expectedBehavior` in design)
  - Property assertion: the final assistant message has `interrupted === true`
  - Run test on UNFIXED code
  - **EXPECTED OUTCOME**: Test FAILS (the assistant message content equals the concatenated tokens with no interruption indicator, and `interrupted` is `undefined`)
  - Document counterexamples found (e.g., tokens `["Hello", " world"]` → message content is `"Hello world"` with no indicator appended)
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 1.2, 2.1_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** — Normal Stream Completions Unchanged
  - **IMPORTANT**: Follow observation-first methodology
  - Create test file `apps/web/src/__tests__/stream-interruption.preservation.test.tsx` (or add to the same test file as task 1)
  - **Observe on UNFIXED code first:**
    - Observe: mock stream yields `[token("Hello"), token(" world"), done({ answer: "Hello world", sources: [...] })]` → message content is `"Hello world"` with sources displayed, no interruption indicator
    - Observe: mock stream yields `[token("Partial"), error({ error: "Server error", retryable: true })]` → placeholder assistant message is removed, `streamError` is set, `failedMessage` is set for retry
    - Observe: mock stream with `AbortSignal` aborted after tokens → `AbortError` caught, empty placeholder removed, non-empty partial message left as-is with no indicator
  - **Property 2a — Normal `done` event preservation**: Use `fast-check` to generate random token sequences (`fc.array(fc.string({ minLength: 1 }), { minLength: 1, maxLength: 20 })`) and a random final answer string and random sources array. Mock stream yields all tokens then `done({ answer, sources })`. Assert: final message content equals `answer` (not concatenated tokens), message has `sources` set, message does NOT end with interruption indicator, `interrupted` is falsy
  - **Property 2b — `error` event preservation**: Use `fast-check` to generate a random error message and random `retryable` boolean. Mock stream yields 0–5 tokens then `error({ error: msg, retryable })`. Assert: placeholder assistant message is removed from messages array, `streamError` is set with matching message and retryable flag
  - **Property 2c — User abort preservation (empty placeholder)**: Simulate `AbortError` thrown before any tokens. Assert: empty placeholder is removed from messages
  - **Property 2d — User abort preservation (non-empty placeholder)**: Simulate tokens received then `AbortError`. Assert: partial message remains in state as-is, no interruption indicator appended, `interrupted` is falsy
  - Run tests on UNFIXED code
  - **EXPECTED OUTCOME**: All preservation tests PASS (confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 3. Implement stream interruption detection and UI indicator

  - [x] 3.1 Add i18n keys for `chat.responseInterrupted` and `chat.sourcesUnavailable`
    - In `packages/i18n/locales/en.json`, add to the `chat` section: `"responseInterrupted": "[Response interrupted]"` and `"sourcesUnavailable": "Sources unavailable — response was interrupted before sources could be delivered."`
    - In `packages/i18n/locales/fr.json`, add to the `chat` section: `"responseInterrupted": "[Réponse interrompue]"` and `"sourcesUnavailable": "Sources indisponibles — la réponse a été interrompue avant que les sources puissent être transmises."`
    - _Requirements: 2.3_

  - [x] 3.2 Add `LocalChatMessage` type and `receivedDone` tracking in `handleSend`
    - In `apps/web/src/app/[locale]/chat/page.tsx`:
    - Define `type LocalChatMessage = ChatMessage & { interrupted?: boolean }` near the top of the file (after imports, in the Types section)
    - Change `useState<ChatMessage[]>` to `useState<LocalChatMessage[]>` for the `messages` state
    - In `handleSend`, add `let receivedDone = false;` before the `for await` loop
    - Set `receivedDone = true;` inside the `done` event handler (after `setMessages`)
    - Set `receivedDone = true;` inside the `error` event handler (after `setMessages` — prevents no-op state update on a removed message)
    - _Bug_Condition: isBugCondition(input) where input.streamEndedWithoutDoneEvent AND input.streamEndedWithoutErrorEvent AND !input.userAborted AND input.assistantMessageContent !== ""_
    - _Requirements: 2.1_

  - [x] 3.3 Add post-loop interruption detection after `for await`
    - After the `for await` loop exits (still inside the `try` block, before `catch`):
    - Check `if (!receivedDone)` — the stream ended without `done` or `error`
    - Update the assistant message in state: append `\n\n${t('responseInterrupted')}` to content and set `interrupted: true`
    - Only apply if the assistant message exists and has non-empty content (guard: `m.id === assistantMsgId && m.content !== ''`)
    - This code is unreachable on `AbortError` (caught by `catch`) — correct behavior per design
    - _Bug_Condition: isBugCondition(input) where stream ends without done/error, user didn't abort, content exists_
    - _Expected_Behavior: message.content ENDS WITH t('responseInterrupted') AND message.interrupted === true_
    - _Preservation: AbortError goes to catch block, done/error set receivedDone=true — post-loop code is skipped_
    - _Requirements: 2.1, 2.2_

  - [x] 3.4 Update `MessageBubble` to show "Sources unavailable" notice
    - In the `MessageBubble` component, update the `message` prop type to accept `LocalChatMessage`
    - After the existing `SourcesPanel` conditional (`!isUser && message.sources && message.sources.length > 0`), add a new conditional block:
    - When `!isUser && (message as LocalChatMessage).interrupted === true && (!message.sources || message.sources.length === 0)`, render: `<p className="text-xs text-gray-500 italic mt-1 px-1">{t('sourcesUnavailable')}</p>`
    - Add `useTranslations('chat')` to `MessageBubble` (or pass `t` as prop)
    - _Expected_Behavior: sourcesUnavailableNoticeIsDisplayed when interrupted && no sources_
    - _Preservation: Non-interrupted messages and messages with sources render exactly as before_
    - _Requirements: 2.2_

  - [x] 3.5 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** — Interrupted Stream Shows Indicator
    - **IMPORTANT**: Re-run the SAME test from task 1 — do NOT write a new test
    - The test from task 1 encodes the expected behavior
    - When this test passes, it confirms the expected behavior is satisfied
    - Run bug condition exploration test from step 1: `npx vitest --run apps/web/src/__tests__/stream-interruption.bug.test.tsx`
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed — interrupted streams now show indicator)
    - _Requirements: 2.1, 2.2_

  - [x] 3.6 Verify preservation tests still pass
    - **Property 2: Preservation** — Normal Stream Completions Unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 2 — do NOT write new tests
    - Run preservation property tests from step 2: `npx vitest --run apps/web/src/__tests__/stream-interruption.preservation.test.tsx`
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions — normal done, error, abort flows unchanged)
    - Confirm all preservation tests still pass after fix

- [x] 4. Checkpoint — Ensure all tests pass
  - Run full test suite: `npx vitest --run` from `apps/web`
  - Ensure all existing tests still pass (no regressions)
  - Ensure both bug condition and preservation tests pass
  - Ask the user if questions arise
