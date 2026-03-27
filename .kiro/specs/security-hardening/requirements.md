# Requirements Document

## Introduction

This feature hardens the security posture of the Diagno-Pilot web application across three areas:

1. **JWT storage migration** — move access and refresh tokens from `localStorage` to `httpOnly` cookies on the Next.js frontend, eliminating XSS-based token theft in a medical context where PHI is at stake.
2. **Strict file upload validation** — augment the existing `FileValidator` with deep MIME-type sniffing (magic-byte inspection of the full allowed set, polyglot detection, and extension/MIME consistency checks) so that disguised malicious files cannot reach S3.
3. **CSRF protection** — add a double-submit-cookie CSRF defence to the Next.js App Router frontend and the FastAPI backend so that cross-origin forged requests cannot abuse the new cookie-based auth.

Mobile (React Native / Expo) already uses secure storage and is out of scope.

---

## Glossary

- **Auth_Service**: The FastAPI router at `backend/routers/auth.py` responsible for issuing, refreshing, and revoking JWT tokens.
- **File_Validator**: The Python module at `backend/core/file_validator.py` responsible for validating uploaded files before they reach S3.
- **Web_Client**: The Next.js (App Router) frontend application running in the user's browser.
- **API_Gateway**: The FastAPI application (`backend/main.py`) that receives all HTTP requests from the Web_Client.
- **CSRF_Middleware**: The server-side component (FastAPI middleware or dependency) that validates CSRF tokens on state-mutating requests.
- **CSRF_Token**: A cryptographically random, per-session value used to prevent cross-site request forgery.
- **httpOnly_Cookie**: An HTTP cookie with the `HttpOnly` flag set, inaccessible to JavaScript running in the browser.
- **Access_Token**: A short-lived JWT (15 minutes) used to authenticate API requests.
- **Refresh_Token**: A long-lived opaque token (7 days) used to obtain new Access_Tokens without re-authentication.
- **Magic_Bytes**: The leading bytes of a file that identify its true format, independent of the declared filename extension or `Content-Type` header.
- **Polyglot_File**: A file that is simultaneously valid in two different formats (e.g., a JPEG that is also a valid PDF), used to bypass MIME-type checks.
- **Allowed_MIME_Types**: The set of permitted MIME types: `application/pdf`, `image/jpeg`, `image/png`, `text/csv`, `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`.

---

## Requirements

### Requirement 1: JWT Access Token Delivered via httpOnly Cookie

**User Story:** As a security engineer, I want the Access_Token to be stored in an httpOnly cookie instead of localStorage, so that XSS attacks cannot steal JWT tokens and access patient health information.

#### Acceptance Criteria

1. WHEN a user successfully authenticates via `POST /api/v1/auth/login`, THE Auth_Service SHALL set an `httpOnly`, `Secure`, `SameSite=Strict` cookie named `access_token` containing the Access_Token, with a `Max-Age` equal to `JWT_EXPIRE_MINUTES * 60` seconds.
2. WHEN a user successfully authenticates via `POST /api/v1/auth/login`, THE Auth_Service SHALL set an `httpOnly`, `Secure`, `SameSite=Strict` cookie named `refresh_token` containing the Refresh_Token, with a `Max-Age` equal to `JWT_REFRESH_EXPIRE_DAYS * 86400` seconds.
3. THE Auth_Service SHALL NOT include the Access_Token or Refresh_Token in the JSON response body when the request originates from the Web_Client.
4. WHEN a request arrives at a protected endpoint, THE API_Gateway SHALL read the Access_Token from the `access_token` cookie when no `Authorization: Bearer` header is present.
5. WHEN a user calls `POST /api/v1/auth/logout`, THE Auth_Service SHALL clear the `access_token` and `refresh_token` cookies by setting them with `Max-Age=0`.
6. WHEN a user calls `POST /api/v1/auth/refresh`, THE Auth_Service SHALL rotate both cookies, issuing new `access_token` and `refresh_token` cookies with updated `Max-Age` values.
7. THE Web_Client SHALL NOT store the Access_Token or Refresh_Token in `localStorage` or `sessionStorage`.
8. WHERE the application is deployed in a non-HTTPS environment (development), THE Auth_Service SHALL omit the `Secure` flag on cookies to allow local testing.

---

### Requirement 2: Refresh Token Rotation via Cookie

**User Story:** As a security engineer, I want the Refresh_Token rotation to work transparently with cookies, so that token theft via network interception is mitigated through automatic rotation.

#### Acceptance Criteria

1. WHEN `POST /api/v1/auth/refresh` is called with a valid `refresh_token` cookie, THE Auth_Service SHALL revoke the presented Refresh_Token and issue a new Refresh_Token cookie.
2. IF the `refresh_token` cookie is absent or contains a revoked or expired token, THEN THE Auth_Service SHALL return HTTP 401 with detail `refresh_token_invalid` and clear both auth cookies.
3. THE Auth_Service SHALL complete the token rotation and set new cookies within a single atomic response, so that the browser never holds two valid Refresh_Tokens simultaneously.

---

### Requirement 3: Web Client Cookie-Based Auth Flow

**User Story:** As a frontend developer, I want the Web_Client to rely on cookies for auth state, so that no token-handling code exists in JavaScript where it is vulnerable to XSS.

#### Acceptance Criteria

1. THE Web_Client SHALL send all API requests with `credentials: 'include'` so that auth cookies are attached automatically by the browser.
2. WHEN the Web_Client receives HTTP 401 from a protected endpoint, THE Web_Client SHALL call `POST /api/v1/auth/refresh` with `credentials: 'include'` to attempt silent token renewal before redirecting to the login page.
3. THE Web_Client SHALL determine authentication state by calling `GET /api/v1/auth/me` rather than by reading token values from storage.
4. WHEN `GET /api/v1/auth/me` returns HTTP 401 and the refresh attempt also returns HTTP 401, THE Web_Client SHALL redirect the user to the login page and clear any local auth state.

