# Requirements Document

## Introduction

The Diagno-Pilot application is a FastAPI + MongoDB + LlamaIndex RAG system for medical diagnosis assistance in West Africa. The diagnosis workflow currently supports three execution paths (RAG, MCP multi-agent, AgentPipeline), but only the RAG path executes due to missing routing logic. Even the RAG path has critical bugs: the confidence score is always `None`, the parser returns useless placeholders instead of retrying, and the LLM URL priority is inverted. Additionally, infrastructure configuration (MongoDB auth, Redis auth, exposed API keys) and the AgentPipeline's French-regex parser are broken. This requirements document captures the fixes for all 9 identified issues plus the recommended improvements.

## Glossary

- **Diagnostic_Orchestrator**: The `DiagnosticOrchestrator` class in `diagnostic_service.py` that coordinates the three diagnosis paths (RAG, MCP, AgentPipeline) and produces a `DiagnosticResult`.
- **LLM_Router**: The `LLMRouter` class in `llm_router.py` that routes LLM generation requests to the primary model (Model_Container / Ollama) with GPT-5 fallback, using circuit breakers and retry policies.
- **RAG_Pipeline**: The `LlamaIndexPipeline` class in `llamaindex_pipeline.py` that performs vector retrieval over MongoDB Atlas and generates grounded answers via the LLM_Router.
- **MCP_Host**: The `MCP_Host` class in `mcp_host.py` that orchestrates four specialist MCP agent servers in parallel via HTTP+SSE JSON-RPC 2.0.
- **Agent_Pipeline**: The `AgentPipeline` class in `agent_pipeline.py` that runs five in-process specialist agents (symptomatology, epidemiology, lab, treatment, synthesis) using LlamaIndex query engines.
- **Diagnostic_Parser**: The `DiagnosticParser` class in `diagnostic_parser.py` that parses raw LLM JSON responses into validated `DifferentialDiagnosis` objects.
- **Diagnosis_Mode**: A configuration setting (`DIAGNOSIS_MODE`) that selects which diagnosis path the Diagnostic_Orchestrator uses: `rag`, `mcp`, or `agent`.
- **Confidence_Score**: A float between 0.0 and 1.0 representing the reliability of the diagnosis result, computed from source chunk relevance scores (RAG path) or weighted agent scores (MCP/Agent paths).
- **Partial_Differential_Parser**: The `_parse_partial_differential` function in `agent_pipeline.py` that extracts diagnosis conditions from LLM answer text using regex or JSON parsing.
- **Diagnose_Router**: The FastAPI router in `diagnose.py` that exposes the `/api/v1/diagnose/symptoms` endpoint and constructs the API response from `DiagnosticResult`.
- **Settings**: The `Settings` class in `config.py` (Pydantic BaseSettings) that loads environment variables and provides application configuration.

## Implementation Order

Requirements have dependencies that constrain execution order. The recommended sequence is:

1. **Infrastructure first** (Req 2, 3, 7, 4) — fix connectivity and security before touching application logic.
2. **Core bug fixes** (Req 8, 5, 9) — fix the RAG path and parsers so the baseline works.
3. **Feature additions** (Req 1, 6) — enable routing and add observability.
4. **Housekeeping** (Req 10, 11) — migration and documentation after code stabilizes.

## Requirements

### Requirement 1: Diagnosis Mode Routing

**Priority:** Critical

**User Story:** As a system administrator, I want to select the diagnosis execution path via a configuration flag, so that the MCP and AgentPipeline paths can be activated without code changes.

**Dependencies:** Req 2 (LLM URL fix), Req 9 (agent parser fix) — activating MCP or Agent mode without these fixes would produce different failures.

#### Acceptance Criteria

