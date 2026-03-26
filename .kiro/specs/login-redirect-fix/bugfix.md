# Bugfix Requirements Document

## Introduction

After a successful login on the web app (Next.js), the user is not redirected to the home/dashboard page — they remain stuck on the login page. The root cause is a cookie name mismatch: the `set-cookie` API route stores the JWT under the name `auth_token`, but the Next.js middleware reads `access_token`. Because the middleware never finds the token, it treats every post-login request as unauthenticated and redirects back to `/login`, creating an infinite redirect loop.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN a user submits valid credentials on the login page THEN the system stores the JWT in a cookie named `auth_token` but the middleware reads a cookie named `access_token`, so the middleware finds no token and redirects the user back to the login page instead of the intended destination.

1.2 WHEN the middleware evaluates a request to a protected route after a successful login THEN the system reads `request.cookies.get('access_token')` which returns `undefined`, causing the middleware to treat the authenticated user as unauthenticated and issue a redirect to `/[locale]/login`.

### Expected Behavior (Correct)

2.1 WHEN a user submits valid credentials on the login page THEN the system SHALL store the JWT in a cookie whose name is consistent with what the middleware reads, so the middleware recognises the authenticated session and allows the redirect to the home/dashboard page to complete.

2.2 WHEN the middleware evaluates a request to a protected route after a successful login THEN the system SHALL find the auth cookie, decode the role from the JWT, and allow the request to proceed (or redirect to the role-appropriate page) without bouncing the user back to `/login`.

### Unchanged Behavior (Regression Prevention)

3.1 WHEN an unauthenticated user navigates to a protected route THEN the system SHALL CONTINUE TO redirect them to `/[locale]/login`.

3.2 WHEN an authenticated non-admin user navigates to `/[locale]/admin` THEN the system SHALL CONTINUE TO redirect them to the locale root (`/[locale]`).

3.3 WHEN an authenticated admin user navigates to `/[locale]/admin` THEN the system SHALL CONTINUE TO allow access to the admin page.

3.4 WHEN any user navigates to a public path (`/login`, `/qa`) THEN the system SHALL CONTINUE TO allow access without requiring authentication.

3.5 WHEN a user logs out THEN the system SHALL CONTINUE TO clear the auth cookie and redirect to `/[locale]/login`.
