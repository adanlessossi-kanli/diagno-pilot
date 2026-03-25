# Design Document: African Image Representation

## Overview

This feature corrects two related issues in the Diagno-Pilot web application:

1. **Image registry gaps and mismatches** — The `IMAGES` constant in `apps/web/src/lib/images.ts` is missing the `loginSide` and `patientsEmpty` keys that page components already reference, and some existing entries may point to Unsplash photos that do not actually depict African subjects despite their alt-text claiming otherwise.

2. **API client missing `credentials: 'include'`** — The `get`, `post`, `put`, `del`, and `postForm` helpers in `packages/api-client/index.ts` do not forward httpOnly session cookies, causing `GET /api/v1/auth/me` to receive `ERR_EMPTY_RESPONSE` and silently log users out on page load.

Both issues are addressed with minimal, targeted changes: adding/updating entries in the image registry and adding `credentials: 'include'` to every `fetch` call in the API client.

---

## Architecture

The system follows a standard Next.js monorepo layout:

```
apps/web/src/
  lib/images.ts              ← Image_Registry (central source of truth)
  app/[locale]/
    page.tsx                 ← Homepage — consumes IMAGES.hero
    login/page.tsx           ← Login page — consumes IMAGES.loginSide
    diagnose/page.tsx        ← Diagnose page — consumes IMAGES.diagnoseHeader
    patients/page.tsx        ← Patients page — consumes IMAGES.patientsEmpty
  components/EmptyState.tsx  ← Renders image prop { src, alt }

packages/api-client/
  index.ts                   ← HTTP helpers (get, post, put, del, postForm)
```

The Image_Registry is the single source of truth for all image metadata. Page components import `IMAGES` and pass `IMAGES.<key>.src` and `IMAGES.<key>.alt` directly to Next.js `<Image>` components or to the `EmptyState` component's `image` prop.

The API client is a factory function (`createApiClient`) that closes over `get`, `post`, `put`, `del`, and `postForm` helpers. Adding `credentials: 'include'` to each helper ensures cookies are forwarded on every request without changing the public API surface.

```mermaid
graph TD
    LP[LoginPage] -->|IMAGES.loginSide| IR[Image Registry]
    HP[HomePage] -->|IMAGES.hero| IR
    DP[DiagnosePage] -->|IMAGES.diagnoseHeader| IR
    PP[PatientsPage] -->|IMAGES.patientsEmpty| IR
    PP -->|image prop| ES[EmptyState]
    ES -->|src, alt| NI[Next.js Image]
    IR -->|src URL| Unsplash[(Unsplash CDN)]

    AC[AuthContext] -->|auth.me()| API[API Client]
    API -->|fetch + credentials:include| BE[FastAPI Backend]
```

---

## Components and Interfaces

### Image Registry (`apps/web/src/lib/images.ts`)

The `ImageEntry` interface and `IMAGES` constant remain the public contract. No interface changes are needed — the fix is purely additive (new keys) and corrective (updated `src` URLs).

```typescript
interface ImageEntry {
  src: string;      // Unsplash URL with width/quality params
  alt: string;      // French alt text describing the African subject
  source: string;   // Unsplash page URL for attribution
  licence: string;  // Licence label
}

export const IMAGES: Record<string, ImageEntry> = { ... }
```

Keys required after this change:

| Key | Consumer | Status |
|---|---|---|
| `hero` | `page.tsx` | exists — verify photo |
| `loginSide` | `login/page.tsx` | **missing — must add** |
| `diagnoseHeader` | `diagnose/page.tsx` | exists — verify photo |
| `patientsEmpty` | `patients/page.tsx` via `EmptyState` | **missing — must add** |
| `consultation` | legacy / future | exists — preserve |
| `medecin` | legacy / future | exists — preserve |
| `infirmiere` | legacy / future | exists — preserve |
| `patient` | legacy / future | exists — preserve |
| `equipe` | legacy / future | exists — preserve |

### API Client (`packages/api-client/index.ts`)

The five internal helpers need `credentials: 'include'` added to their `fetch` calls:

```typescript
function get<T>(path, signal?) {
  return fetch(url, { method: 'GET', headers: headers(), credentials: 'include', signal })
    .then(parseResponse<T>);
}
// same pattern for post, put, del, postForm
```

