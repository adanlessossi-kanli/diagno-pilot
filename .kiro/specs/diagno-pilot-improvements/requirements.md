# Requirements Document

## Introduction

This document specifies a comprehensive set of improvements to Diagno-Pilot, a tropical disease medical diagnosis tool. The improvements span five areas: strict document grounding to prevent hallucination, a multi-agent diagnostic system via MCP, tropical disease-specific RAG pipeline enhancements, safety and audit infrastructure, and a PDF citation popup with inline highlight. The system serves clinicians in West Africa (Togo, Benin) and must remain grounded in ingested medical protocols from sources such as PNLP, CHU Lomé, CHU Abomey-Calavi, MSF, and WHO AFRO.

---

## Glossary

- **RAGService**: The retrieval-augmented generation service that embeds queries, performs hybrid retrieval over document chunks, re-ranks results with a CrossEncoder, applies a similarity threshold guard, and calls the LLMRouter to produce grounded answers.
- **DocumentChunk**: A single indexed passage stored in the `document_chunks` MongoDB collection, including its embedding vector and enriched metadata (disease_tags, document_type, evidence_level, bbox, page_char_start, page_char_end, region).
- **DocumentSource**: The Pydantic model returned to callers identifying the source of a retrieved chunk (document_id, title, source organisation, section, page, excerpt, highlight, confidence_score).
- **LLMRouter**: The service that routes generation requests to MedicalQwen3-Reasoning-14B (primary) with GPT-5 as fallback.
- **DiagnosticOrchestrator**: The orchestrator service (aliased as `DiagnosticService`) that delegates to MCP_Host for multi-agent differential diagnosis and writes a DiagnosticAudit record for every request.
- **MCP_Host**: The Model Context Protocol host process that acts as the multi-agent orchestrator, coordinating four specialist sub-agents in parallel and passing their results to the Synthesis_Agent.
- **Epidemiology_Agent**: A specialist sub-agent responsible for endemic zones, outbreak data, and seasonal patterns.
- **Symptomatology_Agent**: A specialist sub-agent responsible for symptom clusters and pathognomonic signs.
- **Lab_Agent**: A specialist sub-agent responsible for interpreting RDT, microscopy, and PCR results.
- **Treatment_Agent**: A specialist sub-agent responsible for WHO/MSF/PNLP protocols and drug interactions.
- **Synthesis_Agent**: A specialist sub-agent that merges ranked differentials with evidence citations from all other agents into a single DiagnosticResult.
- **BM25_Retriever**: A sparse keyword retrieval component implementing the BM25 ranking function over the `document_chunks` collection.
- **CrossEncoder**: A re-ranking model that scores (query, chunk) pairs to reorder the merged candidate set after initial hybrid retrieval.
- **Chunker**: The component responsible for splitting extracted document text into semantically coherent passages aligned to section headers, numbered steps, and table boundaries.
- **DiagnosticAudit**: A MongoDB document in the `diagnostic_audit` collection recording a single diagnostic request with its inputs, outputs, confidence score, and agent traces.
- **RetrievalFeedback**: A MongoDB document in the `retrieval_feedback` collection recording a clinician's rating of a retrieved source.
- **ConfidenceScore**: The arithmetic mean of the cosine similarity scores of the retained chunks for a given RAG query, expressed as a float in [0.0, 1.0].
- **CitationChip**: An inline UI element (e.g. `[1]`, `[2]`) rendered in the answer text that, when clicked, opens the CitationPopup.
- **CitationPopup**: A frontend drawer or modal that renders the source PDF page with a yellow highlight overlay over the cited passage.
- **BBox**: A bounding box `[x0, y0, x1, y1]` in PDF user-space coordinates identifying the position of a text span on a page.
- **LocaleMiddleware**: The Starlette middleware that resolves `Accept-Language` to `(locale, region)` and stores the result in `request.state`.
- **PNLP**: Programme National de Lutte contre le Paludisme — the national malaria-control programme.
- **CHU**: Centre Hospitalier Universitaire — teaching hospital (Lomé for Togo, Abomey-Calavi for Benin).
- **SIMILARITY_THRESHOLD**: The minimum cosine similarity score (0.75) below which a retrieved chunk is discarded before being passed to the LLM.
- **NO_CONTEXT_MESSAGE**: The fixed French refusal string `"Information non disponible dans la base de connaissances."` returned as the `answer` field when RAGService has no grounded chunks to pass to the LLM.
- **grounding_warning**: A fixed message included in the RAGResponse when keyword fallback is active, indicating that results are based on keyword retrieval only and may not be fully grounded in validated protocols.

