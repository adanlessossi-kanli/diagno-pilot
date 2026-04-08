# Implementation Plan: Chat & Diagnosis Workflow Improvements

## Overview

This plan implements 27 requirements across the Chat and Diagnosis workflows in Diagno-Pilot. Tasks are ordered by dependency: shared models and config first, then backend services, routers, frontend, startup indexes/migrations, and documentation. Each task references specific requirements and design sections.

## Tasks

- [x] 1. Add new settings and update shared data models
  - [x] 1.1 Add `SOURCE_RELEVANCE_THRESHOLD` to `backend/core/config.py`
    - Add `SOURCE_RELEVANCE_THRESHOLD: float = 0.3` to the `Settings` class
    - _Requirements: 10.2_

  - [x] 1.2 Update `Symptom` model with `max_length` on `name` field
    - In `backend/models/consultation.py`, change `name: str` to `name: str = Field(max_length=200)`
    - _Requirements: 16.3_

  - [x] 1.3 Add `parse_failed` and `consultation_persisted` fields to `DiagnosticResult`
    - In `backend/services/diagnostic_service.py`, add `parse_failed: bool = False` and `consultation_persisted: bool = False` to the `DiagnosticResult` dataclass
    - _Requirements: 14.2, 11.3_

  - [x] 1.4 Add `min_dose_floor_pct` field to `AntibioticProtocol`
    - In `backend/services/prescription_service.py`, add `min_dose_floor_pct: int = 10` to the `AntibioticProtocol` dataclass
    - _Requirements: 17.4_


- [x] 2. Update DiagnosticParser with locale-aware failure signaling
  - [x] 2.1 Change `DiagnosticParser.parse()` return type to `tuple[list[DifferentialDiagnosis], bool]`
    - Add `locale: str = "en"` parameter
    - Return `(diagnoses, False)` when ≥3 valid diagnoses parsed
    - Return `(placeholders, True)` when <3 valid diagnoses, using "Diagnostic indisponible" for `fr*` locales and "Diagnosis unavailable" for `en`
    - _Requirements: 14.1, 14.4_

  - [x] 2.2 Write property test for DiagnosticParser failure signaling
    - **Property 8: Diagnostic parser failure signaling**
    - Test that parse_failed is True when <3 diagnoses extracted, False otherwise
    - Test localized placeholder text for fr-TG, fr-BJ, fr, en locales
    - **Validates: Requirements 14.1, 14.4**

- [x] 3. Update DiagnosticParser callers
  - [x] 3.1 Update `_get_diagnosis_via_rag` in `diagnostic_service.py` to unpack tuple
    - Change `diagnoses = self._diagnostic_parser.parse(...)` to `diagnoses, parse_failed = self._diagnostic_parser.parse(..., locale=locale)`
    - Set `result.parse_failed = parse_failed`
    - _Requirements: 14.1, 14.2_

  - [x] 3.2 Update `_get_diagnosis_via_mcp` LLM fallback block in `diagnostic_service.py` to unpack tuple
    - Change `parsed = self._diagnostic_parser.parse(...)` to `parsed, _parse_failed = self._diagnostic_parser.parse(..., locale=locale)`
    - _Requirements: 14.1_

- [x] 4. Checkpoint — Ensure parser changes compile and existing tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Update ChatService with history passthrough, ownership, listing, pagination, and deletion
  - [x] 5.1 Modify `ChatService.send_message` to load and pass session history
    - Call `self._load_history(session_id)` and cap at 20 messages
    - Pass `session_history=history` to `self._rag.query()`
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [x] 5.2 Modify `ChatService.get_history` to accept `user_id` parameter
    - Add `user_id: str | None = None` parameter
    - Include `user_id` in MongoDB query filter when provided
    - _Requirements: 2.3_

  - [x] 5.3 Add `ChatService.list_sessions` method
    - Query `chat_sessions` filtered by `user_id`, sorted by `updated_at` descending
    - Project `session_id`, `created_at`, `updated_at`, and first message preview via `$slice`
    - Support `skip` and `limit` parameters
    - _Requirements: 3.1, 3.2, 3.5_

  - [x] 5.4 Add `ChatService.get_history_paginated` method
    - Accept `session_id`, `user_id`, `skip`, `limit` parameters
    - Use MongoDB `$slice` for message window
    - Return `total_messages` count via aggregation
    - _Requirements: 4.1, 4.3, 4.4_

  - [x] 5.5 Add `ChatService.delete_session` method
    - Accept `session_id` and optional `user_id` for ownership filtering
    - Return `bool` indicating whether deletion occurred
    - _Requirements: 7.2_

  - [x] 5.6 Write property test for history cap invariant
    - **Property 1: History cap invariant**
    - Verify session_history passed to pipeline contains at most 20 messages and they are the most recent
    - **Validates: Requirements 1.4**


