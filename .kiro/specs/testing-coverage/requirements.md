# Requirements Document

## Introduction

This feature expands the automated test coverage of Diagno-Pilot across all three layers of the stack:

- **Backend (Python 3.12 + FastAPI)**: Replace mock-based integration tests with real-infrastructure E2E tests using Testcontainers (MongoDB Atlas Local + LocalStack S3). The existing pytest + Hypothesis suite already covers unit and property-based tests; this work adds a dedicated `tests/integration/` layer that spins up real containers.
- **Frontend web (Next.js App Router + TypeScript)**: Extend the existing Vitest + React Testing Library suite — currently limited to component and context tests — with page-level rendering tests and API route integration tests.
- **Mobile (React Native / Expo)**: Expand the minimal Jest suite with screen-level integration tests, navigation flow tests, and API hook tests covering the key user journeys.

Key flows to cover across all layers: auth login/logout/refresh, diagnose symptoms, prescriptions, patient CRUD, file upload, RAG chat, and alert checks.

---

## Glossary

- **Test_Suite**: The complete automated test collection for a given layer (backend, web, mobile).
- **Integration_Test**: A test that exercises multiple real components together, including real infrastructure (database, object storage) rather than mocks.
- **E2E_Backend_Test**: A backend integration test that uses real MongoDB and real LocalStack S3 containers via Testcontainers, exercising the full FastAPI request/response cycle.
- **HTTP_Stub**: A test-time intercept of outbound HTTP calls made by the backend using `respx` (the standard mock transport for `httpx`). All LLM and embedding service calls in integration tests SHALL be intercepted via `respx.mock` rather than reaching real external endpoints.
- **Testcontainers**: A Python library (`testcontainers`) that starts and stops Docker containers (MongoDB Atlas Local, LocalStack) programmatically during test execution.
- **MongoDB_Container**: A Docker container running `mongodb/mongodb-atlas-local` used exclusively during backend integration tests.
- **LocalStack_Container**: A Docker container running LocalStack that emulates AWS S3, used exclusively during backend integration tests.
- **Page_Test**: A Next.js page-level test that renders a full route component (including its data-fetching wrappers) using Vitest + React Testing Library.
- **API_Route_Test**: A test that calls a Next.js API route handler directly (without an HTTP server) and asserts on the response.
- **Screen_Test**: A React Native screen-level test that renders a full screen component using Jest + React Native Testing Library and asserts on user-visible behaviour.
- **Navigation_Test**: A test that verifies Expo Router navigation transitions between screens.
- **Auth_Flow**: The sequence login → obtain JWT → use JWT → logout → token invalidated.
- **Refresh_Flow**: The sequence access-token-expired → use refresh token → obtain new access token.
- **Diagnose_Flow**: The sequence submit symptoms → receive ≥ 3 differential diagnoses with probability scores and ICD-10 codes.
- **Prescription_Flow**: The sequence select diagnosis → receive prescription with dose, frequency, duration, and safety alerts.
- **Patient_CRUD**: Create, read, update, and delete operations on patient profiles.
- **File_Upload_Flow**: Upload a clinical file (PDF, image, CSV) to S3 via the backend and retrieve its metadata.
- **RAG_Chat_Flow**: Send a multi-turn chat message and receive a response with source citations.
- **Alert_Check_Flow**: Submit a patient profile + antibiotic and receive safety alerts (allergy, contraindication, interaction).
- **Seed_Script**: The `scripts/seed.py` script that creates default users and data in the database.
- **RBAC**: Role-Based Access Control — `medecin`, `pharmacien`, `admin` roles with distinct permissions.

---

## Requirements

### Requirement 1: Backend Testcontainers Infrastructure

**User Story:** As a backend developer, I want a shared pytest fixture that starts real MongoDB and LocalStack containers, so that integration tests run against real infrastructure without manual setup.

#### Acceptance Criteria

1. THE Test_Suite SHALL provide a session-scoped pytest fixture named `real_db` that starts a `mongodb/mongodb-atlas-local` Docker container via Testcontainers before any integration test runs and stops it after all integration tests complete.
2. THE Test_Suite SHALL provide a session-scoped pytest fixture named `real_s3` that starts a LocalStack Docker container via Testcontainers and creates the configured S3 bucket before any integration test runs.
3. WHEN the `real_db` fixture is active, THE Test_Suite SHALL seed the database with at least one `medecin` user and one `admin` user using the same password-hashing logic as the production Seed_Script.
4. WHEN the `real_s3` fixture is active, THE Test_Suite SHALL configure the boto3 client endpoint to point to the LocalStack container URL.
5. THE Test_Suite SHALL place all Testcontainers-based integration tests under `backend/tests/integration/` and mark them with a `pytest.mark.integration` marker so they can be run independently from unit tests.
6. IF Docker is unavailable in the test environment, THEN THE Test_Suite SHALL skip all `pytest.mark.integration` tests with a descriptive skip message rather than failing.

