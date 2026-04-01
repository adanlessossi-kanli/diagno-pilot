# Implementation Plan: Testing Coverage Expansion

## Overview

Expand automated test coverage across the backend (Python/FastAPI), web frontend (Next.js), and mobile (React Native/Expo) layers. The backend gains a real-infrastructure integration layer via Testcontainers; the web gains page-level and API route tests; mobile gains screen, navigation, and hook tests.

## Tasks

- [x] 1. Set up backend Testcontainers infrastructure
  - Create `backend/tests/integration/__init__.py`
  - Create `backend/tests/integration/conftest.py` with session-scoped `real_db`, `real_s3`, and `integration_app` fixtures
  - Add `pytest.mark.integration` marker to `pytest.ini`
  - Implement `_docker_available()` guard and `pytest_collection_modifyitems` hook to skip integration tests when Docker is unavailable
  - Add `testcontainers[mongodb,localstack]>=4.8.0` and `respx>=0.21.0` to `requirements-dev.txt`
  - Seed `real_db` with one `medecin` and one `admin` user using the same bcrypt logic as `scripts/seed.py`
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

  - [x] 1.1 Write property test for container fixture availability
    - **Property 1 (partial): Logout invalidates token (round-trip)**
    - Verify that the `integration_app` fixture correctly wires `real_db` and `real_s3` overrides
    - **Validates: Requirements 1.1, 1.2**

- [x] 2. Implement backend E2E auth integration tests
  - Create `backend/tests/integration/test_auth_e2e.py`
  - Test valid login returns `access_token`, `token_type`, `expires_in`
  - Test login persists audit log entry with `action = "login"` in real MongoDB
  - Test logout invalidates token (subsequent request returns HTTP 401)
  - Test token refresh with valid refresh token returns new access token
  - Test invalid refresh token returns HTTP 401
  - Test failed login with wrong credentials returns HTTP 401 and no audit log entry
  - Stub all LLM/embedding calls with `respx.mock` in strict mode (`assert_all_mocked=True`)
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [x] 2.1 Write property test for logout token invalidation
    - **Property 1: Logout invalidates token (round-trip)**
    - For any valid access token, after logout, a subsequent request with that token SHALL return HTTP 401
    - Use `@given` + `@settings(max_examples=50)` (integration tier)
    - Tag: `# Feature: testing-coverage, Property 1: Logout invalidates token`
    - **Validates: Requirements 2.3**

- [x] 3. Checkpoint — Ensure all backend auth integration tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implement backend E2E patient CRUD integration tests
  - Create `backend/tests/integration/test_patients_e2e.py`
  - Test `POST /api/v1/patients` persists patient and returns `_id`
  - Test create then fetch returns all submitted fields unchanged
  - Test `PUT /api/v1/patients/{id}` updates are reflected in subsequent GET
  - Test `GET /api/v1/patients` returns only the authenticated user's patients
  - Test `pharmacien` user creating a patient returns HTTP 403
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [x] 4.1 Write property test for patient create/fetch round-trip
    - **Property 2: Patient create/fetch round-trip**
    - For any valid patient payload, create then fetch SHALL return all submitted fields equal to original values
    - Tag: `# Feature: testing-coverage, Property 2: Patient create/fetch round-trip`
    - **Validates: Requirements 3.2, 3.6**

  - [x] 4.2 Write property test for patient list scope isolation
    - **Property 3: Patient list scope isolation**
    - For any two distinct users, the patient list for user A SHALL NOT contain patients created by user B
    - Tag: `# Feature: testing-coverage, Property 3: Patient list scope isolation`
    - **Validates: Requirements 3.4**

  - [x] 4.3 Write property test for patient update round-trip
    - **Property 4: Patient update reflected in fetch (round-trip)**
    - For any existing patient and valid update payload, update then fetch SHALL return updated field values
    - Tag: `# Feature: testing-coverage, Property 4: Patient update reflected in fetch`
    - **Validates: Requirements 3.3**

