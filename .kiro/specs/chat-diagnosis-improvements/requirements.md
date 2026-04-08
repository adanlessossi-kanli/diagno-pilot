# Requirements Document: Chat & Diagnosis Workflow Improvements

## Introduction

This feature addresses critical bugs, security vulnerabilities, and missing functionality across the Chat and Diagnosis workflows in Diagno-Pilot. The improvements span conversation history handling, authorization enforcement, session management, input validation, data integrity, error resilience, and frontend state management. These fixes are essential for PHI protection, clinical reliability, and production readiness.

## Glossary

- **Chat_Service**: The backend service (`ChatService`) managing multi-turn chat sessions, message persistence, and RAG query orchestration.
- **LlamaIndex_Pipeline**: The RAG pipeline (`LlamaIndexPipeline`) that retrieves document chunks and generates grounded LLM answers.
- **Chat_Router**: The FastAPI router (`chat.py`) exposing `/api/v1/chat/*` HTTP endpoints.
- **Diagnostic_Service**: The orchestrator (`DiagnosticOrchestrator`) coordinating differential diagnosis via RAG, AgentPipeline, or MCP paths.
- **Diagnostic_Parser**: The stateless parser (`DiagnosticParser`) that transforms raw LLM JSON responses into `DifferentialDiagnosis` objects.
- **Synthesis_Agent**: The agent (`Synthesis_Agent`) that merges specialist agent results into a unified `DiagnosticResult`.
- **Agent_Pipeline**: The in-process multi-agent pipeline (`AgentPipeline`) executing specialist agents via LlamaIndex query engines.
- **MCP_Host**: The orchestrator (`MCP_Host`) running four specialist MCP servers in parallel via HTTP+SSE JSON-RPC 2.0.
- **Prescription_Service**: The service (`PrescriptionService`) calculating weight-based antibiotic prescriptions with renal/hepatic adjustments.
- **Diagnose_Router**: The FastAPI router (`diagnose.py`) exposing `/api/v1/diagnose/*` HTTP endpoints.
- **Chat_Frontend**: The web chat page (`apps/web/src/app/[locale]/chat/page.tsx`) providing the conversational UI.
- **Session**: A persistent conversation or diagnosis record identified by a unique `session_id`, stored in MongoDB.
- **PHI**: Protected Health Information as defined by HIPAA — patient-identifiable medical data.
- **Current_User**: The authenticated user extracted from the JWT token by the `require_role` dependency.

## Requirements

### Requirement 1: Pass Conversation History to LLM

**User Story:** As a clinician, I want the chat assistant to remember previous messages in my session, so that follow-up questions receive contextually relevant answers.

#### Acceptance Criteria

1. WHEN Chat_Service processes a message for an existing session, THE Chat_Service SHALL load the session's previous messages using the `_load_history` method and pass them as `session_history` to LlamaIndex_Pipeline.query().
2. THE LlamaIndex_Pipeline SHALL include the provided `session_history` messages in the LLM context before the current user question.
3. WHEN a new session has no prior messages, THE Chat_Service SHALL pass an empty list as `session_history` to LlamaIndex_Pipeline.query().
4. THE Chat_Service SHALL limit the loaded history to the most recent 20 messages to prevent context window overflow.

### Requirement 2: Enforce Session Ownership on Chat History

**User Story:** As a system administrator, I want chat history retrieval to verify session ownership, so that authenticated users cannot access another user's PHI.

#### Acceptance Criteria

1. WHEN a user requests chat history for a session, THE Chat_Router SHALL verify that the session's `user_id` matches the Current_User's ID before returning the session data.
2. IF the session's `user_id` does not match the Current_User's ID, THEN THE Chat_Router SHALL return HTTP 404 with detail "Chat session not found".
3. THE Chat_Service.get_history method SHALL accept a `user_id` parameter and include it in the MongoDB query filter alongside `session_id`.
4. WHEN the Current_User has the `admin` role, THE Chat_Router SHALL bypass the ownership check and allow access to any session.

### Requirement 3: Session Listing Endpoint

**User Story:** As a clinician, I want to list my previous chat sessions, so that I can resume conversations after navigating away or refreshing the page.

#### Acceptance Criteria