1. THE Settings SHALL expose a `DIAGNOSIS_MODE` field accepting the values `rag`, `mcp`, or `agent`, defaulting to `rag`.
2. IF `DIAGNOSIS_MODE` is set to an unrecognized value, THEN THE application SHALL raise a Pydantic validation error at startup with a message listing the valid options (`rag`, `mcp`, `agent`).
3. WHEN `DIAGNOSIS_MODE` is set to `rag`, THE Diagnostic_Orchestrator SHALL delegate to the RAG_Pipeline path.
4. WHEN `DIAGNOSIS_MODE` is set to `mcp`, THE Diagnostic_Orchestrator SHALL delegate to the MCP_Host path via `_get_diagnosis_via_mcp()`.
5. WHEN `DIAGNOSIS_MODE` is set to `agent`, THE Diagnostic_Orchestrator SHALL delegate to the Agent_Pipeline path via `_get_diagnosis_via_agent_pipeline()`.
6. IF `DIAGNOSIS_MODE` is set to `mcp` and the MCP_Host is not configured (i.e., `self._mcp_host is None`), THEN THE Diagnostic_Orchestrator SHALL fall back to the RAG_Pipeline path and log a warning.
7. IF `DIAGNOSIS_MODE` is set to `agent` and the Agent_Pipeline is not configured (i.e., `self._agent_pipeline is None`), THEN THE Diagnostic_Orchestrator SHALL fall back to the RAG_Pipeline path and log a warning.
8. THE Diagnose_Router SHALL include a `diagnosis_mode` field in the API response indicating which path (`rag`, `mcp`, or `agent`) produced the result.
9. THE `diagnosis_mode` field SHALL be stored in the MongoDB consultation document alongside the diagnoses.

### Requirement 2: LLM URL Priority Fix

**Priority:** Critical

**User Story:** As a developer, I want the LLM_Router to use the correct primary LLM URL, so that the Ollama instance is reachable when `MODEL_CONTAINER_URL` is not available.

#### Acceptance Criteria

1. THE Settings SHALL default `MODEL_CONTAINER_URL` to an empty string instead of `http://model:8080/v1`.
2. WHEN `MODEL_CONTAINER_URL` is empty and `LLM_PRIMARY_URL` is set, THE LLM_Router SHALL use `LLM_PRIMARY_URL` as the primary endpoint.
3. WHEN `MODEL_CONTAINER_URL` is set to a non-empty value, THE startup health check (existing `/health` endpoint logic) SHALL probe the endpoint and log a warning if unreachable, so that misconfigured Docker service names are surfaced early. No new health-check code is required — the existing `_probe_llm_primary()` in `main.py` already covers this when `LLM_PRIMARY_URL` resolves to the correct URL.
4. THE `.env.example` file SHALL document the `MODEL_CONTAINER_URL` and `LLM_PRIMARY_URL` fields with comments explaining the priority order: `MODEL_CONTAINER_URL` (if non-empty) takes precedence over `LLM_PRIMARY_URL`.

**Backward compatibility note:** Existing Docker Compose deployments that rely on the `model:8080` service must explicitly set `MODEL_CONTAINER_URL=http://model:8080/v1` in their `.env` file after this change.

### Requirement 3: MongoDB Authentication

**Priority:** High

**User Story:** As a system administrator, I want MongoDB connections to use authentication credentials, so that the database is secured against unauthorized access.

#### Acceptance Criteria

1. THE `.env.example` file SHALL document the `MONGODB_URI` field with a placeholder showing the authenticated URI format `mongodb://<user>:<password>@<host>:<port>/<database>?authSource=admin`.
2. THE `.env` file SHALL use a `MONGODB_URI` value that includes authentication credentials matching the Docker Compose configuration.
3. THE Settings validator SHALL detect when `MONGODB_URI` contains no credentials (no `@` in the URI) and the host is a Docker service name (single-label hostname, not `localhost`), and log a warning at startup indicating that authentication may be missing.
4. IF the MongoDB connection fails due to authentication errors, THEN THE application SHALL log a clear error message indicating an authentication failure and exit. Note: the existing `db.connect()` in `main.py` already catches `RuntimeError` and re-raises, which causes uvicorn to exit. This AC is satisfied by existing behavior combined with the credential warning from AC3.

### Requirement 4: Fallback API Key Security

**Priority:** Medium

**User Story:** As a security engineer, I want API keys removed from version control and loaded exclusively from environment variables, so that credentials are not exposed in the repository.

#### Acceptance Criteria

1. THE `.env` file SHALL be removed from git tracking via `git rm --cached .env` and SHALL use placeholder values for `LLM_FALLBACK_API_KEY` (e.g., `your_openai_api_key_here`).
2. THE `.env.example` file SHALL contain placeholder values for all API key fields (`LLM_PRIMARY_API_KEY`, `LLM_FALLBACK_API_KEY`, `JWT_SECRET`) with comments instructing the user to set real values.
3. THE `.gitignore` file SHALL include the `.env` file to prevent committing secrets.
4. THE `README.md` SHALL include a security note documenting that the previously committed `LLM_FALLBACK_API_KEY` is compromised and must be rotated in the OpenAI dashboard.