- [x] 5. Implement backend E2E diagnose and prescription integration tests
  - Create `backend/tests/integration/test_diagnose_e2e.py`
  - Stub LLM calls with `respx.mock` (`assert_all_mocked=True`)
  - Test symptom submission returns ≥ 3 diagnoses each with `probability` in [0.0, 1.0] and non-empty `icd_code`
  - Test prescription for patient with known allergy returns critical allergy alert with non-null `alternative`
  - Test fluoroquinolone for child patient returns critical contraindication alert
  - Test prescription for renal failure patient has reduced `dose_mg`
  - Test diagnose session round-trip: GET session returns same diagnoses as original POST response
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [x] 5.1 Write property test for diagnose response structure
    - **Property 5: Diagnose response structure**
    - For any non-empty symptom list (LLM stubbed), response SHALL contain ≥ 3 diagnoses each with probability in [0.0, 1.0] and non-empty `icd_code`
    - Tag: `# Feature: testing-coverage, Property 5: Diagnose response structure`
    - **Validates: Requirements 4.1**

  - [x] 5.2 Write property test for diagnose session round-trip
    - **Property 6: Diagnose session round-trip**
    - For any diagnose session, GET session SHALL return diagnoses equivalent to the original POST response
    - Tag: `# Feature: testing-coverage, Property 6: Diagnose session round-trip`
    - **Validates: Requirements 4.5**

- [x] 6. Implement backend E2E file upload integration tests
  - Create `backend/tests/integration/test_files_e2e.py`
  - Test valid PDF upload stores file in LocalStack S3 and returns `file_id`
  - Test upload then download returns byte-for-byte identical content
  - Test disallowed MIME type upload returns HTTP 422
  - Test unauthenticated upload returns HTTP 401
  - Test admin document upload persists metadata in MongoDB
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [x] 6.1 Write property test for file upload/download round-trip
    - **Property 7: File upload/download round-trip**
    - For any file with allowed MIME type, upload then download SHALL return byte-for-byte identical content
    - Tag: `# Feature: testing-coverage, Property 7: File upload/download round-trip`
    - **Validates: Requirements 5.2**

  - [x] 6.2 Write property test for disallowed file types rejected
    - **Property 8: Disallowed file types rejected**
    - For any file with a MIME type not in the allowed list, upload SHALL return HTTP 422
    - Tag: `# Feature: testing-coverage, Property 8: Disallowed file types rejected`
    - **Validates: Requirements 5.3**

- [x] 7. Implement backend E2E RAG chat integration tests
  - Create `backend/tests/integration/test_chat_e2e.py`
  - Stub LLM endpoint with `respx.mock` (`assert_all_mocked=True`)
  - Test chat message returns non-empty `answer` and `sources` list
  - Test multiple messages in same session: GET history returns all messages in chronological order
  - Test message and response are persisted in MongoDB
  - Test unauthenticated chat request returns HTTP 401
  - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [x] 7.1 Write property test for chat history ordering
    - **Property 9: Chat history ordering**
    - For any sequence of N messages in the same session, GET history SHALL return exactly N messages in chronological order
    - Tag: `# Feature: testing-coverage, Property 9: Chat history ordering`
    - **Validates: Requirements 6.2**

- [x] 8. Checkpoint — Ensure all backend integration tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Add web frontend dependencies and test setup
  - Add `"msw": "^2.7.0"` to `apps/web/package.json` devDependencies
  - Create MSW server setup file for API route tests
  - Verify `@testing-library/react`, `vitest`, and `fast-check` are already present
  - _Requirements: 8.5, 12.3_

- [x] 10. Implement web page-level tests
  - Create `apps/web/src/app/[locale]/login/__tests__/page.test.tsx`
    - Test email/password fields render, valid credentials call auth API and redirect
    - Test invalid credentials display error without redirect
  - Create `apps/web/src/app/[locale]/patients/__tests__/page.test.tsx`
    - Test loading skeleton renders while fetching, patient cards render after resolve
    - Test empty state renders when API returns empty list
  - Create `apps/web/src/app/[locale]/patients/__tests__/[id].test.tsx`
    - Test patient name, weight, allergies, and consultation history are rendered
  - Create `apps/web/src/app/[locale]/diagnose/__tests__/page.test.tsx`
    - Test symptom submission triggers diagnose API and renders differential diagnoses
    - Test critical alerts render with `data-severity="critical"` attribute
  - Create `apps/web/src/app/[locale]/chat/__tests__/page.test.tsx`
    - Test sending a message appends it and renders assistant response with source citations
  - Mock `@diagno-pilot/api-client`, `next/navigation`, and `next-intl` with `vi.mock()`
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8_

  - [x] 10.1 Write property test for patient detail page renders all required fields
    - **Property 10: Patient detail page renders all required fields**
    - For any patient with non-null `full_name`, `weight_kg`, `allergies`, `consultation_history`, the rendered page SHALL display each field
    - Tag: `// Feature: testing-coverage, Property 10: Patient detail page renders all required fields`
    - **Validates: Requirements 7.5**

  - [x] 10.2 Write property test for critical alerts rendered with distinct style
    - **Property 11: Critical alerts rendered with distinct style**
    - For any alert with `level = "critical"`, the rendered element SHALL have `data-severity="critical"`
    - Tag: `// Feature: testing-coverage, Property 11: Critical alerts rendered with distinct style`
    - **Validates: Requirements 7.7**

