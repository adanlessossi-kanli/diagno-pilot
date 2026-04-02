# Implementation Plan: i18n-medical-content

## Overview

Extend Diagno-Pilot's internationalisation from UI strings to all medical content, introducing `fr-TG`, `fr-BJ`, and `en` locale support across the full stack: shared types, backend services, MongoDB data models, web app, and mobile app.

## Tasks

- [x] 1. Extend shared types and i18n package
  - [x] 1.1 Widen `LocaleSchema` in `@diagno-pilot/types` to include `fr-TG` and `fr-BJ`
    - Update `packages/types/src/index.ts` (or equivalent) to export `LocaleSchema = z.enum(['fr', 'en', 'fr-TG', 'fr-BJ'])` and the derived `Locale` type
    - Ensure existing `'fr' | 'en'` consumers remain assignable without changes
    - _Requirements: 1.6, 9.4_

  - [x] 1.2 Add `fr-TG` and `fr-BJ` locale files to `@diagno-pilot/i18n`
    - Create `packages/i18n/locales/fr-TG.json` with Togo-specific overrides merged on top of `fr.json`
    - Create `packages/i18n/locales/fr-BJ.json` with Bénin-specific overrides merged on top of `fr.json`
    - Update `getMessages()` to deep-merge base `fr.json` with the region-specific file
    - Export `locales` array and `defaultLocale = 'fr-TG'` from the package
    - _Requirements: 6.1, 6.6_

  - [x] 1.3 Write unit tests for `getMessages()` merge strategy
    - Verify `fr-TG` and `fr-BJ` messages include base `fr` keys plus region overrides
    - _Requirements: 6.1_

- [x] 2. Implement `Content_Localiser` module (backend)
  - [x] 2.1 Create `backend/services/content_localiser.py` with `parse_locale`, `extract_region`, and `localise`
    - Implement `SUPPORTED_LOCALES`, `FALLBACK_CHAINS`, and `DEFAULT_LOCALE` env var reading
    - `parse_locale`: parse BCP-47 `Accept-Language` header; return best-matching supported locale; fall back to `DEFAULT_LOCALE`
    - `extract_region`: return ISO 3166-1 alpha-2 country code or `None`
    - `localise`: walk `content_object['translations']` using the fallback chain; never raise; return `None` when no key found
    - _Requirements: 1.2, 1.3, 1.4, 1.5, 1.7, 5.1, 5.2, 5.3, 5.5, 5.6_

  - [x] 2.2 Write property test — Property 1: `parse_locale` always returns a supported locale
    - **Property 1: parse_locale always returns a supported locale**
    - **Validates: Requirements 1.2, 1.3, 1.4, 1.7**
    - File: `backend/tests/test_content_localiser.py`

  - [x] 2.3 Write property test — Property 2: `extract_region` correctly derives region
    - **Property 2: extract_region correctly derives region from locale**
    - **Validates: Requirements 1.8, 5.5**
    - File: `backend/tests/test_content_localiser.py`

  - [x] 2.4 Write property test — Property 3: locale round-trip
    - **Property 3: locale round-trip**
    - **Validates: Requirements 5.4**
    - File: `backend/tests/test_content_localiser.py`

  - [x] 2.5 Write property test — Property 4: `localise` follows the fallback chain
    - **Property 4: localise follows the fallback chain**
    - **Validates: Requirements 5.1, 5.2, 5.6**
    - File: `backend/tests/test_content_localiser.py`

  - [x] 2.6 Write unit tests for `Content_Localiser`
    - Cover specific examples: each supported locale, `fr` alias, empty header, `None` header
    - _Requirements: 1.2, 1.3, 1.7, 5.1, 5.3_

- [x] 3. Add FastAPI locale middleware
  - [x] 3.1 Create `backend/core/locale_middleware.py`
    - Starlette middleware that reads `Accept-Language`, calls `Content_Localiser.parse_locale()`, and stores `(locale, region)` in `request.state.locale` / `request.state.region`
    - Log the resolved pair at `INFO` level
    - _Requirements: 1.1, 1.2, 1.3, 10.1_

  - [x] 3.2 Register the middleware in the FastAPI application factory
    - Add `LocaleMiddleware` to the middleware stack before route handlers
    - _Requirements: 1.1_

  - [x] 3.3 Write unit tests for locale middleware
    - Test `fr-TG`, `fr-BJ`, `en`, `fr` alias, absent header, and unsupported locale inputs
    - _Requirements: 1.2, 1.3, 1.7_

