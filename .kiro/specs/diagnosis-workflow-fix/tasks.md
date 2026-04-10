# Implementation Plan: Diagnosis Workflow Fix

## Overview

Fix the Diagno-Pilot diagnosis workflow by addressing infrastructure configuration, core bugs, feature additions, and housekeeping. Implementation follows the dependency order: infrastructure first, then core bug fixes, then feature additions, then housekeeping.

## Tasks

- [x] 1. Fix infrastructure configuration (MongoDB, Redis, API keys, LLM URL)
  - [x] 1.1 Change `MODEL_CONTAINER_URL` default to empty string in `backend/core/config.py`
    - Change `MODEL_CONTAINER_URL: str = "http://model:8080/v1"` to `MODEL_CONTAINER_URL: str = ""`
    - This ensures `LLM_PRIMARY_URL` is used when no local model container is configured
    - _Requirements: 2.1, 2.2_

  - [x] 1.2 Add MongoDB URI credential warning validator in `backend/core/config.py`
    - Add a model validator that detects when `MONGODB_URI` has a Docker service hostname (single-label, no dots, not localhost) but no `@` in the URI
    - Log a warning about potentially missing authentication
    - _Requirements: 3.3, 3.4_

  - [x] 1.3 Fix `.env` file with correct credentials and placeholders
    - Update `MONGODB_URI` to include auth credentials: `mongodb://diagno_dev:diagno_dev_pass@mongo:27017/diagno_pilot?authSource=admin`
    - Update `REDIS_URL` to include password: `redis://:diagno_redis_dev@redis:6379/0`
    - Replace `LLM_FALLBACK_API_KEY` real key with placeholder `your_openai_api_key_here`
    - Run `git rm --cached .env` to remove `.env` from git tracking (Req 4 AC1)
    - Verify `.gitignore` already contains `.env`; add it if missing (Req 4 AC3)
    - _Requirements: 3.2, 4.1, 4.3, 7.1_

  - [x] 1.4 Update `.env.example` with new/modified variable documentation
    - Add `DIAGNOSIS_MODE` with comment explaining valid values (`rag`, `mcp`, `agent`)
    - Update `MODEL_CONTAINER_URL` comment to explain priority order (MODEL_CONTAINER_URL > LLM_PRIMARY_URL) and new empty default
    - Ensure `MONGODB_URI`, `REDIS_URL`, `LLM_FALLBACK_API_KEY` have descriptive placeholder comments
    - _Requirements: 2.4, 7.2, 11.3_

  - [x] 1.5 Write property test for MongoDB URI credential detection
    - **Property 9: MongoDB URI credential detection**
    - Generate URIs with/without credentials and various hostnames; verify warning is emitted for Docker service names without `@`
    - **Validates: Requirements 3.3**

  - [x] 1.6 Write property test for LLM URL priority selection
    - **Property 3: LLM URL priority**
    - Generate `(MODEL_CONTAINER_URL, LLM_PRIMARY_URL)` pairs; verify `LLMRouter` selects `MODEL_CONTAINER_URL` when non-empty, `LLM_PRIMARY_URL` when empty
    - **Validates: Requirements 2.1, 2.2**

- [x] 2. Checkpoint — Ensure all tests pass
  - Run `pytest` from the `backend/` directory to verify no regressions from infrastructure changes. Ask the user if questions arise.

- [x] 3. Fix confidence score bug in diagnose router
  - [x] 3.1 Remove `session_id` guard from `confidence_score` in `backend/routers/diagnose.py`
    - In the MongoDB document construction, change `"confidence_score": result.confidence_score if result.session_id else None` to `"confidence_score": result.confidence_score`
    - In the `DiagnoseResponse` return, change `confidence_score=result.confidence_score if result.session_id else None` to `confidence_score=result.confidence_score`
    - Both occurrences in the `diagnose_symptoms` endpoint must be fixed
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

  - [x] 3.2 Write property test for confidence score propagation
    - **Property 5: Confidence score is never nullified by session_id**
    - Generate `(confidence_score, session_id)` pairs; verify the router includes the original `confidence_score` without conditional nullification
    - **Validates: Requirements 8.1, 8.2, 8.3, 8.4**