- [x] 11. Implement web API route tests
  - Create `apps/web/src/app/api/auth/__tests__/set-cookie.test.ts`
    - Test valid token payload sets cookie with `HttpOnly` and `Secure` flags
    - Test missing/malformed payload returns HTTP 400
  - Create `apps/web/src/app/api/auth/__tests__/proxy.test.ts`
    - Test backend HTTP 401 is propagated as 401 (not 500)
    - Test backend HTTP 403 is propagated as 403
  - Use `msw` to intercept all backend fetch calls; no real network calls
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [x] 11.1 Write property test for malformed set-cookie payload returns HTTP 400
    - **Property 14: Malformed set-cookie payload returns HTTP 400**
    - For any request with missing or malformed body (no `access_token`, wrong type), response SHALL be HTTP 400
    - Tag: `// Feature: testing-coverage, Property 14: Malformed set-cookie payload returns HTTP 400`
    - **Validates: Requirements 8.2**

- [x] 12. Implement web middleware/auth redirect tests
  - Add tests to the appropriate middleware test file (or create `apps/web/src/app/[locale]/__tests__/auth-redirect.test.tsx`)
  - Test that protected routes without a valid session redirect to `/{locale}/login`
  - Test that non-admin users accessing admin-gated pages see access-denied state
  - _Requirements: 7.9, 7.10_

  - [x] 12.1 Write property test for unauthenticated web requests redirected to login
    - **Property 12: Unauthenticated web requests redirected to login**
    - For any protected Next.js route, a request without a valid session SHALL redirect to `/{locale}/login`
    - Tag: `// Feature: testing-coverage, Property 12: Unauthenticated web requests redirected to login`
    - **Validates: Requirements 7.9**

  - [x] 12.2 Write property test for non-admin users see access-denied
    - **Property 13: Non-admin users see access-denied on admin pages**
    - For any user with a role other than `admin`, accessing an admin-gated page SHALL render access-denied
    - Tag: `// Feature: testing-coverage, Property 13: Non-admin users see access-denied on admin pages`
    - **Validates: Requirements 7.10**

- [x] 13. Checkpoint — Ensure all web tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 14. Implement mobile screen-level tests
  - Create `apps/mobile/app/(tabs)/__tests__/diagnose.test.tsx`
    - Test symptom submission renders differential diagnoses with probability indicators
    - Test critical prescription alert renders with `testID="alert-critical"`
  - Create `apps/mobile/app/(tabs)/__tests__/patients.test.tsx`
    - Test screen renders one `MobilePatientCard` per patient
    - Test empty state renders when API returns empty list
  - Create `apps/mobile/app/(tabs)/__tests__/chat.test.tsx`
    - Test sending a message appends it and renders assistant reply with `MobileSourceCitation`
  - Create `apps/mobile/app/(tabs)/__tests__/profile.test.tsx`
    - Test authenticated user's name and role are displayed
  - Create `apps/mobile/app/patient/__tests__/[id].test.tsx`
    - Test patient name, weight, and allergy list are rendered
  - Mock `@diagno-pilot/api-client` with `jest.mock()` and `AuthContext` with `jest.spyOn()`
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 9.9, 9.10_

  - [x] 14.1 Write property test for critical mobile alerts rendered with correct testID
    - **Property 15: Critical mobile alerts rendered with correct testID**
    - For any alert with `level = "critical"`, the rendered element SHALL have `testID="alert-critical"`
    - Tag: `// Feature: testing-coverage, Property 15: Critical mobile alerts rendered with correct testID`
    - **Validates: Requirements 9.4**

  - [x] 14.2 Write property test for mobile patient list renders one card per patient
    - **Property 16: Mobile patient list renders one card per patient**
    - For any list of N patients, the screen SHALL render exactly N `MobilePatientCard` components
    - Tag: `// Feature: testing-coverage, Property 16: Mobile patient list renders one card per patient`
    - **Validates: Requirements 9.5**

  - [x] 14.3 Write property test for mobile patient detail renders required fields
    - **Property 17: Mobile patient detail renders required fields**
    - For any patient with non-null `full_name`, `weight_kg`, `allergies`, the rendered screen SHALL display each field
    - Tag: `// Feature: testing-coverage, Property 17: Mobile patient detail renders required fields`
    - **Validates: Requirements 9.7**

  - [x] 14.4 Write property test for mobile profile screen displays user name and role
    - **Property 18: Mobile profile screen displays user name and role**
    - For any authenticated user with non-null `full_name` and `role`, the profile screen SHALL display both values
    - Tag: `// Feature: testing-coverage, Property 18: Mobile profile screen displays user name and role`
    - **Validates: Requirements 9.9**

