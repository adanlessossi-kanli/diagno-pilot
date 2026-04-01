# Requirements Document

## Introduction

This feature covers three targeted code quality and architecture improvements to the Diagno-Pilot medical application:

1. **DiagnosticService decomposition** — the current `DiagnosticService` conflates prompt engineering, LLM response parsing, and clinical validation into a single class. Splitting it into focused collaborators improves testability, replaceability, and adherence to the Single Responsibility Principle.
2. **Zod runtime validation in the shared types package** — `packages/types` currently exports TypeScript interfaces only. Adding co-located Zod schemas enables runtime validation on both the Next.js frontend and the React Native mobile app, and allows the `packages/api-client` to validate API responses at the boundary.
3. **Medical business logic docstrings on backend services** — `PrescriptionService`, `AlertService`, `DiagnosticService`, `RAGService`, and `EmbeddingModel` contain non-obvious clinical rules (mg/kg capping, organ-failure adjustments, ICD-10 validation, etc.) that are not adequately documented for future maintainers.

---

## Glossary

- **DiagnosticService**: Python class at `backend/services/diagnostic_service.py` responsible for generating differential diagnoses.
- **DiagnosticOrchestrator**: New Python class that coordinates `PromptBuilder`, `DiagnosticParser`, and `RAGService` to produce differential diagnoses.
- **PromptBuilder**: New Python class responsible solely for constructing the LLM prompt from symptoms and patient profile.
- **DiagnosticParser**: New Python class responsible solely for parsing and validating the LLM JSON response into `DifferentialDiagnosis` objects.
- **RAGService**: Existing Python class at `backend/services/rag_service.py` that performs vector retrieval and LLM generation.
- **LLMRouter**: Existing Python class at `backend/services/llm_router.py` that routes generation requests between primary and fallback LLMs.
- **PrescriptionService**: Existing Python class at `backend/services/prescription_service.py` that calculates antibiotic prescriptions.
- **AlertService**: Existing Python class at `backend/services/alert_service.py` that checks safety alerts.
- **EmbeddingModel**: Existing Python class at `backend/services/embedding_service.py` that encodes text into vectors.
- **ZodSchema**: A runtime validation schema defined using the Zod library.
- **packages/types**: Shared TypeScript package at `packages/types/` exporting types and (after this feature) Zod schemas.
- **packages/api-client**: Shared TypeScript package at `packages/api-client/` providing the HTTP client used by web and mobile apps.
- **DifferentialDiagnosis**: Clinical entity representing a candidate diagnosis with a probability score and ICD-10 code.
- **ICD-10**: International Classification of Diseases, 10th revision. Codes follow the pattern `^[A-Z][0-9]{2}(\.[0-9]{1,4})?$`.
- **Round-trip**: The property that `parse(format(x))` produces a value equivalent to `x`.
- **ApiValidationError**: A typed error class thrown by `packages/api-client` when a response body fails Zod schema validation. It wraps the underlying `ZodError` to provide structured validation failure details to callers.

---

## Requirements

### Requirement 1: Extract PromptBuilder from DiagnosticService

**User Story:** As a backend developer, I want prompt construction logic isolated in its own class, so that I can modify or test prompt templates without touching parsing or orchestration code.

#### Acceptance Criteria

1. THE PromptBuilder SHALL expose a `build(symptoms, patient_profile)` method that returns a prompt string.
2. WHEN `patient_profile` is provided, THE PromptBuilder SHALL include age group, weight, comorbidities, and allergies in the prompt.
3. WHEN `patient_profile` is `None`, THE PromptBuilder SHALL produce a valid prompt containing only the symptoms section.
4. THE PromptBuilder SHALL instruct the LLM to return a JSON array of at least 3 diagnoses ordered by descending probability.
5. THE PromptBuilder SHALL contain no I/O operations, no HTTP calls, and no database access.

---

### Requirement 2: Extract DiagnosticParser from DiagnosticService

**User Story:** As a backend developer, I want LLM response parsing and validation isolated in its own class, so that I can unit-test parsing logic independently of the RAG pipeline.

#### Acceptance Criteria

1. THE DiagnosticParser SHALL expose a `parse(llm_answer)` method that returns a list of `DifferentialDiagnosis` objects.
2. WHEN the LLM answer contains a valid JSON array with at least 3 entries, THE DiagnosticParser SHALL return the diagnoses sorted by descending probability.
3. WHEN the LLM answer contains a valid JSON array with fewer than 3 parseable diagnoses (including 0 parseable entries from an otherwise valid JSON array), THE DiagnosticParser SHALL return a list of 3 placeholder `DifferentialDiagnosis` objects with `probability=0.0` and `icd_code=None`.
4. WHEN a diagnosis entry has a `probability` value outside `[0.0, 1.0]`, THE DiagnosticParser SHALL clamp the value to the nearest bound and log a warning.
5. WHEN a diagnosis entry has an `icd_code` that does not match the ICD-10 pattern `^[A-Z][0-9]{2}(\.[0-9]{1,4})?$`, THE DiagnosticParser SHALL set `icd_code` to `None` and log a warning.
6. WHEN the LLM answer contains no parseable JSON array at all (malformed or non-JSON response), THE DiagnosticParser SHALL log a warning and return the 3-placeholder fallback list.
7. WHEN a valid `DifferentialDiagnosis` object is passed through `format` then `parse`, THE DiagnosticParser SHALL return an equivalent object, accounting for clamping of out-of-range `probability` values and nullification of invalid `icd_code` values (round-trip property).
8. THE DiagnosticParser SHALL contain no I/O operations, no HTTP calls, and no database access.

