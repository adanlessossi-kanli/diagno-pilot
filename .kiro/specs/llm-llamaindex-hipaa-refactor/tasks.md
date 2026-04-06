# Implementation Plan: LLM LlamaIndex HIPAA Refactor

## Overview

Incremental refactoring of Diagno-Pilot's LLM integration, RAG pipeline, and compliance layer. Each task builds on the previous, starting with infrastructure and core services, then HIPAA controls, then pipeline wiring, frontend updates, and finally legacy cleanup. Python (backend) and TypeScript (frontend).

## Tasks

- [x] 1. Configuration and Model Container setup
  - [x] 1.1 Add new Settings fields to `backend/core/config.py`
    - Add MODEL_CONTAINER_URL, MODEL_CONTAINER_API_KEY, MODEL_GPU_LAYERS, MODEL_CONTEXT_SIZE, MODEL_THREADS
    - Add LLAMAINDEX_CHUNK_SIZE, LLAMAINDEX_CHUNK_OVERLAP_TOKENS, LLAMAINDEX_SIMILARITY_THRESHOLD
    - Add HIPAA_ENCRYPTION_KEY_ID, HIPAA_AUDIT_HASH_CHAIN_ENABLED, HIPAA_PHI_STRIP_ON_FALLBACK
    - Add production validator: HIPAA_ENCRYPTION_KEY_ID required and HIPAA_PHI_STRIP_ON_FALLBACK enabled when ENV=production
    - Maintain backward compatibility with existing LLM_PRIMARY_URL, LLM_PRIMARY_API_KEY, etc.
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5_

  - [x] 1.2 Add Model_Container services to `docker-compose.yml`
    - Add `model` service (GPU profile) with ghcr.io/ggerganov/llama.cpp:server image, volume mount for `model/`, nvidia GPU passthrough, health check on `/health`
    - Add `model-cpu` service (CPU profile) with same image, LLAMA_ARG_N_GPU_LAYERS=0
    - Configure environment variables: LLAMA_ARG_MODEL, LLAMA_ARG_CTX_SIZE, LLAMA_ARG_N_GPU_LAYERS, LLAMA_ARG_THREADS, LLAMA_ARG_HOST, LLAMA_ARG_PORT
    - Add MODEL_CONTAINER_URL to backend service environment
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.7, 1.8_

  - [x] 1.3 Update `.env.example` with new environment variables
    - Add MODEL_CONTAINER_URL, MODEL_CONTAINER_API_KEY, MODEL_GPU_LAYERS, MODEL_CONTEXT_SIZE, MODEL_THREADS
    - Add LLAMAINDEX_*, HIPAA_* variables with sensible defaults
    - _Requirements: 11.1, 11.2, 11.3_

  - [x] 1.4 Write unit tests for Settings validation
    - Test production validation rejects missing HIPAA_ENCRYPTION_KEY_ID
    - Test production validation rejects HIPAA_PHI_STRIP_ON_FALLBACK=False
    - Test backward compatibility with existing env vars
    - _Requirements: 11.4, 11.5_

- [x] 2. PHI Classification and Encryption services
  - [x] 2.1 Create `backend/services/phi_classifier.py`
    - Implement PHIClassifier with PHI_FIELDS set (full_name, date_of_birth, medical_record_number, allergies, current_medications, comorbidities, weight_kg, diagnoses, prescriptions, consultation_notes, differential_diagnoses, partial_differential)
    - Implement is_phi(field_name) — returns True for known PHI, True for unknown fields
    - Implement classify_document(data), extract_phi_fields(data), extract_non_phi_fields(data)
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [x] 2.2 Write property test for PHI classification
    - **Property 8: PHI classification correctness**
    - **Validates: Requirements 6.1, 6.2, 6.5**

  - [x] 2.3 Create `backend/services/encryption_service.py`
    - Implement EncryptionService with AES-256 field-level encryption using `cryptography` library (Fernet or AES-GCM)
    - Implement encrypt_field(plaintext) → base64 ciphertext, decrypt_field(ciphertext) → plaintext
    - Implement encrypt_phi_fields(data, classifier), decrypt_phi_fields(data, classifier) using PHIClassifier
    - Implement rotate_key(new_key_id) for key rotation support
    - On failure: log to Audit_Logger, return error without exposing plaintext
    - _Requirements: 7.1, 7.4, 7.5, 7.6_

  - [x] 2.4 Write property test for encryption round-trip
    - **Property 9: Encryption round-trip**
    - **Validates: Requirements 7.1, 7.5**

  - [x] 2.5 Write property test for encryption failure safety
    - **Property 10: Encryption failure does not expose plaintext**
    - **Validates: Requirements 7.6**