No changes to the public API surface (`createApiClient`, method signatures, return types).

### Page Components

No changes required to page components. They already reference the correct `IMAGES` keys; the fix is in the registry itself.

### EmptyState Component

No changes required. It already accepts `image?: { src: string; alt: string }` and renders it correctly.

---

## Data Models

### ImageEntry

```typescript
interface ImageEntry {
  src: string;      // e.g. "https://images.unsplash.com/photo-<id>?w=800&q=80"
  alt: string;      // French description, e.g. "Médecin africain en consultation"
  source: string;   // e.g. "https://unsplash.com/photos/<id>"
  licence: string;  // e.g. "Unsplash Licence libre"
}
```

All four fields are required. TypeScript's structural typing enforces this at compile time — any object literal assigned to `ImageEntry` must include all four fields.

### IMAGES constant shape (after fix)

```typescript
export const IMAGES: Record<string, ImageEntry> = {
  hero:           { src, alt, source, licence },  // African medical professional
  loginSide:      { src, alt, source, licence },  // NEW — African healthcare scene
  diagnoseHeader: { src, alt, source, licence },  // African doctor at work
  patientsEmpty:  { src, alt, source, licence },  // NEW — African healthcare context
  consultation:   { src, alt, source, licence },  // preserved
  medecin:        { src, alt, source, licence },  // preserved
  infirmiere:     { src, alt, source, licence },  // preserved
  patient:        { src, alt, source, licence },  // preserved
  equipe:         { src, alt, source, licence },  // preserved
}
```


---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: All required keys exist in the Image Registry

*For any* snapshot of the `IMAGES` constant, the keys `hero`, `loginSide`, `diagnoseHeader`, and `patientsEmpty` must all be present and map to non-null objects.

**Validates: Requirements 1.2, 1.4, 8.1, 8.2**

### Property 2: All Image Registry entries have all required non-empty fields

*For any* entry in the `IMAGES` constant, the entry must have non-empty `src`, `alt`, `source`, and `licence` string fields.

**Validates: Requirements 1.3, 6.1, 7.1, 7.2, 7.3**

### Property 3: All legacy keys are preserved

*For any* version of the `IMAGES` constant, the keys `hero`, `consultation`, `medecin`, `infirmiere`, `patient`, `equipe`, and `diagnoseHeader` must all remain present and accessible.

**Validates: Requirements 1.5**

### Property 4: All API client fetch helpers include credentials

*For any* call to `get`, `post`, `put`, `del`, or `postForm` in the API client, the underlying `fetch` invocation must include `credentials: 'include'` in its options.

**Validates: Requirements 9.2, 9.3**

---

## Error Handling

### Missing Image Registry Keys

Before this fix, accessing `IMAGES.loginSide.src` or `IMAGES.patientsEmpty.src` throws `TypeError: Cannot read properties of undefined (reading 'src')` at runtime, crashing the login and patients pages respectively. The fix is purely additive — adding the missing keys eliminates the error path entirely.

TypeScript's type system provides compile-time safety: the `ImageEntry` interface requires all four fields, so any incomplete entry is a type error caught before deployment.

### API Client Cookie Forwarding

Without `credentials: 'include'`, the browser does not attach httpOnly cookies to cross-origin fetch requests. The backend receives no session cookie and either returns a 401 or drops the connection (`ERR_EMPTY_RESPONSE`). Adding `credentials: 'include'` to all helpers restores the expected behavior.

The existing 401 handling in `AuthContext` is correct: a 401 from `auth/me` sets `user` to `null` and redirects to login. This path is preserved and tested.

### Unsplash Image Loading Failures

Next.js `<Image>` components handle network failures gracefully — a broken `src` URL renders a broken image placeholder rather than crashing the page. The `alt` text is displayed by assistive technologies regardless. No additional error handling is needed at the application layer.

---

## Testing Strategy

### Dual Testing Approach

Both unit tests and property-based tests are used:

- **Unit tests** verify specific examples: that each page component renders the correct image key, and that the 401 auth flow behaves correctly.
- **Property tests** verify universal structural invariants: that all required keys exist, all entries have all required fields, and all fetch helpers include `credentials: 'include'`.

