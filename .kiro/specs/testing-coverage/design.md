# Design Document: Testing Coverage Expansion

## Overview

This document describes the technical design for expanding automated test coverage across all three layers of the Diagno-Pilot stack: the Python/FastAPI backend, the Next.js web frontend, and the React Native/Expo mobile app.

The existing test suite already has solid unit and property-based coverage at the service and model level (pytest + Hypothesis on the backend, Vitest + fast-check on the web). The gaps are:

- **Backend**: No tests run against real infrastructure. All current tests mock MongoDB and S3. A new `tests/integration/` layer using Testcontainers will close this gap.
- **Web frontend**: Tests exist for components, contexts, and middleware logic, but no page-level rendering tests or API route handler tests.
- **Mobile**: Only a handful of component and utility tests exist. Screen-level, navigation, and API hook tests are missing.

The design preserves the existing test structure and adds new layers on top without modifying existing tests.

---

## Architecture

The test architecture follows a layered model with clear separation between fast unit/property tests and slower infrastructure-dependent integration tests.

```mermaid
graph TD
    subgraph Backend
        U[Unit Tests<br/>backend/tests/test_*.py]
        P[Property Tests<br/>backend/tests/test_*_property.py]
        I[Integration Tests<br/>backend/tests/integration/test_*.py]
        U --> |pytest -m not integration| CI_Fast
        P --> |pytest -m not integration| CI_Fast
        I --> |pytest -m integration| CI_Slow
    end

    subgraph Web
        WC[Component Tests<br/>src/components/__tests__/]
        WP[Page Tests<br/>src/app/[locale]/__tests__/]
        WA[API Route Tests<br/>src/app/api/__tests__/]
        WC --> |npx vitest --run| CI_Web
        WP --> |npx vitest --run| CI_Web
        WA --> |npx vitest --run| CI_Web
    end

    subgraph Mobile
        MS[Screen Tests<br/>app/(tabs)/__tests__/]
        MN[Navigation Tests<br/>app/__tests__/]
        MH[Hook Tests<br/>src/contexts/__tests__/]
        MS --> |npx jest --passWithNoTests| CI_Mobile
        MN --> |npx jest --passWithNoTests| CI_Mobile
        MH --> |npx jest --passWithNoTests| CI_Mobile
    end

    subgraph Infrastructure
        TC[Testcontainers]
        MDB[MongoDB Atlas Local<br/>Docker Container]
        LS[LocalStack S3<br/>Docker Container]
        TC --> MDB
        TC --> LS
        I --> TC
    end
```

### Key Architectural Decisions

**Testcontainers over docker-compose for integration tests**: Testcontainers manages container lifecycle programmatically within pytest fixtures, so tests are fully self-contained and portable. No external `docker-compose up` step is needed.

**`respx` for HTTP stubbing in backend integration tests**: The backend uses `httpx` for all outbound calls (LLM, embedding services). `respx` intercepts at the transport layer, so integration tests exercise the full FastAPI request/response cycle including real MongoDB and S3, while keeping LLM calls deterministic.

**`msw` for HTTP stubbing in web API route tests**: Next.js API route handlers are tested by calling them directly (no HTTP server). `msw` intercepts the fetch calls they make to the backend, keeping tests fast and deterministic.

**`fast-check` for property-based tests on web and mobile**: Already present in both `apps/web/package.json` and `apps/mobile/package.json`. No new dependency needed.

**Session-scoped fixtures for containers**: Starting a Docker container takes several seconds. Session-scoped fixtures start each container once per `pytest` invocation and share it across all integration tests, keeping the integration suite fast.

---

## Components and Interfaces

### Backend: Testcontainers Infrastructure

**New files:**
- `backend/tests/integration/__init__.py`
- `backend/tests/integration/conftest.py` — session-scoped `real_db` and `real_s3` fixtures
- `backend/tests/integration/test_auth_e2e.py`
- `backend/tests/integration/test_patients_e2e.py`
- `backend/tests/integration/test_diagnose_e2e.py`
- `backend/tests/integration/test_files_e2e.py`
- `backend/tests/integration/test_chat_e2e.py`

**`conftest.py` fixture interface:**

```python
# Session-scoped: starts once, shared across all integration tests
@pytest.fixture(scope="session")
def real_db() -> Generator[AsyncIOMotorDatabase, None, None]:
    """Starts mongodb/mongodb-atlas-local via Testcontainers, seeds users, yields db."""

@pytest.fixture(scope="session")
def real_s3() -> Generator[boto3.client, None, None]:
    """Starts LocalStack via Testcontainers, creates S3 bucket, yields boto3 client."""

@pytest.fixture(scope="session")
def integration_app(real_db, real_s3) -> FastAPI:
    """Returns the FastAPI app with db/s3 overrides pointing to real containers."""
```