---

## Requirements

### Requirement 1: Strict Document Grounding

**User Story:** As a clinician, I want the assistant to answer only from ingested medical documents, so that I can trust that every response is grounded in validated protocols and not in the LLM's parametric knowledge.

#### Acceptance Criteria

1. THE RAGService SHALL include a grounding system prompt in every LLM context that instructs the LLM to answer exclusively from the provided document passages and to refuse to answer if no relevant passage is available.
2. WHEN RAGService retrieves zero chunks after applying the SIMILARITY_THRESHOLD filter, THE RAGService SHALL return a structured refusal response without calling the LLMRouter, with `answer` set to the NO_CONTEXT_MESSAGE constant (`"Information non disponible dans la base de connaissances."`) and `sources` set to an empty list.
3. WHEN RAGService retrieves chunks from the vector index, THE RAGService SHALL discard any chunk whose cosine similarity score is below SIMILARITY_THRESHOLD (0.75); IF no chunks remain after filtering, THE RAGService SHALL return the structured refusal response defined in criterion 2.
4. THE DocumentSource model SHALL expose a `title` field populated from the document's stored title and a `source` field populated from the document's stored source organisation, and THE RAGService SHALL populate these two fields independently from their respective metadata values.
5. WHEN RAGService returns a response with `degraded_warning` set (keyword fallback active), THE RAGResponse SHALL include a `grounding_warning` field set to a fixed message indicating that results are based on keyword retrieval only and may not be fully grounded in validated protocols.

---

### Requirement 2: Multi-Agent Diagnostic System via MCP

**User Story:** As a clinician, I want the diagnostic pipeline to use specialist agents for epidemiology, symptomatology, lab interpretation, and treatment, so that each dimension of the differential diagnosis is grounded in the most relevant document subset.

#### Acceptance Criteria

1. THE MCP_Host SHALL coordinate four specialist sub-agents — Epidemiology_Agent, Symptomatology_Agent, Lab_Agent, and Treatment_Agent — in parallel for each diagnostic request.
2. WHEN the MCP_Host dispatches a sub-agent, THE MCP_Host SHALL pass a focused sub-question and a `source_filter` scoped to the relevant document types for that agent.
3. THE Epidemiology_Agent SHALL call RAGService.query() with a sub-question focused on endemic zones, outbreak data, and seasonal patterns, and with `source_filter` set to epidemiology documents.
4. THE Symptomatology_Agent SHALL call RAGService.query() with a sub-question focused on symptom clusters and pathognomonic signs, and with `source_filter` set to clinical guidelines.
5. THE Lab_Agent SHALL call RAGService.query() with a sub-question focused on RDT, microscopy, and PCR interpretation, and with `source_filter` set to laboratory protocol documents.
6. THE Treatment_Agent SHALL call RAGService.query() with a sub-question focused on WHO/MSF/PNLP treatment protocols and drug interactions, and with `source_filter` set to treatment protocol documents.
7. THE Synthesis_Agent SHALL merge the ranked differentials and evidence citations returned by all four specialist agents into a single DiagnosticResult containing a minimum of 3 differential diagnoses; WHEN fewer than 3 diagnoses are produced by the agents, THE Synthesis_Agent SHALL add placeholder entries marked with `confidence: low` to reach the minimum.
8. THE DiagnosticOrchestrator SHALL delegate to the MCP_Host for every call to `get_differential_diagnosis`, preserving the existing `get_differential_diagnosis` interface for callers.
9. WHEN a specialist sub-agent returns zero grounded chunks, THE Synthesis_Agent SHALL exclude that agent's contribution from the merged result and record the omission in the DiagnosticAudit.
10. THE MCP_Host SHALL communicate with sub-agents using the MCP stdio transport protocol; each sub-agent SHALL be a separate process exposing MCP tools over stdin/stdout.
11. THE `source_filter` passed by MCP_Host to each sub-agent SHALL be implemented as a `metadata.document_type` filter applied as a MongoDB pre-filter on the `document_chunks` collection before vector search.
12. THE MCP_Host SHALL enforce a per-agent timeout of 30 seconds; WHEN a sub-agent exceeds this timeout, THE MCP_Host SHALL treat it as returning zero grounded chunks and record the timeout in the DiagnosticAudit.
13. THE MCP_Host SHALL not require authentication between host and sub-agents when all processes run within the same trusted deployment boundary (localhost/container network); inter-agent communication SHALL be isolated from external network access.