- [x] 3. HIPAA Audit Logger
  - [x] 3.1 Enhance `backend/services/audit_service.py` with HIPAA-compliant logging
    - Create AuditLogger class using `hipaa_audit_logs` collection
    - Implement log_action with hash chain: SHA-256(previous_hash + json(record))
    - Implement _write_fallback to local JSONL file when MongoDB write fails
    - Implement verify_chain for tamper detection
    - Ensure append-only semantics (no update/delete on collection)
    - Maintain existing AuditService for backward compatibility
    - _Requirements: 8.1, 8.2, 8.3, 8.5, 8.6_

  - [x] 3.2 Create `backend/models/audit.py` with HIPAAAuditRecord Pydantic model
    - Fields: id, timestamp, user_id, action, resource, resource_id, details, ip_address, previous_hash, record_hash
    - _Requirements: 8.1_

  - [x] 3.3 Write property test for audit record completeness
    - **Property 12: Audit record completeness**
    - **Validates: Requirements 8.1**

  - [x] 3.4 Write property test for audit hash chain integrity
    - **Property 13: Audit hash chain integrity**
    - **Validates: Requirements 8.6**

  - [x] 3.5 Write property test for audit PHI exclusion
    - **Property 14: Audit records exclude PHI values**
    - **Validates: Requirements 8.2, 9.3**

- [x] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. BAA Controller and LLM Router refactoring
  - [x] 5.1 Create `backend/services/baa_controller.py`
    - Implement BAAController with PHI_PLACEHOLDERS mapping
    - Implement strip_phi(context, classifier) — replace PHI values with placeholders
    - Implement verify_no_phi(context, classifier) — raise if PHI detected
    - Log each PHI-stripping event to AuditLogger (field types only, no PHI values)
    - Block external call and return error if stripping fails
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

  - [x] 5.2 Write property test for BAA PHI stripping
    - **Property 11: BAA PHI stripping with placeholder substitution**
    - **Validates: Requirements 5.4, 9.1, 9.2**

  - [x] 5.3 Refactor `backend/services/llm_router.py`
    - Update PRIMARY_MODEL to "MedicalQwen3-Reasoning-4B"
    - Default primary URL to MODEL_CONTAINER_URL from settings
    - Integrate BAA_Controller.strip_phi() before fallback to GPT-5
    - Maintain existing circuit breaker and retry logic
    - Record endpoint label in LLM metrics
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [x] 5.4 Write unit tests for LLM Router fallback with PHI stripping
    - Test primary routing to Model_Container
    - Test fallback triggers BAA PHI stripping
    - Test circuit breaker opens after 5 failures
    - _Requirements: 5.2, 5.3, 5.4_

- [x] 6. Source Loaders and Semantic Chunker
  - [x] 6.1 Create `backend/services/source_loaders.py`
    - Implement SourceLoaderService with SUPPORTED_FORMATS = {pdf, docx, csv, txt, html}
    - Implement load(content, filename, source, region) dispatching to format-specific LlamaIndex readers
    - Implement _load_pdf (PDFReader), _load_docx (DocxReader), _load_csv (CSVReader), _load_txt (plain text), _load_html (BeautifulSoupWebReader — supports both uploaded `.html` files and fetching from user-provided URLs)
    - Implement _attach_disease_tags using existing DISEASE_KEYWORDS
    - Implement _infer_document_type reusing existing logic from document_service.py
    - Return descriptive error for unsupported formats
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8_

  - [x] 6.2 Write property test for source loader metadata extraction
    - **Property 4: Source loader metadata extraction**
    - **Validates: Requirements 3.7, 3.8**

  - [x] 6.3 Write property test for unsupported format error
    - **Property 5: Unsupported format error message**
    - **Validates: Requirements 3.6**

  - [x] 6.4 Create `backend/services/semantic_chunker.py`
    - Implement SemanticChunkerService using LlamaIndex SemanticSplitterNodeParser
    - Constructor takes embed_model and max_tokens (default 512)
    - Implement chunk(documents) → list[TextNode] with semantic splitting
    - Implement _preserve_table_boundaries and _preserve_step_numbering post-processors
    - Attach source metadata (document_id, source, section, page, region) to each node
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

  - [x] 6.5 Write property test for chunking round-trip
    - **Property 1: Chunking round-trip preserves text content**
    - **Validates: Requirements 2.7**

  - [x] 6.6 Write property test for chunk token limit
    - **Property 2: Chunk token limit invariant**
    - **Validates: Requirements 2.3**

  - [x] 6.7 Write property test for chunk metadata preservation
    - **Property 3: Chunk metadata preservation**
    - **Validates: Requirements 2.2, 2.6**