**Docker availability guard:**

```python
def pytest_collection_modifyitems(items, config):
    if not _docker_available():
        skip = pytest.mark.skip(reason="Docker unavailable — skipping integration tests")
        for item in items:
            if item.get_closest_marker("integration"):
                item.add_marker(skip)
```

**`pytest.ini` additions:**

```ini
markers =
    integration: marks tests as requiring Docker (deselect with -m "not integration")
```

### Backend: `respx` HTTP Stubbing Pattern

All integration tests that exercise the diagnose or RAG chat flows stub LLM/embedding calls at the `httpx` transport layer:

```python
import respx
import httpx

@pytest.mark.integration
@respx.mock
async def test_diagnose_e2e(integration_client, real_db):
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={"choices": [{"message": {"content": STUB_DIAGNOSES_JSON}}]})
    )
    # ... test body
```

### Web Frontend: Page-Level Tests

**New files:**
- `apps/web/src/app/[locale]/login/__tests__/page.test.tsx`
- `apps/web/src/app/[locale]/patients/__tests__/page.test.tsx`
- `apps/web/src/app/[locale]/patients/__tests__/[id].test.tsx`
- `apps/web/src/app/[locale]/diagnose/__tests__/page.test.tsx`
- `apps/web/src/app/[locale]/chat/__tests__/page.test.tsx`

**Pattern**: Each page test renders the page component with `@testing-library/react`, mocks the API client from `@diagno-pilot/api-client`, and asserts on rendered output and user interactions.

```typescript
// Example pattern for page tests
import { render, screen, waitFor } from '@testing-library/react';
import { vi } from 'vitest';
import * as apiClient from '@diagno-pilot/api-client';

vi.mock('@diagno-pilot/api-client');

describe('PatientsPage', () => {
  it('renders loading skeleton then patient cards', async () => {
    vi.mocked(apiClient.getPatients).mockResolvedValue({ items: mockPatients, total: 2 });
    render(<PatientsPage />);
    expect(screen.getByTestId('skeleton-loader')).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByTestId('patient-card')).toHaveLength(2));
  });
});
```

### Web Frontend: API Route Tests

**New files:**
- `apps/web/src/app/api/auth/__tests__/set-cookie.test.ts`
- `apps/web/src/app/api/auth/__tests__/proxy.test.ts`

**Pattern**: Import the route handler directly, construct a `NextRequest`, call the handler, assert on the `NextResponse`.

```typescript
import { POST } from '../set-cookie/route';
import { NextRequest } from 'next/server';

it('sets HttpOnly Secure cookie for valid payload', async () => {
  const req = new NextRequest('http://localhost/api/auth/set-cookie', {
    method: 'POST',
    body: JSON.stringify({ access_token: 'valid.jwt.token' }),
  });
  const res = await POST(req);
  expect(res.status).toBe(200);
  const setCookie = res.headers.get('set-cookie');
  expect(setCookie).toContain('HttpOnly');
  expect(setCookie).toContain('Secure');
});
```

### Mobile: Screen-Level Tests

**New files:**
- `apps/mobile/app/(tabs)/__tests__/diagnose.test.tsx`
- `apps/mobile/app/(tabs)/__tests__/patients.test.tsx`
- `apps/mobile/app/(tabs)/__tests__/chat.test.tsx`
- `apps/mobile/app/(tabs)/__tests__/profile.test.tsx`
- `apps/mobile/app/patient/__tests__/[id].test.tsx`
- `apps/mobile/app/__tests__/navigation.test.tsx`
- `apps/mobile/src/contexts/__tests__/AuthContext.test.tsx`

**Pattern**: Use `@testing-library/react-native` with `renderRouter` from `expo-router/testing-library` for navigation tests. Mock the API client and `AuthContext`.

```typescript
import { render, screen, fireEvent } from '@testing-library/react-native';
import { renderRouter } from 'expo-router/testing-library';

describe('DiagnoseScreen', () => {
  it('renders diagnoses after symptom submission', async () => {
    mockApiClient.diagnose.mockResolvedValue({ diagnoses: mockDiagnoses });
    render(<DiagnoseScreen />);
    fireEvent.changeText(screen.getByTestId('symptom-input'), 'fever');
    fireEvent.press(screen.getByTestId('submit-button'));
    await waitFor(() => expect(screen.getAllByTestId('diagnosis-item')).toHaveLength(3));
  });
});
```