- [x] 4. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Extend MongoDB data models and migration
  - [x] 5.1 Extend `AntibioticProtocol` Python dataclass
    - Add `region`, `available_regions`, `atc_class`, `first_line`, `names`, `version`, `created_at` fields as specified in the design
    - _Requirements: 2.1, 2.4, 11.1_

  - [x] 5.2 Create `drug_catalogue` MongoDB collection and Pydantic model
    - Define `DrugCatalogueEntry` Pydantic model with `inn`, `display_names`, `trade_names`, `available_regions`, `atc_class`
    - Add MongoDB indexes: unique `{ inn: 1 }` and `{ available_regions: 1 }`
    - _Requirements: 3.1, 3.4_

  - [x] 5.3 Write migration script `backend/scripts/migrate_protocols_add_region.py`
    - For every `antibiotic_protocols` document lacking a `region` field, set `region: "ALL"` and `available_regions: ["TG", "BJ"]` without modifying other fields
    - _Requirements: 9.3_

  - [x] 5.4 Write property test — Property 14: migration assigns `ALL` to legacy documents
    - **Property 14: protocol migration assigns region ALL to legacy documents**
    - **Validates: Requirements 9.3**
    - File: `backend/tests/test_migration.py`

  - [x] 5.5 Add compound index `{ name: 1, region: 1, created_at: -1 }` to `antibiotic_protocols`
    - Add index creation to the database initialisation / migration step
    - _Requirements: 2.7_

- [x] 6. Extend `PrescriptionService` with region-aware logic
  - [x] 6.1 Re-key `_protocols_cache` from `name` to `(name, region)` composite key
    - Update cache loading to index by `(name.lower(), region)` for all documents
    - Implement three-tier lookup: `(name, R)` → `(name, "ALL")` → built-in `ANTIBIOTIC_PROTOCOLS`
    - _Requirements: 2.2, 2.3, 2.7_

  - [x] 6.2 Implement availability check and alternative suggestion in `calculate_prescription`
    - Before returning a protocol, verify `available_regions` includes the request region
    - If not available: find alternative with same ATC class and first-line status; fall back to any same-ATC alternative
    - Set `unavailable_in_region: true` when applicable
    - _Requirements: 2.6, 3.5_

  - [x] 6.3 Create `LocalisedPrescription` Pydantic model and update `calculate_prescription` signature
    - Add `locale`, `region`, `display_name`, `trade_name`, `unavailable_in_region`, `protocol_version` fields
    - Populate `display_name` from `names` map (fall back to raw `name` for legacy docs)
    - Populate `trade_name` from `Drug_Catalogue` for the request region
    - _Requirements: 2.4, 2.5, 3.2, 3.3, 9.5_

  - [x] 6.4 Implement `reload_protocols(name)` method for cache invalidation
    - Synchronously reload protocols for the given name from MongoDB
    - Called by the admin PUT endpoint before returning `200 OK`
    - _Requirements: 8.2, NFR 1_

  - [x] 6.5 Write property test — Property 5: region-aware protocol lookup priority
    - **Property 5: region-aware protocol lookup priority**
    - **Validates: Requirements 2.2, 2.3**
    - File: `backend/tests/test_prescription_service_i18n.py`

  - [x] 6.6 Write property test — Property 6: unavailable protocol triggers alternative suggestion
    - **Property 6: unavailable protocol triggers alternative suggestion**
    - **Validates: Requirements 2.6, 3.5**
    - File: `backend/tests/test_prescription_service_i18n.py`

  - [x] 6.7 Write property test — Property 7: prescription display name always present
    - **Property 7: prescription response always includes localised display name**
    - **Validates: Requirements 2.4, 2.5, 9.5**
    - File: `backend/tests/test_prescription_service_i18n.py`

  - [x] 6.8 Write property test — Property 8: INN always present, trade name conditional
    - **Property 8: drug catalogue response includes INN and conditional trade name**
    - **Validates: Requirements 3.1, 3.2, 3.3**
    - File: `backend/tests/test_prescription_service_i18n.py`

  - [x] 6.9 Write integration unit tests for `PrescriptionService`
    - Verify `LocalisedPrescription` fields are correctly populated for `TG` and `BJ` requests
    - _Requirements: 2.2, 2.4, 3.2_