- [x] 7. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Index Manager and LlamaIndex Pipeline
  - [x] 8.1 Create `backend/services/index_manager.py`
    - Implement IndexManager with MongoDB Atlas Vector Store backend
    - Implement get_or_create_index() returning VectorStoreIndex
    - Implement insert_nodes(nodes) for incremental index updates
    - Implement get_retriever(top_k, region) returning QueryFusionRetriever (vector + BM25 hybrid)
    - Implement get_postprocessors() returning [SimilarityPostprocessor(0.75), CrossEncoderReranker]
    - Support region-based pre-filtering via MongoDB Atlas metadata filters
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

  - [x] 8.2 Write property test for similarity threshold filter
    - **Property 6: Similarity threshold filter**
    - **Validates: Requirements 4.4**

  - [x] 8.3 Write property test for region filter correctness
    - **Property 7: Region filter correctness**
    - **Validates: Requirements 4.6**

  - [x] 8.4 Create `backend/services/llamaindex_pipeline.py`
    - Implement LlamaIndexPipeline with IndexManager, LLMRouter, and cache_service dependencies
    - Implement query(question, context, top_k, region, source_filter, session_history) → RAGResponse
    - Use RetrieverQueryEngine with grounding system prompt
    - Maintain Redis caching: embeddings 24h TTL, RAG responses 5min TTL
    - _Requirements: 4.7, 4.8_

  - [x] 8.5 Create/update `backend/models/document.py` with ChunkNode and ChunkMetadata models
    - Add ChunkNode(id, document_id, content, embedding, metadata) Pydantic model
    - Add ChunkMetadata(source, page, section, region, disease_tags, document_type, evidence_level, bbox, page_char_start, page_char_end, title)
    - _Requirements: 2.6, 3.7_

- [x] 9. Agent Pipeline refactoring
  - [x] 9.1 Create `backend/services/agent_pipeline.py`
    - Implement AgentPipeline with AGENTS config (symptomatology, epidemiology, lab, synthesis, treatment) and their source_filters
    - Implement run(symptoms, patient_profile, region) → DiagnosticResponse with parallel agent execution
    - Implement _run_agent(agent_name, sub_question, patient_profile, region) using LlamaIndex query engine
    - Enforce PHI boundary: full PHI to local Model_Container, BAA stripping for GPT-5 fallback
    - Log each agent invocation to AuditLogger (agent type, query hash, endpoint, duration)
    - Aggregate results with confidence scores (arithmetic mean)
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6_

  - [x] 9.2 Write property test for agent PHI boundary enforcement
    - **Property 15: Agent PHI boundary enforcement**
    - **Validates: Requirements 10.2, 10.3**

  - [x] 9.3 Write property test for agent result aggregation
    - **Property 16: Agent result aggregation preserves confidence scores**
    - **Validates: Requirements 10.6**

- [x] 10. Wire pipeline into existing backend
  - [x] 10.1 Update `backend/services/document_service.py` to use new pipeline
    - Replace `from backend.services.chunker import Chunker, ChunkResult` with SemanticChunkerService
    - Replace `from backend.services.embedding_service import EmbeddingModel` with LlamaIndex embedding via IndexManager
    - Update ingest() to use SourceLoaderService → SemanticChunkerService → IndexManager.insert_nodes()
    - Apply EncryptionService.encrypt_phi_fields() on patient-annotated chunks before storage
    - _Requirements: 2.1, 3.1, 4.5, 7.1_

  - [x] 10.2 Update `backend/services/diagnostic_service.py` to use AgentPipeline
    - Replace subprocess agent calls with AgentPipeline.run()
    - Wire AuditLogger for diagnostic session logging
    - _Requirements: 10.1, 10.5_

  - [x] 10.3 Wire LlamaIndex_Pipeline into chat and RAG endpoints
    - Replace RAGService usage with LlamaIndexPipeline in chat endpoint handlers
    - Ensure response shape matches existing RAGResponse model
    - _Requirements: 4.7, 4.8_