---

### Requirement 3: Tropical Disease-Specific RAG Improvements

**User Story:** As a clinician, I want the RAG pipeline to use semantically coherent chunks, enriched metadata, and hybrid retrieval, so that retrieved passages are more relevant to tropical disease queries.

#### Acceptance Criteria

1. THE Chunker SHALL detect section boundaries using the following rules in order: (1) lines matching the regex `^(\d+\.|\#{1,3}|\*{1,2})[^\n]+` as section headers; (2) lines matching `^(\d+[\.\)])\s` as numbered steps; (3) lines containing pipe characters (`|`) as table rows, grouping consecutive table rows into a single chunk. Chunks SHALL have a maximum of 800 characters; text not matching any boundary rule SHALL be split at sentence boundaries up to the 800-character limit.
2. WHEN the Chunker produces a chunk, THE Chunker SHALL preserve the section header or table caption as the chunk's `metadata.section` field.
3. THE DocumentService SHALL enrich each DocumentChunk at ingestion time with `metadata.disease_tags` detected using a curated keyword list of tropical disease names (malaria/paludisme, typhoid/typhoïde, dengue, cholera/choléra, tuberculosis/tuberculose, HIV/VIH, schistosomiasis/bilharziose, trypanosomiasis/trypanosomiase, yellow fever/fièvre jaune, meningitis/méningite); `metadata.document_type` inferred from the document `source` field (sources containing "PNLP" → `protocol`; "CHU" → `guideline`; "MSF" → `protocol`; "OMS" or "WHO" → `guideline`; otherwise → `other`); and `metadata.evidence_level` mirroring the `document_type` source mapping.
4. THE RAGService SHALL perform hybrid retrieval by combining vector search results with BM25_Retriever results before re-ranking.
5. WHEN RAGService performs hybrid retrieval, THE RAGService SHALL merge vector search and BM25 result sets using Reciprocal Rank Fusion before passing them to the CrossEncoder.
6. THE CrossEncoder SHALL use the `cross-encoder/ms-marco-MiniLM-L-6-v2` model running locally; THE DocumentService SHALL load this model at application startup and expose it as a singleton.
7. WHEN ChatService calls RAGService.query(), THE ChatService SHALL include the last 5 messages (user and assistant turns combined, i.e. up to 2.5 exchanges) from the session history as additional context.
8. WHEN the chat router receives a request, THE chat router SHALL read `request.state.region` set by LocaleMiddleware and pass it to RAGService.query() as the `region` parameter.
9. WHEN `region` is `None`, empty, or an unrecognised value, THE RAGService SHALL apply no region pre-filter and return results from all documents.

---

### Requirement 4: Safety and Audit

**User Story:** As a medical administrator, I want every diagnostic request to be logged with its confidence score, retrieved chunks, and agent traces, so that I can audit the system's reasoning and identify low-confidence responses for clinical review.

#### Acceptance Criteria