---

### Requirement 4: Strict File MIME-Type Validation via Magic Bytes

**User Story:** As a security engineer, I want file uploads to be validated against their actual binary content, so that attackers cannot upload malicious files by renaming them with an allowed extension.

#### Acceptance Criteria

1. WHEN a file is uploaded to `POST /api/v1/files/upload`, THE File_Validator SHALL read at least the first 8192 bytes of the file to detect the MIME type using Magic_Bytes inspection.
2. IF the MIME type detected from Magic_Bytes is not in Allowed_MIME_Types, THEN THE File_Validator SHALL reject the file with HTTP 415 and log the detected type, declared type, filename, and client IP.
3. IF the file extension derived from the filename does not correspond to the detected MIME type according to the canonical extension map, THEN THE File_Validator SHALL reject the file with HTTP 415.
4. THE File_Validator SHALL detect Polyglot_Files by verifying that the file does not simultaneously satisfy the Magic_Bytes signatures of two or more distinct MIME types in Allowed_MIME_Types.
5. WHEN a CSV file is uploaded, THE File_Validator SHALL verify that the file contains only printable UTF-8 or ASCII characters and does not contain null bytes, to prevent CSV injection and binary disguise.
6. THE File_Validator SHALL validate files regardless of the `Content-Type` header value sent by the client.
7. IF the file content is empty (zero bytes), THEN THE File_Validator SHALL reject the file with HTTP 400.

---

### Requirement 5: File Extension and MIME Consistency

**User Story:** As a security engineer, I want filename extensions to be consistent with detected MIME types, so that social-engineering attacks using misleading filenames are blocked.

#### Acceptance Criteria

1. THE File_Validator SHALL maintain a canonical map of allowed extensions to MIME types: `.pdf` → `application/pdf`, `.jpg`/`.jpeg` → `image/jpeg`, `.png` → `image/png`, `.csv` → `text/csv`, `.xlsx` → `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`.
2. WHEN a file is uploaded with an extension not present in the canonical map, THE File_Validator SHALL reject the file with HTTP 415.
3. WHEN a file is uploaded with an extension that does not match the detected MIME type, THE File_Validator SHALL reject the file with HTTP 415 and include both the declared extension and the detected MIME type in the error detail.

---

### Requirement 6: CSRF Protection on State-Mutating Endpoints

**User Story:** As a security engineer, I want all state-mutating API requests from the Web_Client to carry a CSRF token, so that cross-site request forgery attacks cannot exploit the httpOnly cookie-based auth.

#### Acceptance Criteria

1. WHEN a user's session is established (after login), THE Auth_Service SHALL set a non-httpOnly, `Secure`, `SameSite=Strict` cookie named `csrf_token` containing a cryptographically random 256-bit value.
2. WHEN the Web_Client sends a `POST`, `PUT`, `PATCH`, or `DELETE` request to the API_Gateway, THE Web_Client SHALL include the value of the `csrf_token` cookie in a request header named `X-CSRF-Token`.
3. WHEN the API_Gateway receives a `POST`, `PUT`, `PATCH`, or `DELETE` request, THE CSRF_Middleware SHALL compare the `X-CSRF-Token` header value against the `csrf_token` cookie value.
4. IF the `X-CSRF-Token` header is absent or does not match the `csrf_token` cookie, THEN THE CSRF_Middleware SHALL reject the request with HTTP 403 and detail `csrf_token_invalid`.
5. THE CSRF_Middleware SHALL apply CSRF validation to all state-mutating endpoints under `/api/v1/` except `POST /api/v1/auth/login` (which has no session cookie yet) and `POST /api/v1/auth/refresh` (which is protected by the Refresh_Token cookie alone).
6. WHEN a user calls `POST /api/v1/auth/logout`, THE Auth_Service SHALL also clear the `csrf_token` cookie by setting it with `Max-Age=0`.
7. THE CSRF_Middleware SHALL use a constant-time comparison when validating the CSRF_Token to prevent timing attacks.

---

### Requirement 7: CSRF Token Lifecycle

**User Story:** As a frontend developer, I want the CSRF token to be automatically refreshed alongside the Access_Token, so that the CSRF protection does not break silent token renewal.

#### Acceptance Criteria

1. WHEN `POST /api/v1/auth/refresh` issues new auth cookies, THE Auth_Service SHALL also issue a new `csrf_token` cookie with a fresh random value.
2. WHEN the Web_Client performs a silent token renewal via `POST /api/v1/auth/refresh`, THE Web_Client SHALL read the updated `csrf_token` cookie and use it for subsequent requests.
3. THE Auth_Service SHALL generate each CSRF_Token using a cryptographically secure random number generator producing at least 256 bits of entropy.

---

### Requirement 8: Security Headers

**User Story:** As a security engineer, I want the API and web frontend to emit security-relevant HTTP response headers, so that browsers enforce additional protections against XSS and clickjacking.

#### Acceptance Criteria

1. THE API_Gateway SHALL include the header `X-Content-Type-Options: nosniff` on all responses.
2. THE API_Gateway SHALL include the header `X-Frame-Options: DENY` on all responses.
3. THE Web_Client SHALL include a `Content-Security-Policy` header that disallows inline scripts and restricts script sources to the application's own origin.
4. WHILE the application is running in production (`ENV=production`), THE API_Gateway SHALL include the header `Strict-Transport-Security: max-age=31536000; includeSubDomains` on all responses.