---

### Requirement 3: Create DiagnosticOrchestrator to replace DiagnosticService

**User Story:** As a backend developer, I want a thin orchestrator that delegates to PromptBuilder, RAGService, and DiagnosticParser, so that each collaborator can be replaced or tested in isolation.

#### Acceptance Criteria

1. THE DiagnosticOrchestrator SHALL expose a `get_differential_diagnosis(symptoms, patient_profile)` async method with the same signature and return type as the current `DiagnosticService.get_differential_diagnosis`.
2. THE DiagnosticOrchestrator SHALL delegate prompt construction exclusively to PromptBuilder.
3. THE DiagnosticOrchestrator SHALL delegate retrieval and generation exclusively to RAGService.
4. THE DiagnosticOrchestrator SHALL delegate response parsing exclusively to DiagnosticParser.
5. THE DiagnosticOrchestrator SHALL accept `rag_service` as a required constructor parameter and `prompt_builder` and `diagnostic_parser` as optional constructor parameters with sensible defaults (a default `PromptBuilder` instance and a default `DiagnosticParser` instance respectively) to enable dependency injection.
6. WHEN `DiagnosticOrchestrator.get_differential_diagnosis` is called, THE DiagnosticOrchestrator SHALL return a list of at least 3 `DifferentialDiagnosis` objects.
7. THE DiagnosticService name SHALL remain importable as an alias for DiagnosticOrchestrator to preserve backward compatibility with existing API routers.

---

### Requirement 4: Preserve existing DiagnosticService contract

**User Story:** As a backend developer, I want the refactoring to be transparent to API routers and tests, so that no call sites need to change.

#### Acceptance Criteria

1. WHEN the existing `DiagnosticService` import path is used, THE module SHALL resolve to `DiagnosticOrchestrator` without raising an `ImportError`.
2. THE DiagnosticOrchestrator SHALL accept `rag_service` as the only required constructor argument; `prompt_builder` and `diagnostic_parser` are optional and default to new instances of `PromptBuilder` and `DiagnosticParser` respectively.
3. WHEN `get_differential_diagnosis` is called with the same inputs as before the refactoring, THE DiagnosticOrchestrator SHALL return results with the same structure as before.

---

### Requirement 5: Add Zod schemas to packages/types

**User Story:** As a frontend developer, I want Zod schemas co-located with the TypeScript types, so that I can validate API responses at runtime on both web and mobile without duplicating schema definitions.

#### Acceptance Criteria

1. THE packages/types package SHALL export a Zod schema for each interface currently exported: `AuthUser`, `Symptom`, `DifferentialDiagnosis`, `DocumentSource`, `Prescription`, `SafetyAlert`, `PatientProfile`, `Consultation`, `ChatMessage`, and `ChatSession`.
2. FOR ALL valid objects conforming to a TypeScript interface, the corresponding Zod schema `parse` SHALL succeed without throwing.
3. FOR ALL objects that violate a TypeScript interface (e.g. missing required field, wrong type), the corresponding Zod schema `parse` SHALL throw a `ZodError`.
4. THE TypeScript type inferred from each Zod schema (via `z.infer`) SHALL be structurally equivalent to the corresponding hand-written TypeScript interface.
5. THE packages/types package SHALL export both the Zod schemas and the TypeScript types from the same entry point (`index.ts`) so that consumers need only one import.
6. THE TypeScript interfaces in packages/types SHALL be generated from Zod schemas via `z.infer` rather than hand-written. Hand-written interfaces that duplicate Zod-inferred types SHALL be removed from the codebase. This constraint SHALL be enforced by a CI lint rule that fails if any hand-written interface is found alongside a corresponding Zod schema in packages/types.

---

### Requirement 6: Validate API responses in packages/api-client

**User Story:** As a frontend developer, I want the API client to validate responses against Zod schemas, so that type mismatches between backend and frontend are caught at the network boundary rather than silently propagating.

#### Acceptance Criteria

1. WHEN the API client receives a response for a known endpoint, THE packages/api-client SHALL validate the response body against the corresponding Zod schema from packages/types.
2. IF the response body fails Zod validation, THEN THE packages/api-client SHALL throw an `ApiValidationError` containing the `ZodError` details.
3. WHEN the response body passes Zod validation, THE packages/api-client SHALL return the parsed, type-safe value to the caller.
4. THE packages/api-client SHALL not perform Zod validation on endpoints whose response schema is not defined in packages/types.