1. THE Chat_Router SHALL expose a GET `/api/v1/chat/sessions` endpoint that returns the Current_User's chat sessions.
2. THE endpoint SHALL return sessions sorted by `updated_at` in descending order.
3. THE endpoint SHALL support `skip` and `limit` query parameters for pagination, with `limit` defaulting to 20 and capped at 100.
4. WHEN the Current_User has no sessions, THE endpoint SHALL return an empty list with HTTP 200.
5. THE endpoint SHALL return each session's `session_id`, `created_at`, `updated_at`, and the content of the first user message as a preview.

### Requirement 4: Chat History Pagination

**User Story:** As a clinician, I want to paginate through long chat histories, so that the application remains responsive for sessions with many messages.

#### Acceptance Criteria

1. THE Chat_Router GET `/api/v1/chat/history/{session_id}` endpoint SHALL accept `skip` and `limit` query parameters for message pagination.
2. THE `limit` parameter SHALL default to 50 and be capped at 200.
3. THE response SHALL include a `total_messages` field indicating the total number of messages in the session.
4. THE Chat_Service SHALL use MongoDB `$slice` to return only the requested message window.

### Requirement 5: Context-Aware Cache Key

**User Story:** As a clinician, I want cached responses to account for conversation context, so that the same question in different conversation states returns the correct answer.

#### Acceptance Criteria

1. WHEN `session_history` is provided, THE LlamaIndex_Pipeline SHALL include a hash of all provided session_history messages (up to the 20-message limit from Requirement 1) in the cache key, so that the cache window matches the LLM context window.
2. WHEN `session_history` is empty or not provided, THE LlamaIndex_Pipeline SHALL use the existing cache key format without a history hash.
3. THE cache key SHALL remain deterministic: identical question, context, region, and session_history SHALL produce the same cache key.

### Requirement 6: Chat Message Input Validation

**User Story:** As a system operator, I want chat message length to be validated, so that excessively long inputs do not cause LLM timeouts or cost spikes.

#### Acceptance Criteria

1. THE ChatMessageRequest model SHALL enforce a maximum length of 4000 characters on the `message` field.
2. IF a message exceeds 4000 characters, THEN THE Chat_Router SHALL return HTTP 422 with a descriptive validation error.
3. THE ChatMessageRequest model SHALL enforce a minimum length of 1 character on the `message` field after trimming whitespace.

### Requirement 7: Chat Session TTL and Cleanup

**User Story:** As a system administrator, I want chat sessions to expire after a retention period, so that stale PHI data does not accumulate indefinitely.

#### Acceptance Criteria

1. THE application startup SHALL create a MongoDB TTL index on `chat_sessions.updated_at` with an expiry of 90 days.
2. THE Chat_Router SHALL expose a DELETE `/api/v1/chat/sessions/{session_id}` endpoint that allows the session owner to delete a session.
3. WHEN a user requests deletion of a session, THE Chat_Router SHALL verify that the session's `user_id` matches the Current_User's ID before deleting.
4. IF the session does not belong to the Current_User, THEN THE Chat_Router SHALL return HTTP 404.
5. WHEN the Current_User has the `admin` role, THE Chat_Router SHALL bypass the ownership check and allow deletion of any session.

### Requirement 8: Frontend Session Persistence

**User Story:** As a clinician, I want my chat session to persist across page navigations, so that I do not lose my conversation when switching between application sections.

#### Acceptance Criteria

1. WHEN a chat session is created, THE Chat_Frontend (web) SHALL store the `sessionId` in `localStorage` under the key `diagno-pilot-chat-session`.
2. WHEN the chat page loads, THE Chat_Frontend (web) SHALL restore the `sessionId` from `localStorage` if one exists.
3. WHEN the user clicks "New Session", THE Chat_Frontend (web) SHALL clear the stored `sessionId` from `localStorage` and generate a new one.
4. WHEN a stored `sessionId` is restored, THE Chat_Frontend (web) SHALL attempt to load the session's message history from the backend.
5. THE mobile frontend (`apps/mobile`) SHALL persist the current diagnosis session state (step, symptoms, diagnoses, prescription) using `AsyncStorage` so that navigating between tabs does not reset the workflow.

### Requirement 9: Optimistic Message Rollback Consistency

**User Story:** As a clinician, I want the chat UI to stay consistent with the backend state after a send failure, so that I do not see phantom messages or lose my input.

#### Acceptance Criteria

