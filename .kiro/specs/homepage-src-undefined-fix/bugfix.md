# Bugfix Requirements Document

## Introduction

Two related bugs prevent the web application from loading correctly:

1. **LoginPage crash**: The `LoginPage` component in `apps/web/src/app/[locale]/login/page.tsx` crashes on render because it references `IMAGES.loginSide`, a key that does not exist in the centralized image registry (`src/lib/images.ts`). Accessing `.src` on the resulting `undefined` value throws a `TypeError` at line 50.

2. **auth/me empty response**: The `AuthContext` calls `GET /api/v1/auth/me` on mount to restore an existing session, but the request returns `ERR_EMPTY_RESPONSE`. The `get()` helper in the API client does not pass `credentials: 'include'`, so the httpOnly cookie carrying the access token is never sent, causing the backend to reject or drop the connection.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN the `LoginPage` component renders THEN the system throws `TypeError: Cannot read properties of undefined (reading 'src')` at `login/page.tsx:50`
1.2 WHEN `IMAGES.loginSide` is accessed THEN the system returns `undefined` because no such key exists in the `IMAGES` registry
1.3 WHEN `AuthContext` mounts and calls `apiClient.auth.me()` THEN the system receives `ERR_EMPTY_RESPONSE` from `GET /api/v1/auth/me`
1.4 WHEN the `get()` helper in the API client sends a request THEN the system does not include `credentials: 'include'`, so the httpOnly session cookie is omitted

### Expected Behavior (Correct)

2.1 WHEN the `LoginPage` component renders THEN the system SHALL resolve the `loginSide` image `src` and `alt` values without error
2.2 WHEN `IMAGES.loginSide` is accessed THEN the system SHALL return a valid `ImageEntry` object containing `src` and `alt` properties
2.3 WHEN `AuthContext` mounts and calls `apiClient.auth.me()` THEN the system SHALL receive a valid JSON response from `GET /api/v1/auth/me`
2.4 WHEN the `get()` helper sends a request THEN the system SHALL include `credentials: 'include'` so the httpOnly cookie is forwarded to the backend

### Unchanged Behavior (Regression Prevention)

3.1 WHEN other pages access valid `IMAGES` keys (e.g., `IMAGES.hero`, `IMAGES.consultation`, `IMAGES.diagnoseHeader`) THEN the system SHALL CONTINUE TO resolve those entries correctly
3.2 WHEN the `IMAGES` registry is imported elsewhere in the application THEN the system SHALL CONTINUE TO export all existing entries unchanged
3.3 WHEN a user is not authenticated and `auth/me` returns a 401 THEN the system SHALL CONTINUE TO set `user` to `null` and proceed to the login page
3.4 WHEN authenticated API calls are made using `post()`, `put()`, or `del()` helpers THEN the system SHALL CONTINUE TO include the `Authorization: Bearer` header as before
