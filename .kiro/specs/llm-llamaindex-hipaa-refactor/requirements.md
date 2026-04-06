# Requirements Document

## Introduction

Major refactoring of the Diagno-Pilot LLM integration, RAG pipeline, and compliance layer. This feature replaces the custom chunker and direct HTTP-based LLM calls with a containerized local model served via Docker, a LlamaIndex-powered RAG pipeline with semantic chunking and advanced indexing, and HIPAA/BAA-compliant controls across the multi-agent architecture. The MCP Protocol structure for agents will be provided separately and is out of scope for this document.

## Glossary

- **Model_Container**: Docker container running llama.cpp server exposing an OpenAI-compatible API, serving the MedicalQwen3-Reasoning-4B.Q8_0.gguf model from the `model/` directory
- **LlamaIndex_Pipeline**: The LlamaIndex-based RAG pipeline replacing the current custom chunker, embedding service, and retrieval logic
- **Semantic_Chunker**: LlamaIndex SemanticSplitterNodeParser that splits documents based on embedding similarity between sentences rather than fixed character counts
- **Index_Manager**: Component responsible for creating, persisting, and refreshing LlamaIndex vector store indices backed by MongoDB Atlas
- **Source_Loader**: LlamaIndex document loaders specialized per file format (PDF, DOCX, TXT, CSV, HTML) with metadata extraction
- **PHI**: Protected Health Information as defined by HIPAA — includes patient names, dates of birth, medical record numbers, diagnoses, prescriptions, and any data in PatientProfile
- **PHI_Classifier**: Service that tags data fields and document chunks as PHI or non-PHI for encryption and access control decisions
- **Encryption_Service**: Service providing AES-256 encryption at rest for PHI fields in MongoDB and S3, plus TLS 1.2+ in transit
- **Audit_Logger**: Enhanced audit service that records all PHI access, modification, and disclosure events with immutable, tamper-evident logs
- **BAA_Controller**: Component enforcing Business Associate Agreement controls — ensuring third-party LLM calls (GPT-5 fallback) transmit zero PHI
- **LLM_Router**: Existing routing component (LLMRouter) refactored to route to Model_Container as primary and GPT-5 as fallback, with PHI-stripping on fallback path
- **Agent_Pipeline**: The multi-agent diagnostic pipeline (symptomatology, epidemiology, lab, synthesis, treatment) refactored to use LlamaIndex query engines with HIPAA controls
- **Frontend_App**: The Next.js 15 / React 19 web application (apps/web) using Tailwind CSS and next-intl, comprising the Documents page, Chat page, Diagnose page, and the shared API client (@diagno-pilot/api-client)
- **Legacy_Files**: Backend modules superseded by the LlamaIndex_Pipeline refactoring: `backend/services/chunker.py`, `backend/services/rag_service.py`, `backend/services/embedding_service.py`, `backend/agents/_base_agent.py` (FilteredRAGService and subprocess run_agent), and individual agent scripts using the subprocess stdin/stdout pattern

## Requirements

### Requirement 1: Containerized Local LLM Serving

**User Story:** As a developer, I want the local LLM model to run in a Docker container with an OpenAI-compatible API, so that local development and deployment use the same reproducible serving infrastructure.

#### Acceptance Criteria

1. THE Model_Container SHALL expose an OpenAI-compatible `/v1/chat/completions` endpoint on a configurable port
2. THE Model_Container SHALL load the GGUF model file from a volume-mounted `model/` directory at startup
3. THE Model_Container SHALL expose an OpenAI-compatible `/v1/embeddings` endpoint for local embedding generation
4. WHEN the Model_Container starts, THE Model_Container SHALL perform a health check confirming the model is loaded and ready to serve requests
5. THE docker-compose.yml SHALL define a `model` service with GPU passthrough configuration (nvidia runtime) and a CPU-only fallback profile
6. WHEN the Model_Container is unhealthy or unavailable, THE LLM_Router SHALL route requests to the GPT-5 fallback endpoint via the existing circuit breaker pattern
7. THE Model_Container SHALL accept configuration for context window size, number of GPU layers, and thread count via environment variables
8. WHILE the Model_Container is running, THE Model_Container SHALL expose a `/health` endpoint returning HTTP 200 when the model is loaded

