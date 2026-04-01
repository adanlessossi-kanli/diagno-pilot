# Implementation Plan: Code Quality Improvements

## Overview

Three independent workstreams executed in order: (1) decompose `DiagnosticService` into `PromptBuilder`, `DiagnosticParser`, and `DiagnosticOrchestrator`; (2) replace hand-written TypeScript interfaces in `packages/types` with Zod schemas and wire validation into `packages/api-client`; (3) add medical-context docstrings to backend services.

## Tasks

- [x] 1. Create PromptBuilder class
  - Create `backend/services/prompt_builder.py` with a stateless `PromptBuilder` class
  - Implement `build(symptoms, patient_profile)` returning a prompt string
  - Include optional `## Patient profile` section (age group, weight, comorbidities, allergies) when `patient_profile` is not `None`
  - Include `## Symptoms` section and the JSON-array instruction paragraph
  - Add class-level and method-level docstrings per Requirement 11.1
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 11.1_

  - [x] 1.1 Write property test for PromptBuilder purity (Property 1)
    - **Property 1: PromptBuilder is a pure function**
    - **Validates: Requirements 1.1, 1.5**

  - [x] 1.2 Write property test for PromptBuilder profile field inclusion (Property 2)
    - **Property 2: PromptBuilder includes patient profile fields**
    - **Validates: Requirements 1.2, 1.4**

  - [x] 1.3 Write unit tests for PromptBuilder
    - Test `build()` with a full patient profile — verify all fields appear in output
    - Test `build()` with `patient_profile=None` — verify no patient section, symptoms section present
    - _Requirements: 1.1, 1.2, 1.3_

- [x] 2. Create DiagnosticParser class
  - Create `backend/services/diagnostic_parser.py` with a stateless `DiagnosticParser` class
  - Implement `parse(llm_answer)` using the pipeline from the design: regex JSON extraction → `json.loads` → clamp probability → nullify invalid ICD-10 → sort or return 3 placeholders
  - Define `_ICD_CODE_RE` at module level
  - Add class-level and method-level docstrings per Requirement 11.2
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 11.2_

  - [x] 2.1 Write property test for probability clamping invariant (Property 3)
    - **Property 3: DiagnosticParser probability clamping invariant**
    - **Validates: Requirements 2.1, 2.4**

  - [x] 2.2 Write property test for ICD-10 nullification invariant (Property 4)
    - **Property 4: DiagnosticParser ICD-10 nullification invariant**
    - **Validates: Requirements 2.5**

  - [x] 2.3 Write property test for minimum result count (Property 5)
    - **Property 5: DiagnosticParser always returns at least 3 results**
    - **Validates: Requirements 2.2, 2.3, 2.6**

  - [x] 2.4 Write property test for round-trip consistency (Property 6)
    - **Property 6: DiagnosticParser round-trip**
    - **Validates: Requirements 2.7**

  - [x] 2.5 Write property test for DiagnosticParser purity (Property 7)
    - **Property 7: DiagnosticParser is a pure function**
    - **Validates: Requirements 2.8**

  - [x] 2.6 Write unit tests for DiagnosticParser
    - Test well-formed JSON array of 3+ entries — verify sorted order
    - Test 0, 1, 2 entries — verify 3 placeholders returned
    - Test non-JSON input — verify 3 placeholders returned
    - _Requirements: 2.2, 2.3, 2.6_

- [x] 3. Refactor diagnostic_service.py into DiagnosticOrchestrator
  - Replace the existing `DiagnosticService` class body in `backend/services/diagnostic_service.py` with `DiagnosticOrchestrator`
  - Constructor accepts `rag_service` (required), `prompt_builder` and `diagnostic_parser` (optional, defaulting to new instances)
  - `get_differential_diagnosis` delegates to `_prompt_builder.build`, `_rag.query`, and `_diagnostic_parser.parse` in sequence
  - Add `DiagnosticService = DiagnosticOrchestrator` alias at module level
  - Add class-level and method-level docstrings per Requirement 11.3, 11.4
  - Remove the now-extracted `_build_prompt` and `_parse_diagnoses` private methods
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 4.1, 4.2, 4.3, 11.3, 11.4_

  - [x] 3.1 Write property test for DiagnosticOrchestrator minimum result count (Property 8)
    - **Property 8: DiagnosticOrchestrator always returns at least 3 diagnoses**
    - **Validates: Requirements 3.1, 3.6, 4.3**

  - [x] 3.2 Write unit tests for DiagnosticOrchestrator
    - Test with mocked `RAGService`, `PromptBuilder`, `DiagnosticParser` — verify delegation
    - Test `DiagnosticService` import alias — verify `DiagnosticService is DiagnosticOrchestrator`
    - _Requirements: 3.2, 3.3, 3.4, 4.1_