- [x] 15. Implement mobile navigation flow tests
  - Create `apps/mobile/app/__tests__/navigation.test.tsx`
  - Use `renderRouter` from `expo-router/testing-library` with mock file system
  - Test `medecin` user sees Diagnose, Patients, Chat, and Profile tabs
  - Test `pharmacien` user cannot access Patients tab (redirected to access-denied)
  - Test unauthenticated user accessing any protected tab redirects to login
  - Test navigating from patients list to patient detail passes correct `id` route parameter
  - _Requirements: 10.1, 10.2, 10.3, 10.4_

  - [x] 15.1 Write property test for unauthenticated mobile users redirected to login
    - **Property 19: Unauthenticated mobile users redirected to login**
    - For any protected mobile screen with no valid session in `AuthContext`, the app SHALL navigate to login
    - Tag: `// Feature: testing-coverage, Property 19: Unauthenticated mobile users redirected to login`
    - **Validates: Requirements 9.10, 10.3**

  - [x] 15.2 Write property test for navigation passes correct patient id
    - **Property 22: Navigation passes correct patient id as route parameter**
    - For any patient in the list, tapping its card SHALL result in route parameter `id` equaling that patient's `_id`
    - Tag: `// Feature: testing-coverage, Property 22: Navigation passes correct patient id as route parameter`
    - **Validates: Requirements 10.4**

- [x] 16. Implement mobile API hook and AuthContext tests
  - Create `apps/mobile/src/contexts/__tests__/AuthContext.test.tsx`
  - Test token refresh: expired access token + valid refresh token → new access token without re-login
  - Test expired/invalid refresh token → session cleared, navigate to login
  - Test API calls from mobile hooks include `Authorization: Bearer <token>` header
  - Test HTTP 401 from API triggers token refresh before retry
  - _Requirements: 11.1, 11.2, 11.3, 11.4_

  - [x] 16.1 Write property test for mobile API calls include Authorization header
    - **Property 20: Mobile API calls include Authorization header**
    - For any API call with a valid token in `AuthContext`, the outbound request SHALL include `Authorization: Bearer <token>`
    - Tag: `// Feature: testing-coverage, Property 20: Mobile API calls include Authorization header`
    - **Validates: Requirements 11.3**

- [x] 17. Implement mobile utility property tests
  - Locate the `probabilityColor` utility function in the mobile codebase
  - Add a `fast-check` property test asserting `probabilityColor(p)` returns a non-empty string for all `p` in [0.0, 1.0]
  - _Requirements: 11.5_

  - [x] 17.1 Write property test for probabilityColor returns non-empty string
    - **Property 21: `probabilityColor` returns non-empty string for all valid probabilities**
    - For any `p` in [0.0, 1.0], `probabilityColor(p)` SHALL return a non-empty string
    - Use `fc.float({ min: 0.0, max: 1.0 })` with `numRuns: 100`
    - Tag: `// Feature: testing-coverage, Property 21: probabilityColor returns non-empty string`
    - **Validates: Requirements 11.5**

- [x] 18. Final checkpoint — Ensure all tests pass across all layers
  - Ensure all tests pass, ask the user if questions arise.
  - Verify `pytest -m "not integration"` passes without Docker
  - Verify `pytest -m integration` passes with Docker available
  - Verify `npx vitest --run` passes from `apps/web/`
  - Verify `npx jest --passWithNoTests` passes from `apps/mobile/`

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP
- Each task references specific requirements for traceability
- Backend integration tests require Docker; unit/property tests do not
- `respx` is the sole HTTP stubbing library for backend `httpx` calls — no real LLM network calls
- Property tests use `@settings(max_examples=50)` at the integration tier and `numRuns: 100` at the unit tier