---

## Data Models

### Testcontainers Fixture State

The integration `conftest.py` manages the following state across the test session:

```python
@dataclass
class IntegrationState:
    mongo_container: MongoDbContainer      # testcontainers.mongodb.MongoDbContainer
    localstack_container: LocalStackContainer  # testcontainers.localstack.LocalStackContainer
    mongo_uri: str                          # e.g. "mongodb://localhost:27017"
    s3_endpoint_url: str                    # e.g. "http://localhost:4566"
    seeded_users: dict[str, dict]           # {"medecin": {...}, "admin": {...}}
```

### Seeded User Schema (matches production `scripts/seed.py`)

```python
{
    "_id": ObjectId,
    "email": str,           # "medecin@test.local" | "admin@test.local"
    "password_hash": str,   # bcrypt hash of "TestPassword123!"
    "role": str,            # "medecin" | "admin"
    "full_name": str,
    "locale": "fr",
    "created_at": datetime,
    "last_login": None,
}
```

### Web Page Test Mock Shape

Page tests mock the `@diagno-pilot/api-client` module. The mock shape mirrors the types from `packages/types/`:

```typescript
// Patient list mock
{ items: Patient[], total: number, page: number, page_size: number }

// Diagnose response mock
{ session_id: string, diagnoses: DifferentialDiagnosis[] }

// Prescription response mock
{ prescription: Prescription, alerts: Alert[] }
```

### Mobile Test Mock Shape

Mobile screen tests mock the API client and `AuthContext`:

```typescript
// AuthContext mock
{ user: { id: string, role: string, full_name: string } | null, token: string | null }

// API hook mock (jest.fn())
mockUsePatients.mockReturnValue({ data: Patient[], isLoading: false, error: null })
```

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Logout invalidates token (round-trip)

*For any* valid access token, after a successful logout request using that token, a subsequent authenticated request using the same token SHALL return HTTP 401.

**Validates: Requirements 2.3**

---

### Property 2: Patient create/fetch round-trip

*For any* valid patient payload submitted by a `medecin` user, creating the patient and then fetching it by the returned `_id` SHALL return an object with all submitted fields equal to the original values.

**Validates: Requirements 3.2, 3.6**

---

### Property 3: Patient list scope isolation

*For any* two distinct authenticated users, the patient list returned for user A SHALL NOT contain any patient created by user B.

**Validates: Requirements 3.4**

---

### Property 4: Patient update reflected in fetch (round-trip)

*For any* existing patient and any valid update payload, updating the patient and then fetching it SHALL return a response where all updated fields equal the values in the update payload.

**Validates: Requirements 3.3**

---

### Property 5: Diagnose response structure

*For any* non-empty symptom list submitted to the diagnose endpoint (with LLM stubbed), the response SHALL contain at least 3 differential diagnoses, each with a `probability` in `[0.0, 1.0]` and a non-empty `icd_code`.

**Validates: Requirements 4.1**

---

### Property 6: Diagnose session round-trip

*For any* diagnose session created via `POST /api/v1/diagnose/symptoms`, fetching the session via `GET /api/v1/diagnose/session/{session_id}` SHALL return a diagnoses list equivalent to the one returned in the original response.

**Validates: Requirements 4.5**

---

### Property 7: File upload/download round-trip

*For any* file with an allowed MIME type (PDF, image, CSV), uploading it and then downloading it via the returned `file_id` SHALL return bytes that are byte-for-byte identical to the uploaded content.

**Validates: Requirements 5.2**

---

### Property 8: Disallowed file types rejected

*For any* file whose MIME type is not in the allowed list (PDF, image, CSV), uploading it SHALL return HTTP 422.

**Validates: Requirements 5.3**

---

### Property 9: Chat history ordering

*For any* sequence of N messages sent in the same chat session, `GET /api/v1/chat/history/{session_id}` SHALL return exactly N messages in the same chronological order they were sent.

**Validates: Requirements 6.2**

---

### Property 10: Patient detail page renders all required fields

*For any* patient object with non-null `full_name`, `weight_kg`, `allergies`, and `consultation_history`, the rendered patient detail page SHALL contain elements displaying each of those fields.

**Validates: Requirements 7.5**

---

### Property 11: Critical alerts rendered with distinct style