### Requirement 2: LlamaIndex Semantic Chunking

**User Story:** As a developer, I want to replace the custom regex-based chunker with LlamaIndex semantic chunking, so that document chunks preserve semantic coherence and improve retrieval quality.

#### Acceptance Criteria

1. THE Semantic_Chunker SHALL split documents using LlamaIndex SemanticSplitterNodeParser with embedding-based sentence similarity grouping
2. THE Semantic_Chunker SHALL preserve section headers, table structures, and numbered step boundaries as node metadata
3. THE Semantic_Chunker SHALL produce chunks with a configurable maximum token count (default: 512 tokens) rather than a fixed character limit
4. WHEN a document contains tables, THE Semantic_Chunker SHALL keep table rows together within a single node when they fit within the token limit
5. WHEN a document contains clinical protocol steps, THE Semantic_Chunker SHALL preserve step numbering and grouping in chunk boundaries
6. THE Semantic_Chunker SHALL attach source metadata (document_id, source organization, section, page number, region) to each node
7. FOR ALL valid documents, chunking then reconstructing from chunk contents SHALL preserve all original text content without loss (round-trip property)

### Requirement 3: Source-Specific Document Loaders

**User Story:** As a developer, I want LlamaIndex source-specific loaders for each supported document format, so that metadata extraction and text fidelity are optimized per format.

#### Acceptance Criteria

1. THE Source_Loader SHALL use LlamaIndex PDFReader for PDF files, extracting per-page text with page number metadata
2. THE Source_Loader SHALL use LlamaIndex DocxReader for DOCX files, preserving heading hierarchy as metadata
3. THE Source_Loader SHALL use LlamaIndex CSVReader for CSV files, preserving column headers and row structure
4. THE Source_Loader SHALL use a plain text loader for TXT files with paragraph-level splitting
5. THE Source_Loader SHALL use LlamaIndex BeautifulSoupWebReader for HTML content, supporting both uploaded `.html` files and fetching from user-provided URLs, extracting main content text and preserving heading hierarchy as metadata
6. WHEN a document format is unsupported, THE Source_Loader SHALL return a descriptive error identifying the format and listing supported formats
7. THE Source_Loader SHALL extract and attach disease tags (from the existing DISEASE_KEYWORDS set) to each loaded document node
8. THE Source_Loader SHALL extract document_type (protocol, guideline, other) from the source organization name using the existing inference logic

### Requirement 4: Advanced Indexing and Retrieval with LlamaIndex

**User Story:** As a developer, I want LlamaIndex to manage vector store indexing backed by MongoDB Atlas, so that hybrid retrieval, re-ranking, and context fidelity are handled through a unified framework.

#### Acceptance Criteria

1. THE Index_Manager SHALL create and maintain a LlamaIndex VectorStoreIndex backed by MongoDB Atlas Vector Search
2. THE Index_Manager SHALL support hybrid retrieval combining vector similarity and BM25 keyword search via LlamaIndex QueryFusionRetriever
3. THE Index_Manager SHALL apply cross-encoder re-ranking (ms-marco-MiniLM-L-6-v2) as a LlamaIndex NodePostprocessor
4. THE Index_Manager SHALL enforce the existing similarity threshold (0.75) as a SimilarityPostprocessor filter
5. WHEN new documents are ingested, THE Index_Manager SHALL incrementally update the index without rebuilding from scratch
6. THE Index_Manager SHALL support region-based pre-filtering (TG, BJ, ALL) via MongoDB Atlas metadata filters
7. THE LlamaIndex_Pipeline SHALL use a RetrieverQueryEngine with the grounding system prompt enforcing document-only responses
8. THE LlamaIndex_Pipeline SHALL maintain Redis caching for embeddings (24h TTL) and RAG responses (5min TTL) consistent with current behavior

### Requirement 5: LLM Router Refactoring

**User Story:** As a developer, I want the LLM Router to use the containerized local model as primary and maintain GPT-5 as fallback, so that the routing logic integrates with both the new container and HIPAA controls.

#### Acceptance Criteria