### Property-Based Testing

**Library**: [fast-check](https://github.com/dubzzz/fast-check) (TypeScript/JavaScript)

Each property test runs a minimum of **100 iterations**.

Each test is tagged with a comment in the format:
`// Feature: african-image-representation, Property <N>: <property_text>`

**Property 1 test** — Verify all required keys exist:
```typescript
// Feature: african-image-representation, Property 1: All required keys exist in the Image Registry
it('IMAGES contains all required keys', () => {
  const requiredKeys = ['hero', 'loginSide', 'diagnoseHeader', 'patientsEmpty'];
  for (const key of requiredKeys) {
    expect(IMAGES[key]).toBeDefined();
    expect(typeof IMAGES[key]).toBe('object');
  }
});
```
(This is a deterministic structural check; no randomization needed — runs once.)

**Property 2 test** — Verify all entries have all required non-empty fields:
```typescript
// Feature: african-image-representation, Property 2: All Image Registry entries have all required non-empty fields
fc.assert(
  fc.property(fc.constantFrom(...Object.keys(IMAGES)), (key) => {
    const entry = IMAGES[key];
    expect(entry.src).toBeTruthy();
    expect(entry.alt).toBeTruthy();
    expect(entry.source).toBeTruthy();
    expect(entry.licence).toBeTruthy();
  }),
  { numRuns: 100 }
);
```

**Property 3 test** — Verify legacy keys are preserved:
```typescript
// Feature: african-image-representation, Property 3: All legacy keys are preserved
it('IMAGES preserves all legacy keys', () => {
  const legacyKeys = ['hero', 'consultation', 'medecin', 'infirmiere', 'patient', 'equipe', 'diagnoseHeader'];
  for (const key of legacyKeys) {
    expect(IMAGES[key]).toBeDefined();
  }
});
```

**Property 4 test** — Verify all fetch helpers include `credentials: 'include'`:
```typescript
// Feature: african-image-representation, Property 4: All API client fetch helpers include credentials
fc.assert(
  fc.property(fc.constantFrom('get', 'post', 'put', 'del', 'postForm'), async (method) => {
    const fetchSpy = jest.fn().mockResolvedValue(new Response('{}', { status: 200 }));
    global.fetch = fetchSpy;
    const client = createApiClient('http://localhost', () => null);
    // call each method with minimal valid args
    try { await (client as any)[method]?.('/test'); } catch {}
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({ credentials: 'include' })
    );
  }),
  { numRuns: 100 }
);
```

### Unit Tests

**Login page renders loginSide image** (validates Requirement 2.1):
```typescript
it('LoginPage renders IMAGES.loginSide', () => {
  render(<LoginPage />);
  const img = screen.getByRole('img');
  expect(img).toHaveAttribute('src', expect.stringContaining(IMAGES.loginSide.src));
});
```

**Homepage renders hero image** (validates Requirement 3.1):
```typescript
it('HomePage renders IMAGES.hero', () => {
  render(<HomePage />);
  const img = screen.getByRole('img');
  expect(img).toHaveAttribute('src', expect.stringContaining(IMAGES.hero.src));
});
```

**Diagnose page renders diagnoseHeader image** (validates Requirement 4.1):
```typescript
it('DiagnosePage renders IMAGES.diagnoseHeader', () => {
  render(<DiagnosePage />);
  const img = screen.getByRole('img');
  expect(img).toHaveAttribute('src', expect.stringContaining(IMAGES.diagnoseHeader.src));
});
```

**Patients page empty state renders patientsEmpty image** (validates Requirement 5.1):
```typescript
it('PatientsPage empty state renders IMAGES.patientsEmpty', () => {
  mockApiToReturnEmptyList();
  render(<PatientsPage />);
  const img = screen.getByRole('img');
  expect(img).toHaveAttribute('src', expect.stringContaining(IMAGES.patientsEmpty.src));
});
```

**401 from auth/me sets user to null** (validates Requirement 9.4):
```typescript
it('AuthContext sets user to null on 401 from auth/me', async () => {
  mockFetch(401, { detail: 'Unauthorized' });
  const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider });
  await waitFor(() => expect(result.current.isLoading).toBe(false));
  expect(result.current.user).toBeNull();
});
```