- [x] 4. Checkpoint — Ensure all Python tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Replace hand-written interfaces in packages/types with Zod schemas
  - Add `zod` as a dependency to `packages/types/package.json` if not already present
  - Rewrite `packages/types/index.ts`: define `z.enum` schemas for `AgeGroup`, `AlertLevel`, `UserRole`, `Locale`
  - Define `z.object` schemas for all 10 interfaces: `AuthUser`, `Symptom`, `DifferentialDiagnosis`, `DocumentSource`, `Prescription`, `SafetyAlert`, `PatientProfile`, `Consultation`, `ChatMessage`, `ChatSession`
  - Export each schema as `<Name>Schema` and each type as `type <Name> = z.infer<typeof <Name>Schema>`
  - Remove all hand-written `interface` and `type` declarations that are now covered by `z.infer`
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [x] 5.1 Write property test for Zod schemas accepting valid objects (Property 9)
    - **Property 9: Zod schemas accept all valid objects**
    - **Validates: Requirements 5.1, 5.2**

  - [x] 5.2 Write property test for Zod schemas rejecting invalid objects (Property 10)
    - **Property 10: Zod schemas reject invalid objects**
    - **Validates: Requirements 5.3**

  - [x] 5.3 Write property test for Zod schema round-trip serialization (Property 11)
    - **Property 11: Zod schema round-trip serialization**
    - **Validates: Requirements 7.1**

- [x] 6. Add ApiValidationError and schema-aware parseResponse to packages/api-client
  - Add `ApiValidationError` class to `packages/api-client/index.ts` (extends `Error`, exposes `zodError` and `rawData`)
  - Add `normalizeKeys` recursive helper that converts snake_case object keys to camelCase (handles nested objects and arrays)
  - Update `parseResponse<T>` to accept an optional `schema?: ZodSchema<T>` parameter; when provided, normalize keys then `safeParse`, throwing `ApiValidationError` on failure
  - Wire schemas into the call sites for endpoints whose response type is defined in `packages/types` (e.g. `diagnose.getSymptomsDiagnosis`, `patients.listPatients`, `patients.getPatient`, `auth.me`)
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 7.2_

  - [x] 6.1 Write property test for ApiValidationError on schema mismatch (Property 12)
    - **Property 12: ApiValidationError thrown on schema mismatch**
    - **Validates: Requirements 6.1, 6.2, 6.3**

  - [x] 6.2 Write property test for snake_case normalization (Property 13)
    - **Property 13: snake_case normalization before validation**
    - **Validates: Requirements 7.2**

  - [x] 6.3 Write unit tests for ApiValidationError and parseResponse
    - Test `ApiValidationError` is a subclass of `Error` and exposes `zodError` and `rawData`
    - Test `parseResponse()` without schema — verify existing behavior unchanged
    - _Requirements: 6.2, 6.3, 6.4_

- [x] 7. Checkpoint — Ensure all TypeScript tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Add docstrings to PrescriptionService
  - Add class-level docstring to `PrescriptionService` covering role, protocol loading strategy, and patient profile fields consumed
  - Add method docstrings to `calculate_prescription`, `load_protocols_from_db`, and `_get_protocol` per Requirements 8.2–8.4
  - _Requirements: 8.1, 8.2, 8.3, 8.4_

- [x] 9. Add docstrings to AlertService
  - Add class-level docstring to `AlertService` covering the four alert categories, severity levels, and data sources
  - Add method docstrings to `check_prescription`, `_check_allergies`, `_check_interactions`, `_check_age_contraindications`, and `_check_organ_failure` per Requirements 9.2–9.6
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

- [x] 10. Add docstrings to RAGService and EmbeddingModel
  - Add class-level docstring to `RAGService` covering the RAG pipeline, MongoDB collection/index names, and indexed medical document sources
  - Add method docstring to `RAGService.query` covering `top_k`, patient context injection, and `RAGResponse` structure
  - Add class-level docstring to `EmbeddingModel` covering its role, underlying model, and output dimensionality
  - Add method docstring to `EmbeddingModel.encode` covering input format, output shape, and normalisation
  - _Requirements: 10.1, 10.2, 12.1, 12.2_

- [x] 11. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Property tests use Hypothesis (Python) and fast-check (TypeScript)
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- The `DiagnosticService` alias (task 3) must be in place before any existing import sites are touched