---

### Requirement 2: Backend E2E Auth Integration Tests

**User Story:** As a backend developer, I want E2E integration tests for the Auth_Flow and Refresh_Flow against a real MongoDB container, so that JWT issuance, storage, and invalidation are verified end-to-end.

#### Acceptance Criteria

1. WHEN a valid login request is submitted against the real database, THE E2E_Backend_Test SHALL assert that the response contains `access_token`, `token_type`, and `expires_in`.
2. WHEN a login succeeds, THE E2E_Backend_Test SHALL assert that an audit log entry with `action = "login"` is persisted in the real MongoDB_Container.
3. WHEN a logout request is submitted with a valid access token, THE E2E_Backend_Test SHALL assert that the token is invalidated and a subsequent request with the same token returns HTTP 401.
4. WHEN an access token has expired and a valid refresh token is submitted, THE E2E_Backend_Test SHALL assert that a new access token is returned with a future expiry.
5. WHEN an invalid refresh token is submitted, THE E2E_Backend_Test SHALL assert that the response is HTTP 401.
6. WHEN a login attempt is made with incorrect credentials against the real database, THE E2E_Backend_Test SHALL assert that the response is HTTP 401 and no audit log entry is created for that attempt.

---

### Requirement 3: Backend E2E Patient CRUD Integration Tests

**User Story:** As a backend developer, I want E2E integration tests for Patient_CRUD against a real MongoDB container, so that persistence, retrieval, and update operations are verified end-to-end.

#### Acceptance Criteria

1. WHEN a `medecin` user creates a patient via `POST /api/v1/patients`, THE E2E_Backend_Test SHALL assert that the patient is persisted in the MongoDB_Container and the response contains the assigned `_id`.
2. WHEN a patient is created and then retrieved via `GET /api/v1/patients/{id}`, THE E2E_Backend_Test SHALL assert that all submitted fields are returned unchanged (round-trip property).
3. WHEN a patient is updated via `PUT /api/v1/patients/{id}`, THE E2E_Backend_Test SHALL assert that the updated fields are reflected in a subsequent `GET /api/v1/patients/{id}` response.
4. WHEN `GET /api/v1/patients` is called, THE E2E_Backend_Test SHALL assert that the response list contains only patients belonging to the authenticated user's scope.
5. WHEN a `pharmacien` user attempts to create a patient, THE E2E_Backend_Test SHALL assert that the response is HTTP 403.
6. FOR ALL valid patient payloads, creating then fetching the patient SHALL return an object equivalent to the submitted payload (round-trip property).

---

### Requirement 4: Backend E2E Diagnose and Prescription Integration Tests

**User Story:** As a backend developer, I want E2E integration tests for the Diagnose_Flow and Prescription_Flow against a real database, so that the full diagnostic pipeline is verified without mocks.

#### Acceptance Criteria

1. WHEN a symptom list is submitted to `POST /api/v1/diagnose/symptoms` with the LLM service stubbed at the HTTP boundary via `respx.mock`, THE E2E_Backend_Test SHALL assert that the response contains at least 3 differential diagnoses each with a `probability` between 0.0 and 1.0 and a non-empty `icd_code`.
2. WHEN a prescription request is submitted for a patient with a known allergy to the prescribed antibiotic, THE E2E_Backend_Test SHALL assert that the response contains at least one alert with `level = "critical"` and `type = "allergy"` and a non-null `alternative`.
3. WHEN a prescription request is submitted for a child patient with a fluoroquinolone antibiotic, THE E2E_Backend_Test SHALL assert that the response contains at least one alert with `level = "critical"` and `type = "contraindication"`.
4. WHEN a prescription request is submitted for a patient with renal failure, THE E2E_Backend_Test SHALL assert that the prescribed `dose_mg` is reduced relative to the standard adult dose.
5. WHEN a diagnose session is created, THE E2E_Backend_Test SHALL assert that `GET /api/v1/diagnose/session/{session_id}` returns the same diagnoses that were returned in the original response (round-trip property).

---

### Requirement 5: Backend E2E File Upload Integration Tests

**User Story:** As a backend developer, I want E2E integration tests for the File_Upload_Flow against a real LocalStack S3 container, so that file storage and retrieval are verified end-to-end.