1. THE LLM_Router SHALL route primary requests to the Model_Container OpenAI-compatible endpoint
2. THE LLM_Router SHALL maintain the existing circuit breaker pattern (5-failure threshold) and jittered exponential backoff retry for the Model_Container
3. WHEN the Model_Container circuit breaker opens, THE LLM_Router SHALL route to the GPT-5 fallback endpoint
4. WHEN routing to the GPT-5 fallback, THE BAA_Controller SHALL strip all PHI from the request payload before transmission
5. THE LLM_Router SHALL accept Model_Container connection parameters (URL, API key) via environment variables consistent with the existing LLM_PRIMARY_URL/LLM_PRIMARY_API_KEY pattern
6. THE LLM_Router SHALL record which endpoint served each request in the LLM metrics (model label, latency, success/error counts)

### Requirement 6: PHI Data Classification

**User Story:** As a developer, I want all data fields classified as PHI or non-PHI, so that encryption and access controls can be applied precisely to protected health information.

#### Acceptance Criteria

1. THE PHI_Classifier SHALL tag PatientProfile fields (name, date_of_birth, medical_record_number, allergies, diagnoses, medications) as PHI
2. THE PHI_Classifier SHALL tag diagnostic session outputs (differential diagnoses, prescriptions, consultation notes) as PHI
3. THE PHI_Classifier SHALL tag document chunks containing patient-specific annotations as PHI
4. THE PHI_Classifier SHALL tag medical knowledge base content (protocols, guidelines) without patient identifiers as non-PHI
5. WHEN new data fields are added to the schema, THE PHI_Classifier SHALL default to classifying unknown fields as PHI until explicitly reviewed

### Requirement 7: Encryption at Rest and in Transit

**User Story:** As a developer, I want PHI encrypted at rest in MongoDB and S3 and in transit across all service boundaries, so that the system meets HIPAA encryption requirements.

#### Acceptance Criteria

1. THE Encryption_Service SHALL encrypt all PHI-classified fields in MongoDB using AES-256 field-level encryption before storage
2. THE Encryption_Service SHALL encrypt all PHI-classified files in S3 using server-side encryption (SSE-S3 or SSE-KMS)
3. THE Encryption_Service SHALL enforce TLS 1.2 or higher for all inter-service communication (backend to MongoDB, backend to Redis, backend to Model_Container) in production environments
4. THE Encryption_Service SHALL manage encryption keys via a dedicated key management approach with key rotation support
5. WHEN a PHI field is read from MongoDB, THE Encryption_Service SHALL decrypt the field transparently before returning it to the application layer
6. IF encryption or decryption fails, THEN THE Encryption_Service SHALL log the failure to the Audit_Logger and return an error without exposing plaintext PHI

### Requirement 8: HIPAA-Compliant Audit Logging

**User Story:** As a developer, I want all PHI access and modifications recorded in tamper-evident audit logs, so that the system meets HIPAA audit trail requirements.

#### Acceptance Criteria

1. THE Audit_Logger SHALL record all PHI read, create, update, and delete operations with timestamp, user_id, action, resource, and IP address
2. THE Audit_Logger SHALL record all LLM requests that include PHI context, logging the request type and which endpoint was used without logging PHI content
3. THE Audit_Logger SHALL store audit records in an append-only MongoDB collection with write-once semantics (no update or delete operations permitted)
4. THE Audit_Logger SHALL maintain the existing 7-year TTL on diagnostic audit records, applied to both the existing `diagnostic_audit` and the new `hipaa_audit_logs` collections
5. WHEN an audit log write fails, THE Audit_Logger SHALL retry the write and, if retry fails, log to a local fallback file to prevent audit data loss
6. THE Audit_Logger SHALL include a cryptographic hash chain (each record includes the hash of the previous record) for tamper evidence

### Requirement 9: BAA Controls for External LLM Calls

**User Story:** As a developer, I want all external LLM calls (GPT-5 fallback) to transmit zero PHI, so that the system complies with HIPAA Business Associate Agreement requirements.

#### Acceptance Criteria