- [x] 6. Update LlamaIndexPipeline with context-aware cache key and source filtering
  - [x] 6.1 Update `_build_cache_key` to include session history hash
    - Add `session_history` parameter
    - When `session_history` is non-empty, hash the history JSON and append to cache key
    - When empty/None, preserve existing key format
    - _Requirements: 5.1, 5.2, 5.3_

  - [x] 6.2 Update `query()` to pass `session_history` to `_build_cache_key`
    - Thread the `session_history` parameter through to the cache key builder
    - _Requirements: 5.1_

  - [x] 6.3 Add source relevance filtering after chunk retrieval
    - Filter `sources` list by `settings.SOURCE_RELEVANCE_THRESHOLD` before including in response
    - When no chunks meet threshold, return empty `sources` list
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

  - [x] 6.4 Write property test for cache key determinism and differentiation
    - **Property 5: Context-aware cache key determinism and differentiation**
    - Identical inputs produce identical keys; differing inputs produce different keys
    - Empty/None history matches legacy format
    - **Validates: Requirements 5.1, 5.2, 5.3**

  - [x] 6.5 Write property test for source relevance filtering
    - **Property 7: Source relevance filtering**
    - Only chunks with score ≥ threshold appear in sources; empty when none qualify
    - **Validates: Requirements 10.1, 10.3**

- [x] 7. Update Chat Router with validation, ownership, new endpoints, and pagination
  - [x] 7.1 Add input validation to `ChatMessageRequest`
    - Add `Field(min_length=1, max_length=4000)` to `message` field
    - Add `@field_validator("message", mode="before")` to strip whitespace
    - _Requirements: 6.1, 6.2, 6.3_

  - [x] 7.2 Add ownership check to `get_chat_history` endpoint
    - Extract `user_id` from `current_user`, bypass if role is `admin`
    - Pass `user_id` to `ChatService.get_history`
    - Add `skip` and `limit` query parameters (limit default 50, cap 200)
    - Include `total_messages` in response
    - _Requirements: 2.1, 2.2, 2.4, 4.1, 4.2, 4.3_

  - [x] 7.3 Add `GET /api/v1/chat/sessions` endpoint
    - Return current user's sessions sorted by `updated_at` descending
    - Support `skip` and `limit` query params (limit default 20, cap 100)
    - Return empty list with HTTP 200 when no sessions exist
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 7.4 Add `DELETE /api/v1/chat/sessions/{session_id}` endpoint
    - Verify session ownership (admin bypass)
    - Return HTTP 404 if session not found or not owned
    - _Requirements: 7.2, 7.3, 7.4, 7.5_

  - [x] 7.5 Write property test for chat message validation
    - **Property 6: Chat message validation**
    - Accept iff `1 ≤ len(message.strip()) ≤ 4000`; reject with 422 otherwise
    - **Validates: Requirements 6.1, 6.2, 6.3**

  - [x] 7.6 Write property test for session ownership enforcement
    - **Property 2: Session ownership enforcement**
    - Access granted iff `requester_id == owner_id` OR `role == "admin"`; 404 otherwise
    - **Validates: Requirements 2.1, 2.2, 2.4, 7.3, 7.4, 7.5, 13.1, 13.2, 13.3**

  - [x] 7.7 Write property test for session listing invariants
    - **Property 3: Session listing invariants**
    - Only user's sessions returned, sorted by updated_at desc, respects skip/limit
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.5**

  - [x] 7.8 Write property test for pagination parameter clamping
    - **Property 4: Pagination parameter clamping**
    - Effective limit is `min(max(limit, 1), cap)` for each endpoint
    - **Validates: Requirements 3.3, 4.2**

- [x] 8. Checkpoint — Ensure chat workflow changes compile and tests pass
  - Ensure all tests pass, ask the user if questions arise.


