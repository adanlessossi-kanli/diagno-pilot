# Implementation Plan: Security Hardening

## Overview

Implement JWT cookie migration, CSRF protection, file validator hardening, and security headers across the FastAPI backend and Next.js frontend. Tasks are ordered so each step builds on the previous, with property-based tests placed immediately after the code they validate.

## Tasks

- [x] 1. Harden backend auth cookie issuance (`backend/routers/auth.py`, `backend/core/auth.py`)
  - [x] 1.1 Add `_generate_csrf_token()`, `_set_auth_cookies()`, and `_clear_auth_cookies()` helpers to `backend/routers/auth.py`
    - `_generate_csrf_token()` → `secrets.token_hex(32)`
    - `_set_auth_cookies(response, access_token, refresh_token, csrf_token)` sets all three `Set-Cookie` headers; omit `Secure` flag when `settings.ENV != "production"`
    - `_clear_auth_cookies(response)` sets all three cookies with `Max-Age=0`
    - _Requirements: 1.1, 1.2, 1.5, 1.8, 6.1, 7.3_
  - [x] 1.2 Update `POST /auth/login` to call `_set_auth_cookies()` and return slim `TokenResponse` (no token values in body)
    - Remove `access_token` and `refresh_token` from the JSON response body
    - _Requirements: 1.1, 1.2, 1.3_
  - [x] 1.3 Update `POST /auth/refresh` to read `refresh_token` from cookie, rotate all three cookies via `_set_auth_cookies()`, and return slim `TokenResponse`
    - Remove `RefreshRequest` body; read token from `request.cookies.get("refresh_token")`
    - Return HTTP 401 with `detail: "refresh_token_invalid"` and call `_clear_auth_cookies()` on failure
    - _Requirements: 1.6, 2.1, 2.2, 2.3, 7.1_
  - [x] 1.4 Update `POST /auth/logout` to call `_clear_auth_cookies()` including `csrf_token`
    - _Requirements: 1.5, 6.6_
  - [x] 1.5 Update `get_current_user` in `backend/core/auth.py` to fall back to `request.cookies.get("access_token")` when no `Authorization: Bearer` header is present
    - Keep `OAuth2PasswordBearer` scheme for mobile/direct API consumers
    - _Requirements: 1.4_
  - [x] 1.6 Write property tests for auth cookie behaviour (`backend/tests/test_auth_cookies.py`)
    - **Property 1: Login sets all auth cookies with correct attributes** — generate random valid users; assert `Set-Cookie` headers on login response include `access_token` (HttpOnly), `refresh_token` (HttpOnly), `csrf_token` (not HttpOnly), each with `SameSite=Strict` and correct `Max-Age` — **Validates: Requirements 1.1, 1.2, 6.1**
    - **Property 2: Tokens absent from login response body** — assert login JSON body lacks `access_token` and `refresh_token` keys — **Validates: Requirements 1.3**
    - **Property 3: Cookie-based auth grants access to protected endpoints** — generate valid tokens; assert protected endpoints accept cookie auth without `Authorization` header — **Validates: Requirements 1.4**
    - **Property 4: Logout clears all auth cookies** — assert logout response sets `Max-Age=0` on all three cookies — **Validates: Requirements 1.5, 6.6**
    - **Property 5: Refresh rotates all three cookies atomically** — assert refresh sets new cookies in a single response; assert old refresh token is revoked on second call — **Validates: Requirements 1.6, 2.1, 7.1**
    - **Property 6: Invalid refresh token returns 401 and clears cookies** — generate invalid/revoked/absent token values; assert HTTP 401 with `detail: "refresh_token_invalid"` and `Max-Age=0` on all cookies — **Validates: Requirements 2.2**