1. WHEN the LLM_Router falls back to GPT-5, THE BAA_Controller SHALL remove all PHI fields from the request context before transmission
2. THE BAA_Controller SHALL replace PHI values with generic placeholders (e.g., [PATIENT_NAME], [DOB], [MRN]) in the LLM prompt sent to external endpoints
3. THE BAA_Controller SHALL log each PHI-stripping event to the Audit_Logger with the list of field types removed (without logging actual PHI values)
4. THE BAA_Controller SHALL block the external LLM call and return an error if PHI stripping fails or cannot be verified
5. WHILE the Model_Container is available, THE BAA_Controller SHALL permit full PHI context in requests to the local model since no data leaves the infrastructure

### Requirement 10: Agent Pipeline HIPAA Integration

**User Story:** As a developer, I want the multi-agent diagnostic pipeline to enforce HIPAA controls at each agent boundary, so that PHI is protected throughout the parallel agent execution flow.

#### Acceptance Criteria

1. THE Agent_Pipeline SHALL replace subprocess-based agent communication (stdin/stdout JSON) with in-process LlamaIndex query engine calls
2. THE Agent_Pipeline SHALL pass PHI context only to agents running against the local Model_Container
3. WHEN an agent query is routed to the GPT-5 fallback, THE Agent_Pipeline SHALL apply BAA_Controller PHI stripping before the agent processes the query
4. THE Agent_Pipeline SHALL provide functionality equivalent to the current FilteredRAGService source_filter behavior through LlamaIndex metadata filters per agent
5. THE Agent_Pipeline SHALL log each agent invocation (agent type, query hash, endpoint used, duration) to the Audit_Logger
6. THE Agent_Pipeline SHALL aggregate results from parallel agent executions with confidence scores consistent with the current behavior

### Requirement 11: Configuration and Environment Management

**User Story:** As a developer, I want all new configuration parameters centralized in the existing Settings class with environment variable overrides, so that the refactored system is configurable across environments.

#### Acceptance Criteria

1. THE Settings class SHALL include Model_Container configuration: MODEL_CONTAINER_URL, MODEL_CONTAINER_API_KEY, MODEL_GPU_LAYERS, MODEL_CONTEXT_SIZE, MODEL_THREADS
2. THE Settings class SHALL include LlamaIndex configuration: LLAMAINDEX_CHUNK_SIZE, LLAMAINDEX_CHUNK_OVERLAP_TOKENS, LLAMAINDEX_SIMILARITY_THRESHOLD
3. THE Settings class SHALL include HIPAA configuration: HIPAA_ENCRYPTION_KEY_ID, HIPAA_AUDIT_HASH_CHAIN_ENABLED, HIPAA_PHI_STRIP_ON_FALLBACK
4. WHEN ENV is set to "production", THE Settings class SHALL validate that HIPAA_ENCRYPTION_KEY_ID is set and HIPAA_PHI_STRIP_ON_FALLBACK is enabled
5. THE Settings class SHALL maintain backward compatibility with all existing environment variables (LLM_PRIMARY_URL, LLM_PRIMARY_API_KEY, LLM_FALLBACK_URL, LLM_FALLBACK_API_KEY, EMBED_MODEL)

### Requirement 12: Frontend Updates

**User Story:** As a developer, I want the frontend application updated to reflect the LlamaIndex pipeline and Model_Container changes, so that the UI supports new file formats, displays the correct model information, and works with the refactored backend responses.

#### Acceptance Criteria

1. THE Frontend_App Documents page SHALL accept HTML files in addition to the existing PDF, DOCX, TXT, and CSV formats by updating the accepted formats to `.pdf,.docx,.txt,.csv,.html`
2. THE Frontend_App Chat page SHALL display RAG source citations from LlamaIndex_Pipeline responses using the existing CitationChip and CitationPopup components without requiring changes to the DocumentSource data structure
3. WHEN the Diagnose page receives a DiagnosisResponse, THE Frontend_App SHALL display the `llmUsed` field reflecting the Model_Container model name (e.g., MedicalQwen3-Reasoning-4B) served by the local container
4. THE Frontend_App API client DiagnosisResponse type SHALL include all response fields returned by the LlamaIndex_Pipeline, including `llmUsed` and `sources`, consistent with the existing optional type definitions
5. WHEN the LlamaIndex_Pipeline returns source metadata with section and page number fields, THE Frontend_App Chat page SHALL render the section and page number in the CitationChip tooltip
6. IF the backend returns an error from the LlamaIndex_Pipeline, THEN THE Frontend_App SHALL display a descriptive error message to the user without exposing internal pipeline details