1. WHEN a message send fails with a network or server error, THE Chat_Frontend (web) SHALL remove the optimistic user message from the displayed messages.
2. WHEN a message send fails, THE Chat_Frontend (web) SHALL restore the original input text to the input field.
3. WHEN a message send fails with HTTP 500 or timeout, THE Chat_Frontend (web) SHALL display an error message with a "Retry" button that re-sends the same message content.
4. WHEN the user clicks "Retry", THE Chat_Frontend (web) SHALL re-add the optimistic user message and re-attempt the send.
5. THE mobile frontend (`apps/mobile`) diagnosis screen SHALL display a "Retry" option when the diagnosis or prescription API call fails, instead of only showing a generic error alert.


### Requirement 10: Filter Irrelevant Sources from Chat Responses

**User Story:** As a clinician, I want the chat assistant to only show sources that are relevant to my question, so that I am not distracted by unrelated document citations.

#### Acceptance Criteria

1. WHEN the LlamaIndex_Pipeline retrieves chunks, THE LlamaIndex_Pipeline SHALL filter out sources whose similarity score falls below a relevance threshold before including them in the response. This threshold (`SOURCE_RELEVANCE_THRESHOLD`) operates at the response level and SHALL be greater than or equal to the retrieval-level `LLAMAINDEX_SIMILARITY_THRESHOLD` to ensure only the most relevant retrieved chunks are surfaced to the user.
2. THE relevance threshold for source inclusion SHALL be configurable via `settings.SOURCE_RELEVANCE_THRESHOLD`, defaulting to 0.3.
3. WHEN no retrieved chunks meet the relevance threshold, THE LlamaIndex_Pipeline SHALL return an empty `sources` list in the RAGResponse (the LLM may still generate an answer from its own knowledge).
4. WHEN the LLM answer is generated purely from general medical knowledge (no grounded chunks used), THE LlamaIndex_Pipeline SHALL return an empty `sources` list.
5. THE Chat_Frontend SHALL hide the "Sources" panel entirely when the response contains zero sources.

### Requirement 11: Prevent Duplicate Consultation Writes on MCP Path

**User Story:** As a system administrator, I want each diagnosis to produce exactly one consultation document, so that the database does not contain duplicate records for the same diagnostic session.

#### Acceptance Criteria

1. WHEN the MCP path is used for diagnosis, THE Diagnostic_Service SHALL create the consultation document only once via `_create_mcp_consultation`.
2. THE Diagnose_Router SHALL skip its own `insert_one` call when the Diagnostic_Service returns a non-null `session_id` (indicating the MCP path already persisted the consultation).
3. THE DiagnosticResult SHALL include a `consultation_persisted` boolean flag that the Diagnose_Router checks before attempting its own write. THE flag SHALL default to `False` for non-MCP paths (RAG and AgentPipeline), ensuring backward-compatible behavior where the router performs the write.

### Requirement 12: Link Prescription to Diagnosis Session

**User Story:** As a clinician, I want prescriptions to be linked to the diagnosis session they were generated from, so that the full clinical workflow is traceable.

#### Acceptance Criteria

1. THE PrescriptionRequest model SHALL include an optional `session_id` field.
2. WHEN `session_id` is provided, THE Diagnose_Router SHALL update the corresponding consultation document's `prescription` field with the calculated prescription.
3. WHEN `session_id` is provided, THE Diagnose_Router SHALL also store the safety alerts in the consultation document's `alerts` field.
4. WHEN `session_id` is not provided, THE Diagnose_Router SHALL return the prescription without persisting it (current behavior preserved).

### Requirement 13: Enforce Ownership on Diagnosis Session Retrieval

**User Story:** As a system administrator, I want diagnosis session retrieval to verify ownership, so that authenticated users cannot access another user's consultation data.

#### Acceptance Criteria

1. WHEN a user requests a diagnosis session, THE Diagnose_Router SHALL include the Current_User's ID in the MongoDB query filter alongside `session_id`.
2. IF no consultation matches both `session_id` and the Current_User's ID, THEN THE Diagnose_Router SHALL return HTTP 404 with detail "Session not found".
3. WHEN the Current_User has the `admin` role, THE Diagnose_Router SHALL bypass the ownership check and allow access to any consultation.

### Requirement 14: Diagnostic Parser Failure Signaling

**User Story:** As a frontend developer, I want to distinguish between real diagnoses and parser-failure placeholders, so that the UI can display an appropriate warning to the clinician.