- [x] 11. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 12. Frontend updates
  - [x] 12.1 Update Documents page to accept HTML format
    - In `apps/web/src/app/[locale]/documents/page.tsx`, change ACCEPTED_FORMATS to `.pdf,.docx,.txt,.csv,.html`
    - _Requirements: 12.1_

  - [x] 12.2 Write frontend test for HTML format acceptance
    - **Property 17: Frontend accepted formats include HTML**
    - **Validates: Requirements 12.1**

  - [x] 12.3 Update Chat page CitationChip for LlamaIndex metadata
    - Enhance CitationChip tooltip to show `section` and `page` from LlamaIndex node metadata when available
    - _Requirements: 12.2, 12.5_

  - [x] 12.4 Verify API client type compatibility
    - Confirm DiagnosisResponse.llmUsed and DiagnosisResponse.sources optional fields work with new model name
    - Confirm DocumentSourceSchema Zod validation accepts section and page fields
    - No breaking changes expected — verify and adjust if needed
    - _Requirements: 12.3, 12.4, 12.6_

- [x] 13. Legacy code cleanup
  - [x] 13.1 Remove individual agent subprocess scripts
    - Delete `backend/agents/symptomatology.py`, `backend/agents/epidemiology.py`, `backend/agents/lab.py`, `backend/agents/synthesis.py`, `backend/agents/treatment.py`
    - Verify zero import references before each deletion
    - _Requirements: 13.5, 13.6, 13.7_

  - [x] 13.2 Remove `backend/agents/_base_agent.py`
    - Verify zero import references to FilteredRAGService and run_agent
    - _Requirements: 13.4, 13.6, 13.7_

  - [x] 13.3 Remove `backend/services/rag_service.py`
    - Verify zero import references
    - _Requirements: 13.2, 13.6, 13.7_

  - [x] 13.4 Remove `backend/services/embedding_service.py`
    - Verify zero import references
    - _Requirements: 13.3, 13.6, 13.7_

  - [x] 13.5 Remove `backend/services/chunker.py`
    - Verify zero import references
    - _Requirements: 13.1, 13.6, 13.7_

  - [x] 13.6 Write legacy module zero-reference verification test
    - **Property 18: Legacy module zero-reference invariant**
    - **Validates: Requirements 13.6**

- [x] 14. Data migration
  - [x] 14.1 Create migration script/service for re-indexing existing chunks
    - Create `scripts/migrate_chunks.py` or `backend/services/migration_service.py`
    - Implement ChunkMigrationService: iterate medical_documents → fetch from S3 → load via SourceLoaderService → chunk via SemanticChunkerService → insert via IndexManager → delete old chunks → update chunk_count
    - Log success/failure per document; continue on failure
    - Expose as admin endpoint (`POST /api/v1/admin/migrate-chunks`) or CLI command
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 14.7_

- [x] 15. Documentation (in French)
  - [x] 15.1 Create `docs/api-reference.md` in French
    - Document Model_Container endpoints, LlamaIndex_Pipeline query interface, HIPAA control services
    - _Requirements: 15.1, 15.2_

  - [x] 15.2 Create `docs/deployment.md` in French
    - Docker setup, GPU passthrough, CPU fallback, volume mounts, docker-compose usage
    - _Requirements: 15.1, 15.3_

  - [x] 15.3 Create `docs/configuration.md` in French
    - All Settings parameters with descriptions, types, defaults, required-in-production flags
    - _Requirements: 15.1, 15.4, 15.7_

  - [x] 15.4 Create `docs/hipaa-compliance.md` in French
    - PHI classification rules, AES-256 encryption, audit logging format, hash chain verification, BAA controls, key rotation
    - _Requirements: 15.1, 15.5_

  - [x] 15.5 Create `docs/developer-guide.md` in French
    - Architecture overview, agent pipeline flow, PHI boundary data flow diagrams, local dev setup
    - _Requirements: 15.1, 15.6, 15.8_

- [x] 16. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- Legacy cleanup follows dependency-safe removal order (leaf modules first)
- Documentation is written in French per Requirement 15.1