### Requirement 13: Legacy Code Cleanup

**User Story:** As a developer, I want all legacy LLM integration files removed from the codebase, so that the project contains only the LlamaIndex-based implementation and avoids confusion from dead code.

#### Acceptance Criteria

1. THE Legacy_Files `backend/services/chunker.py` SHALL be removed from the codebase after the Semantic_Chunker is operational
2. THE Legacy_Files `backend/services/rag_service.py` SHALL be removed from the codebase after the LlamaIndex_Pipeline is operational
3. THE Legacy_Files `backend/services/embedding_service.py` SHALL be removed from the codebase after the LlamaIndex_Pipeline embedding integration is operational
4. THE Legacy_Files `backend/agents/_base_agent.py` FilteredRAGService class and subprocess `run_agent` function SHALL be removed after the Agent_Pipeline replaces subprocess-based agent communication
5. THE Legacy_Files individual agent scripts using the subprocess stdin/stdout pattern SHALL be removed after the Agent_Pipeline in-process query engine calls are operational
6. WHEN a Legacy_Files module is removed, THE codebase SHALL contain zero import references to the removed module
7. IF a Legacy_Files module is still imported by other code, THEN the removal SHALL be blocked until all references are migrated to the LlamaIndex_Pipeline equivalents

### Requirement 14: Data Migration

**User Story:** As a developer, I want existing document chunks re-indexed with LlamaIndex and necessary data migrated, so that the refactored pipeline operates on a consistent index without losing previously ingested content.

#### Acceptance Criteria

1. WHEN the LlamaIndex_Pipeline is operational, ALL existing `document_chunks` created by the legacy chunker SHALL be re-indexed using the Semantic_Chunker and stored as LlamaIndex nodes
2. THE migration process SHALL preserve all existing document metadata (source, region, disease_tags, document_type, evidence_level) during re-indexing
3. THE migration process SHALL re-embed all chunks using the LlamaIndex embedding integration to ensure vector consistency with the new pipeline
4. WHEN migration completes for a document, THE old chunks for that document SHALL be replaced by the new LlamaIndex nodes in the `document_chunks` collection
5. THE migration process SHALL update the `chunk_count` field on each `medical_documents` record to reflect the new chunk count after re-indexing
6. IF migration fails for a specific document, THEN the migration SHALL log the error and continue with remaining documents without blocking the entire process
7. THE migration process SHALL be executable as a one-time admin command or script, not triggered automatically on application startup

### Requirement 15: Documentation

**User Story:** As a developer, I want comprehensive documentation in French covering the API, deployment, configuration, HIPAA compliance, and architecture, so that new and existing team members can understand, deploy, and maintain the refactored system.

#### Acceptance Criteria

1. ALL Documentation SHALL be written in French as the primary language
2. THE Documentation SHALL include API reference documentation for the Model_Container endpoints (`/v1/chat/completions`, `/v1/embeddings`, `/health`), the LlamaIndex_Pipeline query interface, and the HIPAA control services (PHI_Classifier, Encryption_Service, Audit_Logger, BAA_Controller)
3. THE Documentation SHALL include Docker setup and deployment instructions covering Model_Container build, GPU passthrough configuration (nvidia runtime), CPU-only fallback profile, volume mounts for the `model/` directory, and docker-compose usage
4. THE Documentation SHALL include a configuration reference listing all Settings parameters (Model_Container, LlamaIndex, and HIPAA groups) with descriptions, types, default values, and required-in-production flags
5. THE Documentation SHALL include a HIPAA compliance guide covering PHI classification rules, AES-256 field-level encryption procedures, audit logging format and hash chain verification, BAA controls for external LLM calls, and key rotation procedures
6. THE Documentation SHALL include a developer onboarding guide covering the system architecture overview, the multi-agent diagnostic pipeline flow with LlamaIndex query engines, data flow diagrams showing PHI boundaries, and local development setup steps
7. WHEN a new Settings parameter is added, THE Documentation SHALL be updated to include the new parameter in the configuration reference before the change is merged
8. WHEN a new agent is added to the Agent_Pipeline, THE Documentation SHALL be updated to reflect the agent in the architecture overview and data flow diagrams