*For any* prescription alert with `level = "critical"`, the rendered diagnose page element for that alert SHALL have a `data-severity="critical"` attribute (or equivalent testable marker).

**Validates: Requirements 7.7**

---

### Property 12: Unauthenticated web requests redirected to login

*For any* protected Next.js route, a request without a valid session token SHALL result in a redirect to the `/{locale}/login` path.

**Validates: Requirements 7.9**

---

### Property 13: Non-admin users see access-denied on admin pages

*For any* user with a role other than `admin`, accessing an admin-gated page SHALL render an access-denied state rather than the page content.

**Validates: Requirements 7.10**

---

### Property 14: Malformed set-cookie payload returns HTTP 400

*For any* request to `POST /api/auth/set-cookie` with a missing or malformed body (no `access_token` field, wrong type, etc.), the response SHALL be HTTP 400.

**Validates: Requirements 8.2**

---

### Property 15: Critical mobile alerts rendered with correct testID

*For any* prescription alert with `level = "critical"`, the rendered mobile diagnose screen element for that alert SHALL have `testID="alert-critical"`.

**Validates: Requirements 9.4**

---

### Property 16: Mobile patient list renders one card per patient

*For any* list of N patients returned by the API, the patients list screen SHALL render exactly N `MobilePatientCard` components.

**Validates: Requirements 9.5**

---

### Property 17: Mobile patient detail renders required fields

*For any* patient object with non-null `full_name`, `weight_kg`, and `allergies`, the rendered mobile patient detail screen SHALL contain elements displaying each of those fields.

**Validates: Requirements 9.7**

---

### Property 18: Mobile profile screen displays user name and role

*For any* authenticated user with a non-null `full_name` and `role`, the profile screen SHALL display both values.

**Validates: Requirements 9.9**

---

### Property 19: Unauthenticated mobile users redirected to login

*For any* protected mobile screen, when the `AuthContext` has no valid session, the app SHALL navigate to the login screen rather than rendering the protected content.

**Validates: Requirements 9.10, 10.3**

---

### Property 20: Mobile API calls include Authorization header

*For any* API call made from a mobile hook when a valid token is present in `AuthContext`, the outbound request SHALL include an `Authorization: Bearer <token>` header.

**Validates: Requirements 11.3**

---

### Property 21: `probabilityColor` returns non-empty string for all valid probabilities

*For any* probability value `p` in `[0.0, 1.0]`, `probabilityColor(p)` SHALL return a non-empty string.

**Validates: Requirements 11.5**

---

### Property 22: Navigation passes correct patient id as route parameter

*For any* patient in the patients list, tapping on that patient's card and navigating to the detail screen SHALL result in the route parameter `id` equaling that patient's `_id`.

**Validates: Requirements 10.4**

---

## Error Handling

### Container Startup Failures

If a Testcontainers container fails to start (timeout, Docker unavailable, image pull failure), the fixture SHALL:
1. Catch the exception
2. If Docker is unavailable: skip all `pytest.mark.integration` tests with message `"Docker unavailable — skipping integration tests (image: {image_name})"`
3. If Docker is available but container fails: re-raise with a message including the container image name and the timeout duration (e.g., `"Container mongodb/mongodb-atlas-local failed to start within 60s"`)

```python
import docker
from testcontainers.core.exceptions import ContainerStartException

def _docker_available() -> bool:
    try:
        docker.from_env().ping()
        return True
    except Exception:
        return False
```

### `respx` Unmatched Requests

All backend integration tests that use `respx.mock` SHALL configure `respx` in strict mode (`assert_all_called=False`, `assert_all_mocked=True`). Any outbound `httpx` request not matched by a stub will raise `respx.MockNotFoundError`, preventing accidental real network calls.

### Web API Route Error Propagation

Next.js API route handlers SHALL propagate backend HTTP error status codes (4xx, 5xx) directly to the client. They SHALL NOT swallow errors and return 500 when the backend returns a specific 4xx code. The proxy pattern:

```typescript
const backendRes = await fetch(backendUrl, { ... });
if (!backendRes.ok) {
  return NextResponse.json(await backendRes.json(), { status: backendRes.status });
}
```

### Mobile Auth Error Handling

The `AuthContext` token refresh logic SHALL follow this error handling flow:
1. On 401 from any API call: attempt token refresh using the stored refresh token
2. If refresh succeeds: retry the original request with the new token
3. If refresh fails (401/invalid): clear the session from `expo-secure-store` and navigate to login
4. All errors SHALL be caught and not propagate as unhandled promise rejections