- [x] 9. Update Diagnose Router with validation, ownership, idempotency, duplicate prevention, and prescription linking
  - [x] 9.1 Update `DiagnoseRequest` model with validation and new fields
    - Add `Field(min_length=1, max_length=30)` to `symptoms` list
    - Add `idempotency_key: str | None = None` field
    - _Requirements: 16.1, 16.2, 20.1_

  - [x] 9.2 Add `parse_failed` field to `DiagnoseResponse`
    - Add `parse_failed: bool = False` to the response model
    - Set from `result.parse_failed` in the endpoint handler
    - _Requirements: 14.3_

  - [x] 9.3 Add idempotency check to `diagnose_symptoms` endpoint
    - Before running diagnosis, check if `idempotency_key` exists in consultations
    - If found, return existing consultation response with HTTP 200
    - Store `idempotency_key` in consultation document when provided
    - _Requirements: 20.1, 20.2, 20.3, 20.4, 20.5_

  - [x] 9.4 Prevent duplicate consultation writes on MCP path
    - Check `result.consultation_persisted` (or `result.session_id is not None`) before router insert
    - Skip `insert_one` when MCP path already persisted the consultation
    - _Requirements: 11.1, 11.2, 11.3_

  - [x] 9.5 Add ownership enforcement to `get_diagnosis_session` endpoint
    - Include `current_user["_id"]` in MongoDB query filter
    - Admin bypass: skip user_id filter when role is `admin`
    - Return HTTP 404 when no match
    - _Requirements: 13.1, 13.2, 13.3_

  - [x] 9.6 Add `session_id` field to `PrescriptionRequest` and implement prescription linking
    - Add `session_id: str | None = None` to `PrescriptionRequest`
    - When `session_id` provided, update consultation's `prescription` and `alerts` fields
    - Apply ownership check on the consultation update (admin bypass)
    - _Requirements: 12.1, 12.2, 12.3, 12.4_

  - [x] 9.7 Write property test for diagnosis input validation
    - **Property 10: Diagnosis input validation**
    - Accept iff `1 ≤ len(symptoms) ≤ 30` and all `name` lengths ≤ 200; reject with 422 otherwise
    - **Validates: Requirements 16.1, 16.2, 16.3, 16.4**

  - [x] 9.8 Write property test for idempotency on diagnosis requests
    - **Property 12: Idempotency on diagnosis requests**
    - Existing idempotency_key returns existing response, no new document created
    - **Validates: Requirements 20.2, 20.3**

- [x] 10. Update Synthesis_Agent with symptom deduplication fix
  - [x] 10.1 Fix `synthesize()` to union matching_symptoms when merging duplicate conditions
    - Add `_union_symptoms` helper for case-insensitive deduplication
    - When merging, keep highest probability and union symptom lists
    - _Requirements: 15.1, 15.2, 15.3_

  - [x] 10.2 Write property test for synthesis agent merge correctness
    - **Property 9: Synthesis agent merge correctness**
    - Merged result has highest probability, case-insensitive symptom union, no duplicates, condition appears once
    - **Validates: Requirements 15.1, 15.2, 15.3**

- [x] 11. Update PrescriptionService with dose floor clamping
  - [x] 11.1 Add dose floor clamping when both renal and hepatic failure are present
    - Capture `pre_adjustment_dose` before organ-failure adjustments
    - After both adjustments, clamp to `pre_adjustment_dose * (min_dose_floor_pct / 100)` if below
    - Log warning when clamping is applied
    - Only apply when BOTH renal and hepatic failure are present
    - _Requirements: 17.1, 17.2, 17.3, 17.4_

  - [x] 11.2 Write property test for prescription dose floor clamping
    - **Property 11: Prescription dose floor clamping**
    - When both failures present, final dose ≥ pre_adjustment_dose × floor_pct; when only one, no clamping
    - **Validates: Requirements 17.1, 17.2, 17.4**

- [x] 12. Checkpoint — Ensure diagnosis workflow changes compile and tests pass
  - Ensure all tests pass, ask the user if questions arise.


- [x] 13. Update MCP_Host timeout simplification
  - [x] 13.1 Remove inner `asyncio.wait_for` from `_call_agent_http`
    - Ensure `_call_agent_http` has no internal timeout wrapping
    - The outer `asyncio.wait_for` in `run_diagnostic._call_with_timeout` is the single timeout layer
    - Effective timeout per agent is exactly `AGENT_TIMEOUT` seconds
    - _Requirements: 18.1, 18.2, 18.3_

- [x] 14. Update DiagnosticOrchestrator audit completeness and MCP consultation flag
  - [x] 14.1 Fix `_write_audit` to use actual confidence_score and agent_contributions
    - Replace hardcoded `confidence_score=0.0` with `result.confidence_score`
    - Replace empty `agent_results=[]` with populated list from `result.agent_contributions`
    - _Requirements: 19.1, 19.2, 19.3_

  - [x] 14.2 Set `consultation_persisted=True` in `_create_mcp_consultation`
    - After successful consultation insert, set `result.consultation_persisted = True`
    - _Requirements: 11.3_