#### Acceptance Criteria

1. WHEN the Diagnostic_Parser cannot parse 3 or more valid diagnoses from the LLM response, THE Diagnostic_Parser SHALL set a `parse_failed` flag to true on the returned result.
2. THE DiagnosticResult SHALL include a `parse_failed` boolean field, defaulting to false.
3. WHEN `parse_failed` is true, THE Diagnose_Router SHALL include `parse_failed: true` in the response so the frontend can display a warning.
4. THE Diagnostic_Parser SHALL accept a `locale` parameter and return placeholder diagnoses with localized condition text: "Diagnostic indisponible" for French locales (fr-TG, fr-BJ, fr), "Diagnosis unavailable" for English locales (en).

### Requirement 15: Synthesis Agent Symptom Deduplication Fix

**User Story:** As a clinician, I want the merged diagnosis to include all matching symptoms from every contributing agent, so that no concordant symptom evidence is lost during synthesis.

#### Acceptance Criteria

1. WHEN the Synthesis_Agent merges two agents' results for the same condition, THE Synthesis_Agent SHALL union the `matching_symptoms` lists from both agents.
2. THE merged `matching_symptoms` list SHALL contain no duplicate symptom names (case-insensitive deduplication).
3. THE Synthesis_Agent SHALL retain the highest probability value when merging duplicate conditions.

### Requirement 16: Diagnosis Input Validation

**User Story:** As a system operator, I want symptom input to be validated, so that empty or excessively large symptom lists do not cause errors or resource exhaustion.

#### Acceptance Criteria

1. THE DiagnoseRequest model SHALL enforce a minimum of 1 symptom in the `symptoms` list.
2. THE DiagnoseRequest model SHALL enforce a maximum of 30 symptoms in the `symptoms` list.
3. THE Symptom model SHALL enforce a maximum length of 200 characters on the `name` field.
4. IF the symptom list is empty or exceeds 30 entries, THEN THE Diagnose_Router SHALL return HTTP 422 with a descriptive validation error.

### Requirement 17: Prescription Dose Floor for Clinical Relevance

**User Story:** As a clinician, I want the prescription calculator to enforce a minimum clinically meaningful dose, so that combined renal and hepatic adjustments do not produce sub-therapeutic doses.

#### Acceptance Criteria

1. WHEN both renal and hepatic adjustment factors are applied, THE Prescription_Service SHALL ensure the final dose is at least 10% of the unadjusted dose.
2. IF the adjusted dose falls below 10% of the unadjusted dose, THEN THE Prescription_Service SHALL clamp the dose to 10% of the unadjusted dose.
3. THE Prescription_Service SHALL log a warning when dose clamping is applied, including the antibiotic name and the original and clamped dose values.
4. THE AntibioticProtocol dataclass SHALL support an optional `min_dose_floor_pct` field (defaulting to 10) that allows individual protocols to override the default 10% floor when clinically justified.

### Requirement 18: Remove Redundant MCP Agent Timeout

**User Story:** As a developer, I want the MCP timeout logic to be simplified, so that the timeout is applied at a single layer and the effective timeout matches the configured value.

#### Acceptance Criteria

1. THE MCP_Host.run_diagnostic method SHALL apply the `AGENT_TIMEOUT` via `asyncio.wait_for` on each agent call.
2. THE MCP_Host._call_agent_http method SHALL NOT wrap its internal logic in a separate `asyncio.wait_for` or equivalent timeout.
3. THE effective timeout for each agent call SHALL be exactly `AGENT_TIMEOUT` seconds, applied once.

### Requirement 19: Complete Audit Data on MCP Path

**User Story:** As an auditor, I want diagnostic audit records to contain accurate confidence scores and agent results, so that audit trails are complete regardless of the diagnostic path used.

#### Acceptance Criteria

1. WHEN the MCP path produces a DiagnosticResult, THE Diagnostic_Service._write_audit method SHALL use the result's `confidence_score` instead of hardcoded 0.0.
2. WHEN the MCP path produces agent contributions, THE Diagnostic_Service._write_audit method SHALL populate `agent_results` from the result's `agent_contributions` instead of an empty list.
3. THE DiagnosticAudit document SHALL reflect the actual values from the diagnostic run for all paths (RAG, AgentPipeline, MCP).

### Requirement 20: Diagnosis Request Idempotency