- [x] 7. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Extend `PromptBuilder` with locale/region injection
  - [x] 8.1 Update `PromptBuilder.build()` to accept `locale` and `region` parameters
    - Prepend the language-and-guidelines system instruction block to the prompt
    - Map `fr-TG`/`fr-BJ` → French + CHU Lomé/CHU Abomey-Calavi; `en` → English + OMS AFRO/MSF
    - _Requirements: 4.1, 4.2, 4.3_

  - [x] 8.2 Write property test — Property 9: prompt contains locale and region instructions
    - **Property 9: prompt contains locale and region instructions for all supported locales**
    - **Validates: Requirements 4.1, 4.2, 4.3**
    - File: `backend/tests/test_prompt_builder_i18n.py`

  - [x] 8.3 Write snapshot unit tests for `PromptBuilder`
    - Verify exact system instruction block for each locale/region combination
    - _Requirements: 4.1, 4.2, 4.3_

- [x] 9. Extend `RAGService` with region-aware retrieval
  - [x] 9.1 Add `region` parameter to `RAGService.query()`
    - When `region` is provided, extend the `$vectorSearch` pipeline with `filter: { "metadata.region": { "$in": [region, "ALL"] } }`
    - _Requirements: 4.6_

  - [x] 9.2 Write property test — Property 11: RAG query includes region filter
    - **Property 11: RAG query includes region filter for non-ALL regions**
    - **Validates: Requirements 4.6**
    - File: `backend/tests/test_rag_service_i18n.py`

- [x] 10. Extend `DiagnosticOrchestrator` with locale metadata and mismatch detection
  - [x] 10.1 Pass `(locale, region)` from `request.state` through to `PromptBuilder.build()` and `RAGService.query()`
    - _Requirements: 4.1, 4.6_

  - [x] 10.2 Extend `DiagnosticResult` dataclass with `locale` and `language_mismatch` fields
    - After `LLMRouter.generate()` returns, run lightweight language detection (e.g. `langdetect`)
    - Set `language_mismatch: true` and log `WARNING` on mismatch; set `locale` to requested locale when metadata absent
    - _Requirements: 4.4, 4.5, 4.7_

  - [x] 10.3 Write property test — Property 10: `DiagnosticResult` always carries locale metadata
    - **Property 10: DiagnosticResult always carries locale metadata**
    - **Validates: Requirements 4.4, 4.7**
    - File: `backend/tests/test_diagnostic_orchestrator_i18n.py`

  - [x] 10.4 Write unit test for language mismatch detection
    - Mock LLM returning wrong-language response; assert `language_mismatch: true`
    - _Requirements: 4.5_

- [x] 11. Extend `AuditService` with locale and region fields
  - [x] 11.1 Update `log_action()` to include `locale` and `region` in the `details` dict for medical content endpoints
    - _Requirements: 10.1, 10.2_

  - [x] 11.2 Update `PrescriptionService` to store `protocol_version`, `locale`, and `region` in the prescription audit record
    - _Requirements: 10.2, 11.3_

  - [x] 11.3 Write unit tests for audit logging
    - Assert prescription audit record contains `locale`, `region`, `protocol_version`
    - _Requirements: 10.2, 11.3_

- [x] 12. Implement protocol version history endpoints
  - [x] 12.1 Ensure protocol updates create new documents rather than overwriting
    - `PrescriptionService` always selects the latest version for `(name, region)` at cache-load time
    - _Requirements: 11.1, 11.2_

  - [x] 12.2 Write property test — Property 15: protocol update creates a new version document
    - **Property 15: protocol update creates a new version document**
    - **Validates: Requirements 11.1, 11.2**
    - File: `backend/tests/test_protocol_versioning.py`

  - [x] 12.3 Add `GET /protocols/{id}/version/{version_id}` endpoint
    - Retrieve a `Protocol_Variant` by version identifier for audit and review
    - _Requirements: 11.4_