- [x] 15. Update AgentPipeline with error resilience and improved sub-questions
  - [x] 15.1 Change `asyncio.gather` to use `return_exceptions=True` in `run()`
    - Convert exceptions to `AgentResult` with `error` field set
    - Preserve agent name from task order for error results
    - _Requirements: 21.1, 21.2, 21.3_

  - [x] 15.2 Rewrite `_SUB_QUESTIONS` with West African tropical medicine context
    - Update all 5 sub-question templates with tropical disease context, patient profile, and guidelines references
    - Add `{patient_context}` and `{guidelines_ref}` placeholders
    - _Requirements: 22.1, 22.2, 22.3, 22.4, 22.5, 22.6, 22.7_

  - [x] 15.3 Update `AgentPipeline.run()` to build patient_context and guidelines_ref strings
    - Build `patient_context` string from patient_profile (age group, weight, allergies, comorbidities)
    - Map region to `guidelines_ref` (TG→CHU Lomé, BJ→CHU Abomey-Calavi, else→OMS AFRO / MSF)
    - Include symptom severity and duration in `symptom_text`
    - Format all placeholders in sub-questions
    - _Requirements: 22.2, 22.4_

- [x] 16. Update MCP server tool handlers with patient profile and symptom detail
  - [x] 16.1 Update `symptomatology_server.py` `_handle_query_symptomatology`
    - Include patient profile data (age group, weight, allergies, comorbidities) in sub-question when provided
    - Include symptom severity and duration in sub-question text, not just names
    - _Requirements: 22.8, 22.9_

  - [x] 16.2 Update `epidemiology_server.py` `_handle_query_epidemiology`
    - Include patient profile data in sub-question when provided
    - Include symptom severity and duration in sub-question text
    - _Requirements: 22.8, 22.9_

  - [x] 16.3 Update `lab_server.py` `_handle_query_lab`
    - Include patient profile data in sub-question when provided
    - Include symptom severity and duration in sub-question text
    - _Requirements: 22.8, 22.9_

  - [x] 16.4 Update `treatment_server.py` `_handle_query_treatment`
    - Include patient profile data in sub-question when provided
    - Include symptom severity and duration in sub-question text
    - _Requirements: 22.8, 22.9_