**User Story:** As a clinician, I want accidental double-clicks or retries on the diagnose button to not create duplicate consultations, so that my consultation history remains clean.

#### Acceptance Criteria

1. THE DiagnoseRequest model SHALL accept an optional client-generated `idempotency_key` field.
2. WHEN an `idempotency_key` is provided, THE Diagnose_Router SHALL check if a consultation with the same `idempotency_key` already exists in MongoDB.
3. IF a consultation with the same `idempotency_key` exists, THEN THE Diagnose_Router SHALL return the existing consultation's response with HTTP 200 instead of creating a new one.
4. THE `idempotency_key` SHALL be stored as an indexed field on the consultation document.
5. WHEN `idempotency_key` is not provided, THE Diagnose_Router SHALL proceed with normal consultation creation (backward compatible).

### Requirement 21: Agent Pipeline Error Resilience

**User Story:** As a clinician, I want the diagnostic pipeline to return partial results when some agents fail, so that a single agent failure does not discard all other agents' results.

#### Acceptance Criteria

1. THE Agent_Pipeline.run method SHALL use `asyncio.gather` with `return_exceptions=True` so that individual agent exceptions do not cancel other agents.
2. WHEN an agent returns an exception instead of an AgentResult, THE Agent_Pipeline SHALL create an AgentResult with the `error` field set to the exception message.
3. THE Agent_Pipeline._aggregate method SHALL treat agents with errors the same as agents with empty chunks (excluded from active results, noted in degraded_warning).

### Requirement 22: Agent Sub-Question Improvements

**User Story:** As a clinician practicing in West Africa, I want the specialist diagnostic agents to use detailed, region-aware sub-questions grounded in tropical medicine, so that document retrieval is more targeted and the resulting diagnoses reflect the disease landscape of Togo, Benin, and the broader West African region.

#### Acceptance Criteria

1. ALL agent sub-question templates (AgentPipeline and MCP servers) SHALL frame their queries in the context of West African tropical and infectious diseases (malaria, typhoid, dengue, meningitis, schistosomiasis, etc.) rather than using generic medical language.
2. THE AgentPipeline sub-question templates SHALL include the patient profile (age group, weight, comorbidities, allergies) when available, in addition to symptoms and region.
3. THE symptomatology sub-question SHALL instruct the agent to consider symptom severity and duration when ranking differential diagnoses, prioritizing endemic tropical pathologies prevalent in the specified West African region.
4. THE epidemiology sub-question SHALL instruct the agent to consider endemic disease prevalence, seasonal patterns (rainy/dry season), and regional outbreak data specific to Togo (TG) or Benin (BJ), referencing CHU Lomé or CHU Abomey-Calavi guidelines as appropriate.
5. THE lab sub-question SHALL instruct the agent to recommend laboratory tests available in West African clinical settings (thick/thin blood smear, Widal test, rapid diagnostic tests) and prioritize tests that narrow the tropical differential diagnosis.
6. THE treatment sub-question SHALL instruct the agent to recommend treatment protocols aligned with West African national formularies and OMS AFRO guidelines, accounting for patient allergies, comorbidities, age group, and regional drug availability.
7. THE synthesis sub-question SHALL instruct the agent to reconcile conflicting diagnoses across agents, weight evidence by source quality, and prioritize conditions with high morbidity/mortality in the West African context.
8. ALL MCP specialist server tool handlers SHALL include patient profile data (age group, weight, allergies, comorbidities) in the sub-question text when the `patient_profile` argument is provided.
9. ALL MCP specialist server tool handlers SHALL include symptom severity and duration in the sub-question text, not just symptom names.

### Requirement 23: Prompt and System Prompt Improvements

**User Story:** As a clinician, I want the system prompts and prompt builder to produce well-structured, locale-aware, West African-contextualized instructions, so that the LLM generates accurate and properly formatted diagnostic output.

#### Acceptance Criteria

1. THE PromptBuilder SHALL write the instruction paragraph in the same language as the requested locale (French for fr-TG/fr-BJ/fr, English for en) instead of always using English.
2. THE PromptBuilder SHALL include `matching_symptoms` in the requested JSON output schema so the LLM returns concordant symptoms for each diagnosis.
3. THE DIAGNOSIS_SYSTEM_PROMPT SHALL explicitly instruct the LLM to return raw JSON without markdown code block wrappers.
4. THE DIAGNOSIS_SYSTEM_PROMPT SHALL reference the West African tropical medicine context and instruct the LLM to prioritize endemic pathologies when the region is TG or BJ.