---

### Requirement 7: Round-trip schema consistency

**User Story:** As a developer, I want to verify that Zod schemas correctly round-trip through serialization, so that data integrity is maintained across the API boundary.

#### Acceptance Criteria

1. FOR ALL Zod schemas in packages/types, parsing a JSON-serialized object and re-serializing it SHALL produce an output equivalent to the original serialized form (round-trip property).
2. THE Zod schemas SHALL accept camelCase field names (TypeScript convention). THE packages/api-client SHALL normalize snake_case field names from the backend to camelCase before Zod validation.

---

### Requirement 8: Add docstrings to PrescriptionService

**User Story:** As a backend developer, I want PrescriptionService methods documented with medical context, so that future maintainers understand the clinical rules without reading external references.

#### Acceptance Criteria

1. THE PrescriptionService class SHALL have a class-level docstring explaining its role in the antibiotic prescription workflow, the protocol loading strategy (MongoDB → built-in fallback), and the patient profile fields it consumes.
2. THE `calculate_prescription` method SHALL have a docstring explaining: the mg/kg calculation for paediatric patients, the adult-dose cap (`is_capped_to_adult_dose`), the renal and hepatic adjustment factors, and the conditions under which `ValueError` and `HTTPException` are raised.
3. THE `load_protocols_from_db` method SHALL have a docstring explaining the MongoDB collection name, the fallback behaviour, and when this method should be called.
4. THE `_get_protocol` method SHALL have a docstring explaining the two-level lookup (cache → built-in dict) and the error raised for unknown antibiotics.

---

### Requirement 9: Add docstrings to AlertService

**User Story:** As a backend developer, I want AlertService methods documented with medical context, so that the clinical significance of each alert type is clear.

#### Acceptance Criteria

1. THE AlertService class SHALL have a class-level docstring listing the four alert categories it checks (allergy, drug interaction, age contraindication, organ failure), the severity levels used for each, and the data sources (MongoDB `drug_interactions` collection, built-in fallback).
2. THE `check_prescription` method SHALL have a docstring explaining the order of checks, the meaning of `critical` vs `warning` alerts, and that the returned list may be empty.
3. THE `_check_allergies` method SHALL have a docstring explaining the substring-matching strategy and why only one allergy alert per drug is emitted.
4. THE `_check_interactions` method SHALL have a docstring explaining the symmetric matching logic and the source of the interaction data.
5. THE `_check_age_contraindications` method SHALL have a docstring explaining which age groups are considered paediatric and how the contraindicated age group list is used.
6. THE `_check_organ_failure` method SHALL have a docstring explaining the renal and hepatic adjustment factors and why the alert level is `warning` rather than `critical`.

---

### Requirement 10: Add docstrings to RAGService

**User Story:** As a backend developer, I want RAGService documented so that the retrieval pipeline and its medical context are understandable without reading the MongoDB Atlas documentation.

#### Acceptance Criteria

1. THE RAGService class SHALL have a class-level docstring explaining the retrieval-augmented generation pipeline: embedding → vector search → LLM generation, the MongoDB collection and index names used, and the medical document sources indexed (CHU Lomé/Abomey-Calavi, OMS AFRO, MSF, PNLP).
2. THE `query` method SHALL have a docstring explaining the `top_k` parameter, how patient context is injected into the LLM prompt, and the structure of the returned `RAGResponse`.

---

### Requirement 11: Add docstrings to DiagnosticOrchestrator and its collaborators

**User Story:** As a backend developer, I want the new diagnostic classes documented so that the separation of responsibilities is immediately clear.

#### Acceptance Criteria

1. THE PromptBuilder class SHALL have a class-level docstring explaining its sole responsibility (prompt construction) and the prompt structure it produces.
2. THE DiagnosticParser class SHALL have a class-level docstring explaining its sole responsibility (LLM response parsing), the expected JSON format, and the fallback behaviour.
3. THE DiagnosticOrchestrator class SHALL have a class-level docstring explaining the orchestration flow and listing its three collaborators.
4. THE `get_differential_diagnosis` method on DiagnosticOrchestrator SHALL have a docstring explaining the end-to-end flow, the minimum number of diagnoses returned, and the conditions under which fallback placeholders are returned.

---

### Requirement 12: Add docstrings to EmbeddingModel

**User Story:** As a backend developer, I want EmbeddingModel documented so that its role in the vector retrieval pipeline is immediately clear to future maintainers.

#### Acceptance Criteria

1. THE EmbeddingModel class SHALL have a class-level docstring explaining its role in encoding text into dense vectors for semantic similarity search, the underlying model it wraps, and the expected output dimensionality.
2. THE `encode` method SHALL have a docstring explaining the input format (a string or list of strings), the returned tensor or array shape, and any normalisation applied to the output vectors.