- [x] 2. Add CSRF protection middleware (`backend/core/csrf.py`, `backend/main.py`)
  - [x] 2.1 Create `backend/core/csrf.py` with `verify_csrf` FastAPI dependency
    - Skip validation for `GET`, `HEAD`, `OPTIONS` methods
    - Skip validation for paths `/api/v1/auth/login` and `/api/v1/auth/refresh`
    - Use `hmac.compare_digest(cookie_val, header_val)` for constant-time comparison
    - Raise `HTTPException(status_code=403, detail="csrf_token_invalid")` on mismatch or missing values
    - _Requirements: 6.3, 6.4, 6.5, 6.7_
  - [x] 2.2 Register `verify_csrf` globally in `backend/main.py` via `app.router.dependencies`
    - Add `from backend.core.csrf import verify_csrf` and append to `app.router.dependencies`
    - _Requirements: 6.5_
  - [x] 2.3 Write property tests for CSRF middleware (`backend/tests/test_csrf.py`)
    - **Property 11: CSRF middleware enforces token on all state-mutating endpoints** — generate random endpoint paths and mismatched token pairs; assert HTTP 403 with `detail: "csrf_token_invalid"`; assert matching pairs are not rejected — **Validates: Requirements 6.3, 6.4, 6.5**
    - **Property 12: CSRF token has sufficient entropy** — generate N tokens via `_generate_csrf_token()`; assert all have length ≥ 64 hex characters — **Validates: Requirements 7.3**

- [x] 3. Add security headers middleware (`backend/core/security_headers.py`, `backend/main.py`)
  - [x] 3.1 Create `backend/core/security_headers.py` with `SecurityHeadersMiddleware(BaseHTTPMiddleware)`
    - Always set `X-Content-Type-Options: nosniff` and `X-Frame-Options: DENY`
    - Set `Strict-Transport-Security: max-age=31536000; includeSubDomains` only when `settings.ENV == "production"`
    - _Requirements: 8.1, 8.2, 8.4_
  - [x] 3.2 Register `SecurityHeadersMiddleware` in `backend/main.py` before the CORS middleware
    - _Requirements: 8.1, 8.2, 8.4_
  - [x] 3.3 Write property tests for security headers (`backend/tests/test_security_headers.py`)
    - **Property 13: Security headers present on all API responses** — assert `X-Content-Type-Options: nosniff` and `X-Frame-Options: DENY` on responses from all registered routes; assert HSTS present when `settings.ENV == "production"` and absent otherwise — **Validates: Requirements 8.1, 8.2, 8.4**