1. THE RAGService SHALL compute a ConfidenceScore for every query as the arithmetic mean of the cosine similarity scores of the retained chunks, and SHALL include it in the RAGResponse as `confidence_score`.
2. WHEN RAGService returns a response with `fallback_used=True`, THE ChatService and DiagnosticOrchestrator SHALL include a disclaimer in the response indicating that the answer was generated by the fallback model and requires clinical verification.
3. THE DiagnosticOrchestrator SHALL write a DiagnosticAudit document to the `diagnostic_audit` MongoDB collection for every call to `get_differential_diagnosis`, containing: request timestamp, symptoms, patient profile hash, locale, region, ConfidenceScore, diagnoses, fallback_used, degraded_warning, and agent_results from each sub-agent. The patient profile hash SHALL be computed as SHA-256 over the JSON serialisation of the PatientProfile fields `age`, `weight`, `sex`, and `comorbidities` only; PII fields (name, identifiers) SHALL NOT be included in the hash input.
4. THE DiagnosticAudit document SHALL store `agent_results` as a list of objects, each containing: agent name, sub-question, retrieved chunk IDs, ConfidenceScore, and the agent's partial differential.
5. THE DocumentChunk stored in MongoDB SHALL include `metadata.disease_tags`, `metadata.document_type`, and `metadata.evidence_level` fields as defined in Requirement 3, criterion 3.
6. THE system SHALL expose a `POST /api/v1/feedback/retrieval` endpoint accessible to users with roles `admin`, `medecin`, and `infirmière` for submitting retrieval feedback; the request body SHALL contain: `session_id`, `document_id`, `chunk_id`, and `rating` (value: `1` or `-1`).
7. WHEN a clinician submits retrieval feedback, THE system SHALL store: session_id, user_id, document_id, chunk_id, rating (1 or -1), and timestamp in the `retrieval_feedback` collection.
8. THE `diagnostic_audit` collection SHALL have a TTL index of 2555 days (7 years) on the `timestamp` field, in compliance with clinical record retention requirements.
9. THE `diagnostic_audit` collection SHALL be readable only by users with the `admin` role; medecin and infirmière roles SHALL NOT have read access to audit records.

---

### Requirement 5: PDF Citation Popup with Highlight

**User Story:** As a clinician, I want to click on a citation chip in the answer text and see the exact passage highlighted in the source PDF, so that I can verify the evidence directly without leaving the application.

#### Acceptance Criteria

1. WHEN DocumentService ingests a PDF file, THE DocumentService SHALL extract the BBox and character offsets for each chunk using pypdf and store `metadata.bbox` (list of `[x0, y0, x1, y1]` floats), `metadata.page_char_start` (int), and `metadata.page_char_end` (int) on the DocumentChunk.
2. THE DocumentSource model SHALL include an optional `highlight` field of type `{bbox: list[float], page: int}` populated from the chunk's stored `metadata.bbox` and `metadata.page` when available.
3. THE `GET /api/v1/documents/{id}/view` endpoint SHALL be accessible to users with roles `admin`, `medecin`, and `infirmière`, and SHALL return a presigned S3 URL valid for 15 minutes for the document's stored S3 object.
4. WHEN a user requests `GET /api/v1/documents/{id}/view` for a document that does not exist, THE documents router SHALL return HTTP 404.
5. THE frontend SHALL render CitationChips inline in the answer text using the pattern `[N]` where N is the 1-based index of the source in the `sources` list.
6. WHEN a user clicks a CitationChip, THE frontend SHALL open a CitationPopup that fetches the presigned S3 URL, renders the source PDF page, and overlays a yellow highlight rectangle at the position specified by the `highlight.bbox` field of the corresponding DocumentSource.
7. WHEN a DocumentSource has no `highlight` field, THE CitationPopup SHALL display the `excerpt` text only without attempting to render a PDF page.
8. WHEN DocumentService ingests a non-PDF file (DOCX, TXT, CSV), THE DocumentSource for chunks from that document SHALL have no `highlight` field, and THE CitationPopup SHALL display the `excerpt` text only without attempting to render a PDF page.
9. THE CitationPopup SHALL be accessible as a drawer or modal and SHALL be closable by pressing Escape or clicking outside the popup area.

---

### Requirement 6: Data Integrity and Migration

**User Story:** As a system administrator, I want the system to handle mixed-state document chunks and maintain referential integrity across collections, so that the deployment of new features does not break existing data or audit trails.

#### Acceptance Criteria