### Requirement 5: Diagnostic Parser Markdown Stripping

**Priority:** High

**User Story:** As a clinician, I want the diagnosis endpoint to return real diagnoses instead of placeholders, so that I receive clinically useful results even when the LLM wraps its JSON in markdown code blocks.

#### Acceptance Criteria

1. WHEN the LLM response contains a JSON array wrapped in markdown code fences (`` ```json ``, `` ```JSON ``, or bare `` ``` ``), THE Diagnostic_Parser SHALL strip the code fences and surrounding whitespace before attempting JSON extraction.
2. WHEN the LLM response contains `<think>...</think>` XML blocks (common with Qwen reasoning models), THE Diagnostic_Parser SHALL strip those blocks before attempting JSON extraction.
3. THE Diagnostic_Parser SHALL strip any text preceding the first `[` character and any text following the last `]` character in the cleaned response, to isolate the JSON array from preamble or postamble text.
4. WHEN the Diagnostic_Parser extracts fewer than 3 valid diagnoses after all stripping, THE Diagnostic_Parser SHALL return the placeholder list with `parse_failed=True`.
5. FOR ALL valid JSON arrays (with or without markdown wrapping, `<think>` blocks, or surrounding text), parsing then serializing then parsing SHALL produce an equivalent list of DifferentialDiagnosis objects (round-trip property).

### Requirement 6: Empty Knowledge Base Warning

**Priority:** Medium

**User Story:** As a clinician, I want to know when diagnoses are generated without document grounding, so that I can assess the reliability of the results.

#### Acceptance Criteria

1. WHEN the `document_chunks` collection has zero documents (checked via `estimated_document_count()` which is O(1) on MongoDB), THE RAG_Pipeline SHALL set a `degraded_warning` on the RAGResponse with the message "No medical documents indexed — diagnoses are based on LLM general knowledge only."
2. WHEN the `document_chunks` collection contains documents but the vector search returns zero relevant chunks for the query, THE RAG_Pipeline SHALL set a `degraded_warning` on the RAGResponse with the message "No relevant documents found for these symptoms — diagnoses are based on LLM general knowledge only."
3. WHEN the RAG_Pipeline returns a response with no sources, THE Diagnostic_Orchestrator SHALL propagate the `degraded_warning` to the DiagnosticResult.
4. THE Diagnose_Router SHALL include the `degraded_warning` in the API response so the frontend can display it to the clinician.

### Requirement 7: Redis Authentication

**Priority:** Medium

**User Story:** As a system administrator, I want Redis connections to use authentication, so that the cache layer is secured.

#### Acceptance Criteria

1. THE `.env` file SHALL include a `REDIS_URL` value with authentication credentials matching the Docker Compose Redis configuration (format: `redis://:<password>@<host>:<port>/<db>`).
2. THE `.env.example` file SHALL document the `REDIS_URL` field with a placeholder showing the authenticated format and a comment explaining the password must match `REDIS_PASSWORD` in Docker Compose.
3. IF Redis connection fails due to authentication errors, THEN THE application SHALL continue in degraded mode with caching disabled and log a warning indicating the authentication failure.

### Requirement 8: Confidence Score Bug Fix

**Priority:** Critical

**User Story:** As a clinician, I want to see the confidence score for RAG-based diagnoses, so that I can gauge the reliability of the results.

#### Acceptance Criteria

1. THE Diagnose_Router SHALL include `confidence_score` from the DiagnosticResult in the API response for all diagnosis paths (RAG, MCP, and Agent).
2. WHEN the RAG_Pipeline computes a non-null confidence_score, THE Diagnose_Router SHALL return that value regardless of whether `session_id` is set.
3. THE confidence_score SHALL NOT be conditionally nullified based on the presence or absence of `session_id` — it SHALL always reflect the value computed by the diagnosis path.
4. THE confidence_score stored in the MongoDB consultation document SHALL match the value returned in the API response.

### Requirement 9: AgentPipeline Partial Differential Parser Fix

**Priority:** High

**User Story:** As a developer, I want the AgentPipeline to correctly extract diagnoses from LLM responses, so that agent results contribute meaningful partial differentials to the synthesis.

#### Acceptance Criteria

1. WHEN the LLM answer contains a valid JSON array of diagnosis objects, THE Partial_Differential_Parser SHALL parse the JSON and return a list of DifferentialDiagnosis objects, extracting `condition`, `probability`, `icd_code`, and `matching_symptoms` fields, clamping probability to [0.0, 1.0].
2. WHEN the LLM answer contains French-keyword diagnosis text (e.g., "diagnostic : Paludisme") but no valid JSON array, THE Partial_Differential_Parser SHALL extract conditions using the existing regex pattern.
3. THE Partial_Differential_Parser SHALL attempt JSON parsing first; only if JSON parsing fails SHALL it fall back to regex extraction.
4. WHEN the LLM answer contains neither valid JSON nor French-keyword text, THE Partial_Differential_Parser SHALL return an empty list.
5. FOR ALL valid JSON arrays of diagnoses, parsing then serializing then parsing SHALL produce an equivalent list of DifferentialDiagnosis objects (round-trip property).

### Requirement 10: Data Migration for Existing Consultations

**Priority:** Low

**User Story:** As a system administrator, I want existing consultation documents in MongoDB to be migrated to include the new fields, so that historical data remains consistent with the updated schema.

#### Acceptance Criteria

1. WHEN the application starts, THE application SHALL run an idempotent migration that sets `confidence_score` to `null` on existing consultation documents where the field is missing, to maintain schema consistency.
2. WHEN the application starts, THE application SHALL run an idempotent migration that backfills `diagnosis_mode` on existing consultation documents, setting it to `rag` for all documents that lack the field.
3. THE migration SHALL use MongoDB `update_many` with a filter for documents missing the target field, so that re-running the migration on already-migrated documents produces no changes (idempotent).
4. IF the migration fails, THEN THE application SHALL log the error and continue startup without blocking.

### Requirement 11: Documentation Update

**Priority:** Low

**User Story:** As a developer, I want the architecture documentation to reflect the diagnosis workflow fixes, so that the documentation stays accurate and onboarding is straightforward.

#### Acceptance Criteria

1. THE `docs/rag-chat-workflow.md` file SHALL be updated to include a diagram showing the three diagnosis paths (RAG, MCP, AgentPipeline) and the `DIAGNOSIS_MODE` routing logic.
2. THE `docs/rag-chat-workflow.md` file SHALL document the LLM URL priority order (`MODEL_CONTAINER_URL` > `LLM_PRIMARY_URL`) and the correct default values.
3. THE `.env.example` file SHALL document all new and modified environment variables (`DIAGNOSIS_MODE`, `MODEL_CONTAINER_URL`, `MONGODB_URI`, `REDIS_URL`, `LLM_FALLBACK_API_KEY`) with descriptive comments.
4. THE `README.md` file SHALL include a section on required environment configuration for MongoDB authentication, Redis authentication, and LLM endpoint setup.

## Non-Functional Requirements

### NFR-1: Latency

- THE RAG diagnosis path SHALL respond within `LLM_TIMEOUT` seconds (default 180s as configured in `.env`) under normal conditions, excluding circuit-breaker fallback time.
- THE MCP diagnosis path SHALL respond within the configured `AGENT_TIMEOUT` (default 120 seconds) plus 10 seconds for synthesis.
- THE Agent_Pipeline path SHALL respond within `LLM_TIMEOUT × number_of_agents` seconds in the worst case (sequential fallback), or `LLM_TIMEOUT` seconds in the best case (parallel execution).

### NFR-2: Backward Compatibility

- Changing `MODEL_CONTAINER_URL` default to empty string SHALL NOT break existing Docker Compose deployments that explicitly set the variable in their `.env` file.
- THE `DIAGNOSIS_MODE` default of `rag` SHALL preserve existing behavior for all deployments that do not set the variable.
- ALL existing API response schemas SHALL remain unchanged; new fields (`diagnosis_mode`, `degraded_warning`) SHALL be additive only.

### NFR-3: Testing Strategy

- Requirements 1, 5, 8, 9 SHALL have property-based tests (Hypothesis) validating the correctness properties stated in their acceptance criteria.
- Requirements 2, 3, 7 SHALL have unit tests verifying configuration parsing and fallback behavior.
- Requirements 1, 6 SHALL have integration tests verifying end-to-end behavior through the `/api/v1/diagnose/symptoms` endpoint.