- [x] 4. Checkpoint — Ensure all backend tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Harden file validator (`backend/core/file_validator.py`)
  - [x] 5.1 Increase `_MIME_PROBE_BYTES` from 2048 to 8192 and add `EXTENSION_MIME_MAP` canonical map
    - Map: `.pdf`→`application/pdf`, `.jpg`/`.jpeg`→`image/jpeg`, `.png`→`image/png`, `.csv`→`text/csv`, `.xlsx`→`application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
    - _Requirements: 4.1, 5.1_
  - [x] 5.2 Add `validate_not_empty(content)` — raise `HTTPException(400, "File is empty.")` when `len(content) == 0`
    - _Requirements: 4.7_
  - [x] 5.3 Add `validate_extension(filename, detected_mime)` — extract suffix, look up `EXTENSION_MIME_MAP`, reject with HTTP 415 if absent or mismatched; include declared extension and detected MIME in error detail
    - _Requirements: 4.3, 5.2, 5.3_
  - [x] 5.4 Add `validate_polyglot(content)` — check magic bytes against each allowed MIME type's known signatures; raise HTTP 415 if more than one signature matches
    - _Requirements: 4.4_
  - [x] 5.5 Add `validate_csv_content(content)` — decode as UTF-8, check for null bytes and non-printable characters; raise HTTP 415 on failure
    - _Requirements: 4.5_
  - [x] 5.6 Update `validate()` orchestrator to call all new validators in order; log rejections with detected type, declared type, filename, and client IP
    - _Requirements: 4.2, 4.6_
  - [x] 5.7 Write property tests for file validator (`backend/tests/test_file_validator.py`)
    - **Property 7: File validator rejects disallowed MIME types** — generate files with disallowed magic bytes; assert HTTP 415 and rejection log contains detected type, declared type, filename, client IP — **Validates: Requirements 4.1, 4.2**
    - **Property 8: File validator rejects extension/MIME mismatches** — generate mismatched (extension, content) pairs; assert HTTP 415 with declared extension and detected MIME in error detail — **Validates: Requirements 4.3, 5.1, 5.2, 5.3**
    - **Property 9: File validator rejects polyglot files** — construct synthetic polyglot byte sequences matching two or more allowed MIME signatures; assert HTTP 415 — **Validates: Requirements 4.4**
    - **Property 10: File validator rejects CSV files with null bytes or non-printable characters** — generate CSV content containing null bytes or control characters; assert HTTP 415 — **Validates: Requirements 4.5**

- [x] 6. Checkpoint — Ensure all backend tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Update API client (`packages/api-client/index.ts`)
  - [x] 7.1 Remove `getToken` parameter from `createApiClient` and remove `Authorization: Bearer` header injection from all internal `headers()` calls
    - _Requirements: 3.1_
  - [x] 7.2 Add `getCsrfToken()` helper that reads `csrf_token` from `document.cookie`; inject `X-CSRF-Token` header on all `POST`, `PUT`, `PATCH`, `DELETE` requests
    - _Requirements: 6.2_
  - [x] 7.3 Remove `access_token` and `refresh_token` fields from `LoginResponse` type
    - _Requirements: 1.3_
  - [x] 7.4 Write unit tests for API client CSRF injection (`packages/api-client/__tests__/`)
    - Verify `X-CSRF-Token` header is injected on mutating methods and absent on `GET`
    - Verify `getCsrfToken()` correctly parses edge cases: empty cookie string, multiple cookies, URL-encoded values
    - _Requirements: 6.2_

- [x] 8. Update Web_Client auth context (`apps/web/src/contexts/AuthContext.tsx`)
  - [x] 8.1 Remove `memoryTokenRef` and all `localStorage`/`sessionStorage` token reads and writes
    - _Requirements: 1.7, 3.3_
  - [x] 8.2 Remove calls to `/api/auth/set-cookie` BFF route from `login()` and all other methods
    - _Requirements: 3.1_
  - [x] 8.3 Update `login()` to call `POST /api/v1/auth/login` with `credentials: 'include'`, then call `GET /api/v1/auth/me` to populate `user` state
    - _Requirements: 3.1, 3.3_
  - [x] 8.4 Update `logout()` to call `POST /api/v1/auth/logout` with `credentials: 'include'` and clear local `user` state
    - _Requirements: 1.5_
  - [x] 8.5 Update `tryRefresh()` to call `POST /api/v1/auth/refresh` with `credentials: 'include'`, then re-call `GET /api/v1/auth/me` on success
    - _Requirements: 3.2, 7.2_
  - [x] 8.6 Update `fetchWithRefresh()` to remove `Authorization` header injection; keep 401 intercept → refresh → retry logic; on double-401 redirect to login
    - _Requirements: 3.2, 3.4_
  - [x] 8.7 Remove `getToken()` from context value
    - _Requirements: 1.7_
  - [x] 8.8 Write unit tests for AuthContext (`apps/web/src/contexts/__tests__/`)
    - Test 401 → refresh → retry flow
    - Test double-401 → redirect flow
    - _Requirements: 3.2, 3.4_

- [x] 9. Delete BFF set-cookie route and add CSP header
  - [x] 9.1 Delete `apps/web/src/app/api/auth/set-cookie/route.ts`
    - _Requirements: 3.1_
  - [x] 9.2 Add `headers()` export to `apps/web/next.config.ts` with `Content-Security-Policy` header restricting scripts to `'self'`
    - CSP value: `"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https://images.unsplash.com; connect-src 'self'; font-src 'self'; frame-ancestors 'none';"`
    - _Requirements: 8.3_

- [x] 10. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP
- Property tests use Hypothesis (Python) and fast-check (TypeScript)
- Each property test must include the comment: `# Feature: security-hardening, Property <N>: <property_text>`
- The `Secure` cookie flag is omitted when `settings.ENV != "production"` (Requirement 1.8)
- The `/api/auth/set-cookie` BFF route deletion in task 9.1 is a breaking change — complete tasks 7 and 8 first