#### Acceptance Criteria

1. WHEN a valid PDF file is uploaded via `POST /api/v1/files/upload`, THE E2E_Backend_Test SHALL assert that the file is stored in the LocalStack_Container S3 bucket and the response contains a `file_id`.
2. WHEN a file is uploaded and then retrieved via `GET /api/v1/files/{file_id}`, THE E2E_Backend_Test SHALL assert that the returned file content is byte-for-byte identical to the uploaded content (round-trip property).
3. WHEN a file type that is not in the allowed list (PDF, image, CSV) is uploaded, THE E2E_Backend_Test SHALL assert that the response is HTTP 422.
4. WHEN a file upload is performed by an unauthenticated user, THE E2E_Backend_Test SHALL assert that the response is HTTP 401.
5. WHEN a document is uploaded via `POST /api/v1/documents/upload` by an `admin` user, THE E2E_Backend_Test SHALL assert that the document metadata is persisted in the MongoDB_Container.

---

### Requirement 6: Backend E2E RAG Chat Integration Tests

**User Story:** As a backend developer, I want E2E integration tests for the RAG_Chat_Flow with the LLM stubbed at the HTTP boundary, so that message routing, history persistence, and citation formatting are verified.

#### Acceptance Criteria

1. WHEN a chat message is submitted to `POST /api/v1/chat/message` with the LLM endpoint stubbed via `respx.mock`, THE E2E_Backend_Test SHALL assert that the response contains a non-empty `answer` and a `sources` list.
2. WHEN multiple messages are sent in the same session, THE E2E_Backend_Test SHALL assert that `GET /api/v1/chat/history/{session_id}` returns all messages in chronological order.
3. WHEN a chat message is submitted, THE E2E_Backend_Test SHALL assert that the message and response are persisted in the MongoDB_Container.
4. WHEN a chat request is submitted by an unauthenticated user, THE E2E_Backend_Test SHALL assert that the response is HTTP 401.

---

### Requirement 7: Frontend Web Page-Level Tests

**User Story:** As a frontend developer, I want page-level tests for each major Next.js route, so that full page rendering, data loading states, and user interactions are verified beyond isolated component tests.

#### Acceptance Criteria

1. THE Page_Test for the login page SHALL assert that the email and password fields are rendered, that submitting valid credentials calls the auth API, and that the user is redirected on success.
2. THE Page_Test for the login page SHALL assert that submitting invalid credentials displays an error message without redirecting.
3. THE Page_Test for the patients list page SHALL assert that the page renders a loading skeleton while data is being fetched and then renders patient cards once data resolves.
4. THE Page_Test for the patients list page SHALL assert that an empty state component is rendered when the API returns an empty list.
5. THE Page_Test for the patient detail page SHALL assert that the patient's name, weight, allergies, and consultation history are rendered.
6. THE Page_Test for the diagnose page SHALL assert that submitting a symptom list triggers the diagnose API call and renders the returned differential diagnoses.
7. THE Page_Test for the diagnose page SHALL assert that prescription alerts with `level = "critical"` are rendered with a visually distinct style (e.g., a `data-severity="critical"` attribute or equivalent).
8. THE Page_Test for the chat page SHALL assert that sending a message appends it to the conversation and renders the assistant's response with source citations.
9. WHEN a page requires authentication and no valid session exists, THE Page_Test SHALL assert that the middleware redirects to the login page.
10. WHERE the `admin` role is required, THE Page_Test SHALL assert that non-admin users see an access-denied state rather than the page content.

---

### Requirement 8: Frontend Web API Route Tests

**User Story:** As a frontend developer, I want integration tests for Next.js API route handlers, so that cookie management, token forwarding, and error propagation are verified without a running server.

#### Acceptance Criteria

1. THE API_Route_Test for `POST /api/auth/set-cookie` SHALL assert that a valid token payload results in the `access_token` cookie being set with `HttpOnly` and `Secure` flags.
2. THE API_Route_Test for `POST /api/auth/set-cookie` SHALL assert that a missing or malformed payload returns HTTP 400.
3. WHEN the backend returns HTTP 401, THE API_Route_Test SHALL assert that the Next.js API route propagates a 401 response to the client rather than a 500.
4. WHEN the backend returns HTTP 403, THE API_Route_Test SHALL assert that the Next.js API route propagates a 403 response to the client.
5. THE API_Route_Test SHALL mock the backend HTTP calls using `msw` (Mock Service Worker) or equivalent request interception so no real network calls are made.

---

### Requirement 9: Mobile Screen-Level Integration Tests