### Requirement 24: Respond in the User's Language

**User Story:** As a clinician, I want the assistant to respond in the same language I use to ask my question, so that I can interact naturally in French or English without manually switching locale settings.

#### Acceptance Criteria

1. THE GROUNDING_SYSTEM_PROMPT (chat workflow) SHALL instruct the LLM to detect the language of the user's message and respond in that same language.
2. THE DIAGNOSIS_SYSTEM_PROMPT (diagnosis workflow) SHALL instruct the LLM to generate diagnosis output in the detected language of the user's input.
3. WHEN the LLM can confidently detect the user's message language, THE LLM SHALL respond in that language regardless of the `locale` header value. The user's message language always takes precedence.
4. WHEN language detection is ambiguous (e.g., single-word input, mixed-language text), THE LLM SHALL fall back to the language implied by the `locale` header (French for fr-TG/fr-BJ/fr, English for en).

### Requirement 25: Frontend Parse Failure Warning Display

**User Story:** As a clinician, I want to see a clear warning when the diagnostic system could not produce reliable diagnoses, so that I know to exercise additional clinical judgment.

#### Acceptance Criteria

1. WHEN the diagnosis API response contains `parse_failed: true`, THE Chat_Frontend (web) diagnosis results view SHALL display a prominent warning banner indicating that the diagnostic results may be incomplete or unreliable.
2. WHEN the diagnosis API response contains `parse_failed: true`, THE mobile frontend (`apps/mobile`) diagnosis results screen SHALL display a prominent warning banner with the same messaging.
3. THE warning message SHALL be localized: "Les résultats diagnostiques peuvent être incomplets ou peu fiables. Veuillez exercer votre jugement clinique." for French locales, "Diagnostic results may be incomplete or unreliable. Please exercise clinical judgment." for English locales.
4. WHEN `parse_failed` is false or absent, THE frontends SHALL NOT display the warning banner.

### Requirement 26: Backfill `updated_at` on Existing Chat Sessions

**User Story:** As a system administrator, I want all existing chat sessions to have an `updated_at` field, so that the TTL index (Requirement 7) can expire stale sessions and PHI data does not accumulate indefinitely.

#### Acceptance Criteria

1. THE application startup SHALL run a one-time migration that sets `updated_at` to the value of `created_at` (or the current timestamp if `created_at` is also missing) for all `chat_sessions` documents where `updated_at` does not exist.
2. THE migration SHALL be idempotent: running it multiple times SHALL NOT modify documents that already have an `updated_at` field.
3. THE migration SHALL run BEFORE the TTL index creation (Requirement 7.1) to ensure all documents are eligible for expiry.
4. THE migration SHALL log the number of documents updated.

### Requirement 27: Update Relevant Documentation

**User Story:** As a developer onboarding to the project, I want the documentation to accurately reflect the current chat and diagnosis workflows, so that I can understand the system without reading every source file.

#### Acceptance Criteria

1. THE `docs/rag-chat-workflow.md` SHALL be updated to reflect the new chat session flow, including conversation history being passed to the LLM, session ownership checks, session listing, and pagination.
2. THE `docs/rag-chat-workflow.md` Chat Session Flow mermaid diagram SHALL be updated to show the `_load_history` call and `session_history` parameter being passed to the RAG pipeline.
3. THE `docs/architecture.md` SHALL be updated to document the source relevance filtering, the idempotency mechanism on diagnosis requests, and the single-write consultation persistence on the MCP path.
4. THE `docs/api-reference.md` SHALL be updated to document the new and modified endpoints: `GET /api/v1/chat/sessions`, `DELETE /api/v1/chat/sessions/{session_id}`, updated pagination parameters on `GET /api/v1/chat/history/{session_id}`, and the `idempotency_key` and `session_id` fields on diagnosis/prescription requests.
5. THE `docs/hipaa-compliance.md` SHALL be updated to document the session ownership enforcement on both chat and diagnosis retrieval endpoints, and the 90-day TTL on chat sessions.
6. THE `docs/ops-guide.fr.md` and `docs/ops-guide.en.md` SHALL be updated to document the new `SOURCE_RELEVANCE_THRESHOLD` configuration setting, the chat session TTL index, and the `updated_at` backfill migration.