- [x] 13. Implement region-aware admin API endpoints
  - [x] 13.1 Add `PUT /protocols/{id}` endpoint with region scoping
    - Accept `region` field in request body; call `prescription_service.reload_protocols(name)` synchronously before returning `200 OK`
    - _Requirements: 8.1, 8.2, NFR 1_

  - [x] 13.2 Add `DELETE /protocols/{id}` endpoint with last-variant guard
    - Reject deletion if the protocol is the only variant across all regions; return explanatory error
    - _Requirements: 8.5_

  - [x] 13.3 Add `POST /protocols` and `GET /protocols` endpoints with region filter support
    - Support creating new Protocol_Variants and listing by region
    - _Requirements: 8.1, 8.3_

  - [x] 13.4 Add `POST /admin/documents` endpoint requiring `region` field
    - Validate that uploaded medical documents include a `region` field (`TG`, `BJ`, or `ALL`)
    - Store `metadata.region` on the resulting `document_chunks` documents
    - _Requirements: 8.4_

  - [x] 13.5 Write property test — Property 16: last-variant deletion is rejected
    - **Property 16: last-variant deletion is rejected**
    - **Validates: Requirements 8.5**
    - File: `backend/tests/test_admin_protocol.py`

  - [x] 13.6 Write unit tests for admin protocol CRUD
    - Test region scoping, cache reload within 5 s (NFR 1), and error responses
    - _Requirements: 8.1, 8.2, 8.5, NFR 1_

- [x] 14. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 15. Extend web app (Next.js) locale routing
  - [x] 15.1 Update `apps/web/src/i18n/routing.ts` to include `fr-TG`, `fr-BJ`, `en` locales with `defaultLocale: 'fr-TG'`
    - _Requirements: 6.2, 6.6_

  - [x] 15.2 Update `apps/web/src/middleware.ts` to resolve `fr` → `fr-TG` and forward `Accept-Language` on all API fetch calls
    - Implement or update the shared `apiFetch` wrapper to inject the `Accept-Language` header
    - _Requirements: 6.3, 9.1_

  - [x] 15.3 Persist user locale preference in `diagno_locale` cookie; read it in middleware to override browser detection
    - _Requirements: 6.4, 6.5_

  - [x] 15.4 Write property test — Property 12: `Accept-Language` header forwarded on all API requests (web)
    - **Property 12: Accept-Language header is forwarded on all API requests**
    - **Validates: Requirements 6.3, 7.3**
    - File: `apps/web/src/__tests__/api-client-locale.test.ts`

  - [x] 15.5 Write unit tests for web middleware locale resolution
    - Test `fr-TG`, `fr-BJ`, `en`, `fr`, unsupported values, and cookie override
    - _Requirements: 6.2, 6.4, 6.5, 9.1_

- [x] 16. Extend mobile app (React Native) I18nContext
  - [x] 16.1 Update `I18nContext` to support `fr-TG`, `fr-BJ`, `en`; use `expo-localization` for device locale detection
    - Export `SUPPORTED_LOCALES` and `DEFAULT_LOCALE = 'fr-TG'`
    - `setLocale()` triggers cache invalidation so cached medical content is re-fetched
    - _Requirements: 7.1, 7.2, 7.4_

  - [x] 16.2 Update the shared `apiClient` to inject `Accept-Language: <locale>` on all API calls
    - _Requirements: 7.3_

  - [x] 16.3 Write property test — Property 13: mobile locale fallback to `fr-TG`
    - **Property 13: mobile locale detection falls back to fr-TG for unsupported device locales**
    - **Validates: Requirements 7.2, 7.5**
    - File: `apps/mobile/src/__tests__/I18nContext.test.tsx`

  - [x] 16.4 Write unit tests for mobile `I18nContext`
    - Test locale persistence round-trip via mocked `SecureStore`; test `Accept-Language` injection
    - _Requirements: 7.1, 7.3, 7.4_

- [x] 17. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP
- Each task references specific requirements for traceability
- Property tests use `hypothesis` (Python) and `fast-check` (TypeScript)
- Checkpoints ensure incremental validation at logical boundaries
- The migration script (task 5.3) must be run against the live database before deploying the updated `PrescriptionService`