- [x] 4. Fix diagnostic parser markdown stripping
  - [x] 4.1 Add `_clean_llm_response()` method to `DiagnosticParser` in `backend/services/diagnostic_parser.py`
    - Strip `<think>...</think>` XML blocks using `re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL | re.IGNORECASE)` (case-insensitive to handle `<Think>`, `<THINK>` variants)
    - Strip markdown code fences (`` ```json ``, `` ```JSON ``, bare `` ``` ``)
    - Strip preamble before first `[` and postamble after last `]`
    - _Requirements: 5.1, 5.2, 5.3_

  - [x] 4.2 Integrate `_clean_llm_response()` into `DiagnosticParser.parse()` method
    - Call `_clean_llm_response()` on the input before the existing `re.search(r"\[.*\]", ...)` extraction
    - Ensure fewer-than-3 valid diagnoses still returns placeholders with `parse_failed=True`
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [x] 4.3 Write property test for parser markdown stripping round-trip
    - **Property 4: Diagnostic parser markdown stripping round-trip**
    - Generate valid JSON arrays of 3+ diagnosis objects; wrap in random combinations of markdown fences, `<think>` blocks, and preamble/postamble; verify `parse()` produces the same results as parsing bare JSON
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.5**

- [x] 5. Fix AgentPipeline partial differential parser
  - [x] 5.1 Rewrite `_parse_partial_differential()` in `backend/services/agent_pipeline.py` with JSON-first parsing
    - Try JSON extraction first using `re.search(r"\[.*\]", answer, re.DOTALL)` and `json.loads`
    - Extract `condition`, `probability` (clamped to [0.0, 1.0]), `icd_code`, and `matching_symptoms` from each item
    - If JSON parsing succeeds and produces results, return them
    - If JSON parsing fails, fall back to existing French-keyword regex extraction
    - Add `import json` at the top of the module (alongside existing `import re`)
    - _Requirements: 9.1, 9.2, 9.3, 9.4_

  - [x] 5.2 Write property test for AgentPipeline JSON parsing
    - **Property 6: AgentPipeline JSON-first parsing with correct extraction**
    - Generate valid JSON arrays of diagnosis objects; verify `_parse_partial_differential` extracts matching `DifferentialDiagnosis` objects with clamped probabilities
    - **Validates: Requirements 9.1, 9.3, 9.5**

  - [x] 5.3 Write property test for AgentPipeline regex fallback
    - **Property 7: AgentPipeline regex fallback for French-keyword text**
    - Generate strings with French diagnostic keyword patterns but no valid JSON; verify at least one `DifferentialDiagnosis` is extracted
    - **Validates: Requirements 9.2**

- [x] 6. Checkpoint — Ensure all tests pass
  - Run `pytest` from the `backend/` directory to verify core bug fixes and new property tests pass. Ask the user if questions arise.

- [x] 7. Add diagnosis mode routing
  - [x] 7.1 Add `DIAGNOSIS_MODE` field to `Settings` in `backend/core/config.py`
    - Add `DIAGNOSIS_MODE: Literal["rag", "mcp", "agent"] = "rag"` field
    - Add `from typing import Literal` import
    - Pydantic's `Literal` type handles validation automatically — unrecognized values raise `ValidationError` at startup
    - _Requirements: 1.1, 1.2_

  - [x] 7.2 Add routing logic to `get_differential_diagnosis()` in `backend/services/diagnostic_service.py`
    - Replace the hardcoded RAG-only call with a mode-based dispatch using `settings.DIAGNOSIS_MODE`
    - For `"rag"`: delegate to `_get_diagnosis_via_rag()` (existing behavior)
    - For `"mcp"`: delegate to `_get_diagnosis_via_mcp()` if `self._mcp_host is not None`, else fall back to RAG with a logged warning
    - For `"agent"`: delegate to `_get_diagnosis_via_agent_pipeline()` if `self._agent_pipeline is not None`, else fall back to RAG with a logged warning
    - _Requirements: 1.3, 1.4, 1.5, 1.6, 1.7_

  - [x] 7.3 Add `diagnosis_mode` field to `DiagnoseResponse` and populate in endpoint
    - Add `diagnosis_mode: str | None = None` to the `DiagnoseResponse` Pydantic model in `backend/routers/diagnose.py`
    - Populate `diagnosis_mode` from `settings.DIAGNOSIS_MODE` in the `diagnose_symptoms` endpoint response and MongoDB document
    - _Requirements: 1.8, 1.9_

  - [x] 7.4 Write property test for DIAGNOSIS_MODE validation
    - **Property 1: DIAGNOSIS_MODE validation accepts exactly the valid set**
    - Generate random strings; verify `Settings(DIAGNOSIS_MODE=value)` succeeds iff value is in `{"rag", "mcp", "agent"}`
    - **Validates: Requirements 1.1, 1.2**

  - [x] 7.5 Write property test for routing correctness
    - **Property 2: Diagnosis mode routing selects the correct path**
    - Generate `(mode, has_mcp, has_agent)` tuples; mock the three path methods; verify correct delegation and fallback behavior
    - **Validates: Requirements 1.3, 1.4, 1.5, 1.6, 1.7**

- [x] 8. Add empty knowledge base warning to LlamaIndexPipeline
  - [x] 8.1 Add `degraded_warning` for empty collection and no-chunks scenarios in `backend/services/llamaindex_pipeline.py`
    - First, add `degraded_warning: str | None = None` field to `RAGResponse` in `backend/models/document.py` if not already present
    - In the `query()` method, before the existing `if not chunks:` block, use `estimated_document_count()` (O(1) on MongoDB) to check if the collection is empty and set `degraded_warning` to "No medical documents indexed — diagnoses are based on LLM general knowledge only."
    - When the collection has documents but retrieval returns zero chunks, set `degraded_warning` to "No relevant documents found for these symptoms — diagnoses are based on LLM general knowledge only."
    - Set the `degraded_warning` field on the `RAGResponse` object
    - _Requirements: 6.1, 6.2_

  - [x] 8.2 Verify and fix `degraded_warning` propagation through DiagnosticOrchestrator and Diagnose Router
    - Check that `_get_diagnosis_via_rag()` in `diagnostic_service.py` propagates `rag_response.degraded_warning` to `DiagnosticResult`; add propagation if missing
    - Check that `diagnose.py` includes `degraded_warning` in the `DiagnoseResponse`; add it if missing
    - _Requirements: 6.3, 6.4_

  - [x] 8.3 Write property test for degraded warning propagation
    - **Property 8: Degraded warning propagation**
    - Generate `RAGResponse` objects with random `degraded_warning` strings; verify `DiagnosticOrchestrator` propagates the exact string to `DiagnosticResult.degraded_warning`
    - **Validates: Requirements 6.3**

- [x] 9. Checkpoint — Ensure all tests pass
  - Run `pytest` from the `backend/` directory to verify feature additions and routing tests pass. Ask the user if questions arise.

- [x] 10. Add startup migration for existing consultations
  - [x] 10.1 Add idempotent backfill migration in `backend/main.py` lifespan function
    - Add `update_many` to set `confidence_score` to `null` on consultations missing the field
    - Add `update_many` to set `diagnosis_mode` to `"rag"` on consultations missing the field
    - Wrap in try/except so migration failures log an error but don't block startup
    - Log the number of modified documents for each backfill
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

- [x] 11. Update documentation
  - [x] 11.1 Add diagnosis mode routing diagram to `docs/rag-chat-workflow.md`
    - Add a new section with a Mermaid flowchart showing the three diagnosis paths (RAG, MCP, AgentPipeline) and the `DIAGNOSIS_MODE` routing logic
    - Document the LLM URL priority order (`MODEL_CONTAINER_URL` > `LLM_PRIMARY_URL`) and correct default values
    - _Requirements: 11.1, 11.2_

  - [x] 11.2 Add environment configuration section to `README.md`
    - Add a section documenting required environment configuration for MongoDB authentication, Redis authentication, and LLM endpoint setup
    - Add a security note that the previously committed `LLM_FALLBACK_API_KEY` is compromised and must be rotated
    - _Requirements: 4.4, 11.4_

- [x] 12. Final checkpoint — Ensure all tests pass
  - Run `pytest` from the `backend/` directory to verify the full test suite passes after all changes. Ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation after each phase
- Property tests validate universal correctness properties from the design document
- The implementation order follows the dependency chain: infrastructure → core bugs → features → housekeeping
- The project uses Python 3.12 + FastAPI + Hypothesis for property-based testing