---

## Testing Strategy

### Dual Testing Approach

Both unit/example tests and property-based tests are required. They are complementary:
- **Unit/example tests** verify specific scenarios, edge cases, and error conditions
- **Property-based tests** verify universal invariants across many generated inputs

### Backend

**Test runner**: `pytest` with `pytest-asyncio` (already configured in `pytest.ini`)

**Unit and property tests** (existing layer, no changes):
- Run with `pytest -m "not integration"` — no Docker required
- Hypothesis for property-based tests (already in `requirements-dev.txt`)

**Integration tests** (new layer):
- Run with `pytest -m integration` — requires Docker
- New dependencies to add to `requirements-dev.txt`:
  ```
  testcontainers[mongodb,localstack]>=4.8.0
  respx>=0.21.0
  ```
- Each integration test file imports fixtures from `tests/integration/conftest.py`
- LLM/embedding calls stubbed with `respx.mock` — no real network calls
- Property-based tests within the integration layer use Hypothesis with `@settings(max_examples=50)` (fewer examples due to container overhead)

**Property test configuration**:
- Minimum 100 iterations for unit-level property tests
- Minimum 50 iterations for integration-level property tests (container overhead)
- Tag format: `# Feature: testing-coverage, Property {N}: {property_text}`

### Web Frontend

**Test runner**: Vitest (already configured in `apps/web/vitest.config.ts`)

**Run command**: `npx vitest --run` from `apps/web/`

**New dependencies** (add to `apps/web/package.json` devDependencies):
```json
"msw": "^2.7.0",
"@next/test-utils": "^15.0.0"
```

**Page tests**:
- Use `@testing-library/react` with `jsdom` environment (already configured)
- Mock `@diagno-pilot/api-client` with `vi.mock()`
- Mock `next/navigation` (`useRouter`, `usePathname`) with `vi.mock()`
- Mock `next-intl` (`useTranslations`) with `vi.mock()`
- Property tests use `fast-check` (already in devDependencies)

**API route tests**:
- Import route handlers directly (no HTTP server)
- Use `msw` to intercept fetch calls to the backend
- Assert on `NextResponse` status, headers, and body

**Unit test focus**: specific rendering scenarios, loading states, error states, empty states
**Property test focus**: Properties 10–14 from the Correctness Properties section

### Mobile

**Test runner**: Jest with `jest-expo` preset (already configured in `apps/mobile/package.json`)

**Run command**: `npx jest --passWithNoTests` from `apps/mobile/`

**No new dependencies needed** — `@testing-library/react-native`, `fast-check`, and `expo-router/testing-library` are already present.

**Screen tests**:
- Use `@testing-library/react-native` `render` for isolated screen tests
- Use `renderRouter` from `expo-router/testing-library` for navigation tests
- Mock `AuthContext` with `jest.fn()` / `jest.spyOn()`
- Mock API client with `jest.mock('@diagno-pilot/api-client')`

**Navigation tests**:
- Use `renderRouter` with a mock file system to simulate Expo Router routes
- Assert on `screen.getByText` and navigation state

**Property tests**:
- Use `fast-check` (already in devDependencies)
- Minimum 100 iterations per property test
- Tag format: `// Feature: testing-coverage, Property {N}: {property_text}`

**Unit test focus**: specific screen interactions, error states, empty states, auth flows
**Property test focus**: Properties 15–22 from the Correctness Properties section

### CI Integration

```
# Fast feedback (no Docker required)
pytest -m "not integration"          # backend unit + property tests
npx vitest --run                     # web tests (from apps/web/)
npx jest --passWithNoTests           # mobile tests (from apps/mobile/)

# Full integration (requires Docker)
pytest -m integration                # backend E2E tests with real containers
```

Each property-based test MUST be implemented by a single test function referencing its design property via a comment tag. Example:

```python
# Feature: testing-coverage, Property 2: Patient create/fetch round-trip
@given(patient=patient_strategy())
@settings(max_examples=100)
@pytest.mark.integration
async def test_patient_round_trip(patient, integration_client, real_db):
    ...
```

```typescript
// Feature: testing-coverage, Property 21: probabilityColor returns non-empty string
it('returns non-empty string for all valid probabilities', () => {
  fc.assert(
    fc.property(fc.float({ min: 0.0, max: 1.0 }), (p) => {
      return probabilityColor(p).length > 0;
    }),
    { numRuns: 100 },
  );
});
```