- [x] 17. Update prompts and system prompts
  - [x] 17.1 Update `PromptBuilder.build()` with locale-aware instruction language
    - Write instruction paragraph in French for `fr*` locales, English otherwise
    - Include `matching_symptoms` in the JSON output schema
    - _Requirements: 23.1, 23.2_

  - [x] 17.2 Update `DIAGNOSIS_SYSTEM_PROMPT` in `diagnostic_service.py`
    - Add West African tropical medicine context
    - Instruct LLM to return raw JSON without markdown code block wrappers
    - Add language detection instruction (respond in user's message language, fallback to locale)
    - _Requirements: 23.3, 23.4, 24.2_

  - [x] 17.3 Update `GROUNDING_SYSTEM_PROMPT` in `llamaindex_pipeline.py`
    - Add language detection instruction: detect user's message language and respond in that language
    - Add locale fallback for ambiguous cases
    - _Requirements: 24.1, 24.3, 24.4_

  - [x] 17.4 Write property test for PromptBuilder locale-aware instruction language
    - **Property 13: PromptBuilder locale-aware instruction language**
    - French instruction for `fr*` locales, English otherwise; JSON schema includes `matching_symptoms`
    - **Validates: Requirements 23.1, 23.2**

- [x] 18. Checkpoint — Ensure all backend changes compile and tests pass
  - Ensure all tests pass, ask the user if questions arise.


- [x] 19. Update web frontend chat page
  - [x] 19.1 Add session persistence via localStorage
    - Store `sessionId` in `localStorage` under key `diagno-pilot-chat-session` on session creation
    - Restore `sessionId` from `localStorage` on page load
    - Clear stored `sessionId` on "New Session" click
    - Load message history from backend when restoring a session
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

  - [x] 19.2 Improve optimistic message rollback and retry
    - On send failure: remove optimistic user message, restore input text to input field
    - Show error message with "Retry" button on HTTP 500 or timeout
    - On Retry click: re-add optimistic message and re-attempt send
    - _Requirements: 9.1, 9.2, 9.3, 9.4_

  - [x] 19.3 Hide Sources panel when response contains zero sources
    - In `SourcesPanel` component, return `null` when `sources.length === 0` (already implemented, verify)
    - _Requirements: 10.5_

  - [x] 19.4 Display parse failure warning banner on diagnosis results
    - When `parse_failed` is true in the diagnosis API response, show a prominent localized warning banner
    - French: "Les résultats diagnostiques peuvent être incomplets ou peu fiables. Veuillez exercer votre jugement clinique."
    - English: "Diagnostic results may be incomplete or unreliable. Please exercise clinical judgment."
    - Hide the banner when `parse_failed` is false or absent
    - _Requirements: 25.1, 25.3, 25.4_

- [x] 20. Update mobile frontend diagnose screen
  - [x] 20.1 Add state persistence via AsyncStorage
    - Persist current diagnosis session state (step, symptoms, diagnoses, prescription) using `AsyncStorage`
    - Restore state when navigating back to the diagnose tab
    - _Requirements: 8.5_

  - [x] 20.2 Replace generic Alert with Retry button on API failure
    - On diagnosis API failure: show inline error with "Retry" button instead of `Alert.alert`
    - On prescription API failure: show inline error with "Retry" button instead of `Alert.alert`
    - _Requirements: 9.5_

  - [x] 20.3 Display parse failure warning banner on diagnosis results
    - When `parse_failed` is true in the diagnosis API response, show a prominent localized warning banner
    - French: "Les résultats diagnostiques peuvent être incomplets ou peu fiables. Veuillez exercer votre jugement clinique."
    - English: "Diagnostic results may be incomplete or unreliable. Please exercise clinical judgment."
    - Hide the banner when `parse_failed` is false or absent
    - _Requirements: 25.2, 25.3, 25.4_

- [x] 21. Add startup indexes and data migration in main.py
  - [x] 21.1 Add idempotent backfill migration for `updated_at` on `chat_sessions`
    - Use `update_many` with `{"updated_at": {"$exists": False}}` filter
    - Set `updated_at` to `created_at` (or current timestamp if `created_at` is also missing)
    - Log the number of documents updated
    - Must run BEFORE the TTL index creation
    - _Requirements: 26.1, 26.2, 26.3, 26.4_

  - [x] 21.2 Create TTL index on `chat_sessions.updated_at`
    - Add `create_index("updated_at", expireAfterSeconds=90*24*3600, background=True)` on `chat_sessions` collection
    - _Requirements: 7.1_

  - [x] 21.3 Create unique sparse index on `consultations.idempotency_key`
    - Add `create_index("idempotency_key", unique=True, sparse=True, background=True)` on `consultations` collection
    - _Requirements: 20.4_

- [x] 22. Checkpoint — Ensure frontend and startup changes compile and tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 23. Update documentation
  - [x] 23.1 Update `docs/rag-chat-workflow.md`
    - Document conversation history passthrough, session ownership, session listing, pagination
    - Update Chat Session Flow mermaid diagram to show `_load_history` call and `session_history` parameter
    - _Requirements: 27.1, 27.2_

  - [x] 23.2 Update `docs/architecture.md`
    - Document source relevance filtering, idempotency mechanism, single-write consultation persistence on MCP path
    - _Requirements: 27.3_

  - [x] 23.3 Update `docs/api-reference.md`
    - Document new endpoints: `GET /api/v1/chat/sessions`, `DELETE /api/v1/chat/sessions/{session_id}`
    - Document updated pagination params on `GET /api/v1/chat/history/{session_id}`
    - Document `idempotency_key` and `session_id` fields on diagnosis/prescription requests
    - _Requirements: 27.4_

  - [x] 23.4 Update `docs/hipaa-compliance.md`
    - Document session ownership enforcement on chat and diagnosis endpoints
    - Document 90-day TTL on chat sessions
    - _Requirements: 27.5_

  - [x] 23.5 Update `docs/ops-guide.fr.md` and `docs/ops-guide.en.md`
    - Document `SOURCE_RELEVANCE_THRESHOLD` configuration setting
    - Document chat session TTL index and `updated_at` backfill migration
    - _Requirements: 27.6_

- [x] 24. Final checkpoint — Ensure all tests pass and all requirements are covered
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- The DiagnosticParser return type change (task 2) is a breaking change — all callers are updated in task 3
- MCP server tool handler updates (task 16) are independent across the 4 servers and can be parallelized
- Frontend tasks (19, 20) are independent of each other and can be parallelized