1. WHEN the system starts up, THE DocumentService SHALL detect `document_chunks` records that lack `metadata.disease_tags`, `metadata.document_type`, or `metadata.evidence_level` fields and SHALL log a warning with the count of unmigrated chunks; a background migration task SHALL NOT be run automatically at startup.
2. THE system SHALL expose an admin-only `POST /api/v1/admin/migrate-chunks` endpoint that triggers a background re-enrichment of all `document_chunks` lacking the new metadata fields, processing chunks in batches of 100.
3. THE system SHALL expose an admin-only `POST /api/v1/admin/reindex-document/{id}` endpoint that re-ingests a document from its stored S3 key using the new semantic Chunker and pypdf bbox extraction, deletes all existing `document_chunks` for that document, inserts the newly produced chunks, and updates the `chunk_count` on the `medical_documents` record.
4. WHEN `POST /api/v1/admin/reindex-document/{id}` is called for a PDF document, THE DocumentService SHALL extract BBox and character offsets for each new chunk as defined in Requirement 5, criterion 1.
5. WHEN `POST /api/v1/admin/reindex-document/{id}` is called for a non-PDF document (DOCX, TXT, CSV), THE DocumentService SHALL apply the new semantic Chunker and metadata enrichment only; no bbox extraction SHALL be attempted.
6. WHEN a document is deleted via `DELETE /api/v1/documents/{id}`, THE system SHALL retain any `diagnostic_audit` records that reference chunks from that document; the `chunk_id` references in those audit records SHALL remain as tombstone references and SHALL NOT be deleted.
7. THE end-to-end latency from user query submission to first response token SHALL not exceed 15 seconds at the 95th percentile under normal operating conditions (both LLMs available, Redis available, MongoDB available).
8. THE multi-agent diagnostic pipeline SHALL complete within 45 seconds at the 95th percentile; this budget includes all four specialist agent calls (each capped at 30s) plus Synthesis_Agent processing.

---

### Requirement 7: Implementation Documentation

**User Story:** As a developer or clinical engineer onboarding to the project, I want up-to-date documentation of the new implementation including architecture diagrams, so that I can understand the system's data flows and component interactions without reading the source code.

#### Acceptance Criteria

1. THE project SHALL include a documentation file at `docs/architecture.md` that describes the complete new implementation across all six requirement areas (document grounding, multi-agent MCP, RAG pipeline, safety & audit, PDF citation popup, data integrity).
2. THE `docs/architecture.md` file SHALL contain a Mermaid flowchart diagram of the document ingestion pipeline, covering: file upload → text extraction → semantic chunking → metadata enrichment → embedding → S3 upload → MongoDB storage.
3. THE `docs/architecture.md` file SHALL contain a Mermaid flowchart diagram of the RAG query pipeline, covering: cache lookup → query embedding → hybrid retrieval (vector + BM25) → Reciprocal Rank Fusion → CrossEncoder re-ranking → SIMILARITY_THRESHOLD filter → grounding system prompt → LLM generation → response caching.
4. THE `docs/architecture.md` file SHALL contain a Mermaid sequence diagram of the multi-agent diagnostic flow, covering: clinician request → DiagnosticOrchestrator → MCP_Host → parallel dispatch to four specialist agents → Synthesis_Agent → DiagnosticAudit write → DiagnosticResult returned.
5. THE `docs/architecture.md` file SHALL contain a Mermaid sequence diagram of the PDF citation popup flow, covering: answer render with CitationChips → user click → presigned URL fetch → PDF page render → highlight overlay.
6. THE `docs/architecture.md` file SHALL contain a section describing the MongoDB collections schema, listing all fields for: `document_chunks`, `medical_documents`, `chat_sessions`, `diagnostic_audit`, and `retrieval_feedback`.
7. THE `docs/architecture.md` file SHALL contain a section describing the new API endpoints introduced by this implementation: `GET /api/v1/documents/{id}/view`, `POST /api/v1/feedback/retrieval`, `POST /api/v1/admin/migrate-chunks`, and `POST /api/v1/admin/reindex-document/{id}`, including method, path, required roles, request body, and response shape.
8. WHEN any of the five core services (RAGService, DocumentService, ChatService, DiagnosticOrchestrator, MCP_Host) changes its public interface, THE corresponding diagram and description in `docs/architecture.md` SHALL be updated as part of the same change.