**User Story:** As a mobile developer, I want screen-level integration tests for the key Expo screens, so that rendering, user interactions, and API calls are verified beyond isolated component tests.

#### Acceptance Criteria

1. THE Screen_Test for the login screen SHALL assert that entering valid credentials and pressing the login button calls the auth API and navigates to the main tab layout.
2. THE Screen_Test for the login screen SHALL assert that a failed login displays an error message on screen.
3. THE Screen_Test for the diagnose screen SHALL assert that entering symptoms and submitting renders a list of differential diagnoses with probability indicators.
4. THE Screen_Test for the diagnose screen SHALL assert that a critical prescription alert is rendered with a visually distinct indicator (e.g., a `testID` of `"alert-critical"`).
5. THE Screen_Test for the patients list screen SHALL assert that the screen renders a `MobilePatientCard` for each patient returned by the API.
6. THE Screen_Test for the patients list screen SHALL assert that an empty state is rendered when the API returns an empty list.
7. THE Screen_Test for the patient detail screen SHALL assert that the patient's name, weight, and allergy list are rendered.
8. THE Screen_Test for the chat screen SHALL assert that sending a message appends it to the conversation view and renders the assistant's reply with a `MobileSourceCitation`.
9. THE Screen_Test for the profile screen SHALL assert that the authenticated user's name and role are displayed.
10. WHEN the user is not authenticated, THE Screen_Test SHALL assert that the app navigates to the login screen rather than rendering a protected screen.

---

### Requirement 10: Mobile Navigation Flow Tests

**User Story:** As a mobile developer, I want navigation flow tests that verify Expo Router transitions between screens, so that RBAC-gated routes and deep links behave correctly.

#### Acceptance Criteria

1. WHEN a `medecin` user is authenticated, THE Navigation_Test SHALL assert that the tab bar renders the Diagnose, Patients, Chat, and Profile tabs.
2. WHEN a `pharmacien` user is authenticated, THE Navigation_Test SHALL assert that the Patients tab is not accessible and navigating to it redirects to an access-denied screen.
3. WHEN an unauthenticated user attempts to access any protected tab, THE Navigation_Test SHALL assert that the app redirects to the login screen.
4. WHEN the user navigates from the patients list to a patient detail screen, THE Navigation_Test SHALL assert that the correct patient `id` is passed as a route parameter.

---

### Requirement 11: Mobile API Hook Tests

**User Story:** As a mobile developer, I want unit tests for the API hooks and service utilities used by mobile screens, so that data fetching, error handling, and token refresh logic are verified in isolation.

#### Acceptance Criteria

1. THE Test_Suite SHALL test the `AuthContext` token refresh logic: WHEN the access token is expired and a valid refresh token exists, THE AuthContext SHALL obtain a new access token without requiring the user to log in again.
2. WHEN the refresh token is also expired or invalid, THE AuthContext SHALL clear the session and navigate the user to the login screen.
3. THE Test_Suite SHALL assert that API calls made from mobile hooks include the `Authorization: Bearer <token>` header.
4. WHEN an API call returns HTTP 401, THE Test_Suite SHALL assert that the mobile API client attempts a token refresh before retrying the original request.
5. FOR ALL probability values returned by the diagnose API, THE Test_Suite SHALL assert that `probabilityColor(p)` returns a non-empty string for any `p` in `[0.0, 1.0]` (property-based test using fast-check or equivalent).

---

### Requirement 12: Test Infrastructure and CI Integration

**User Story:** As a developer, I want the new tests to be runnable in CI with clear separation between fast unit tests and slower integration tests, so that feedback loops remain short.

#### Acceptance Criteria

1. THE Test_Suite SHALL allow running only backend unit and property-based tests via `pytest -m "not integration"` without requiring Docker.
2. THE Test_Suite SHALL allow running only backend integration tests via `pytest -m integration`, which requires Docker to be available.
3. THE Test_Suite SHALL allow running only frontend web tests via `npx vitest --run` from `apps/web/`.
4. THE Test_Suite SHALL allow running only mobile tests via `npx jest --passWithNoTests` from `apps/mobile/`.
5. WHEN a Testcontainers-based test fails due to a container startup timeout, THE Test_Suite SHALL report the failure with a message that includes the container image name and the timeout duration.
6. THE Test_Suite SHALL not introduce any test that requires a running Diagno-Pilot application server (i.e., all tests must be self-contained).
7. THE Test_Suite SHALL use `respx` as the sole HTTP stubbing library for intercepting outbound `httpx` calls in backend integration tests; no test SHALL allow real network calls to LLM or embedding endpoints.
