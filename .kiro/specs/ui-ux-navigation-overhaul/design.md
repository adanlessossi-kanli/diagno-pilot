# UI/UX Navigation Overhaul — Bugfix Design

## Overview

Diagno-Pilot's web UI has nine distinct defects that together degrade brand identity, navigation clarity, and role-based access. This design covers the targeted fixes:

1. Add a custom SVG icon/logo (medical + African identity) to the NavBar wordmark and login page.
2. Replace the small `h-64` hero on the home page with a full-screen splash section using existing Unsplash images, an app tagline, and a CTA to `/chat`.
3. Fix the post-login redirect so all roles land on `/` (Accueil) instead of role-branching.
4. Reorder NavBar links to: Q&A Assistant → Diagnostic guidé → Patients → Documents → Admin (admin-only).
5. Rename the document-management nav label from `nav.admin` to `nav.documents` in both `fr.json` and `en.json`.
6. Create a new `/admin-panel` route (admin-only, RBAC-protected) with user management, statistics dashboard, and audit log sections.
7. Extend `GET /api/v1/admin/stats` to include consultations, documents, and active users counts.
8. Add `PATCH` endpoints for role-only and status-only user updates with self-guard protection.
9. Add `GET /api/v1/audit` endpoint to expose the audit log to the admin panel.

The `/admin` route and all existing API contracts remain completely unchanged.

---

## Glossary

- **Bug_Condition (C)**: Any of the six conditions that trigger a defect — missing logo, inadequate splash, wrong redirect target, wrong nav order, mislabeled nav key, or absent admin-panel route.
- **Property (P)**: The desired correct behavior when a bug condition holds — logo present, splash prominent, redirect to `/`, correct link order, `nav.documents` key resolves, `/admin-panel` exists and is RBAC-protected.
- **Preservation**: All behaviors not touched by the fix that must remain identical — `/admin` document management, RBAC hiding of admin links for non-admins, NavBar hidden for unauthenticated users, all i18n keys outside `nav.documents`/`nav.adminPanel`, all existing API contracts.
- **NavBar**: `apps/web/src/components/NavBar.tsx` — renders the top navigation bar for authenticated users.
- **AuthContext.login**: The `login` function in `apps/web/src/contexts/AuthContext.tsx` — performs POST /auth/login, fetches /auth/me, then calls `router.push` with the redirect target.
- **LoginPage redirect**: The `useEffect` in `apps/web/src/app/[locale]/login/page.tsx` that redirects already-authenticated users away from the login page.
- **IMAGES**: Registry in `apps/web/src/lib/images.ts` — Unsplash free-licence images; `IMAGES.hero` is the primary splash image.
- **nav.documents**: New i18n key replacing `nav.admin` for the document-management nav link label.
- **nav.adminPanel**: New i18n key for the admin panel nav link label.
- **admin-panel route**: New Next.js App Router page at `apps/web/src/app/[locale]/admin-panel/page.tsx`.
- **audit_logs collection**: MongoDB collection populated by `audit_service.log_action()` — already exists; the new `GET /api/v1/audit` endpoint exposes it read-only.
- **Self-guard**: The check that prevents an admin from demoting or deactivating their own account via the user management endpoints.

---

## Bug Details

### Bug Condition

Six independent bug conditions exist. Each is formalized below.

**Formal Specification:**

```
FUNCTION isBugCondition_NoLogo(X)
  INPUT: X = rendered NavBar or login page component tree
  OUTPUT: boolean
  RETURN X contains no <svg> element with role="img" and data-logo="diagno-pilot"
END FUNCTION

FUNCTION isBugCondition_NoSplash(X)
  INPUT: X = rendered home page component
  OUTPUT: boolean
  RETURN X.heroSection.heightClass = "h-64"
         OR X.heroSection.hasTagline = false
         OR X.heroSection.hasCtaButton = false
         OR X.heroSection.ctaHref ≠ "/chat"
END FUNCTION

FUNCTION isBugCondition_WrongLoginRedirect(X)
  INPUT: X = AuthUser returned by fetchMe() after successful login
  OUTPUT: boolean
  RETURN router.lastPushedPath ≠ "/" + locale + "/"
         (i.e. redirect branches on role instead of always going to "/")
END FUNCTION

FUNCTION isBugCondition_WrongNavOrder(X)
  INPUT: X = rendered NavBar links array for an admin user
  OUTPUT: boolean
  RETURN X[0].key ≠ "chat"
         OR X[1].key ≠ "diagnose"
         OR X[2].key ≠ "patients"
         OR X[3].key ≠ "documents"
         OR X[4].key ≠ "admin-panel"
END FUNCTION

FUNCTION isBugCondition_MislabeledDocuments(X)
  INPUT: X = i18n locale files (fr.json, en.json)
  OUTPUT: boolean
  RETURN "nav.documents" NOT IN X.keys
END FUNCTION

FUNCTION isBugCondition_NoAdminPanel(X)
  INPUT: X = Next.js route registry
  OUTPUT: boolean
  RETURN "/admin-panel" NOT IN X.routes
         OR X.routes["/admin-panel"].rbacRole ≠ "admin"
END FUNCTION
```

### Examples

- **No Logo**: NavBar renders `<span>Diagno-Pilot</span>` with no SVG — expected: SVG icon + wordmark side by side.
- **No Splash**: Home page hero is `h-64` with no tagline or CTA — expected: `min-h-screen` section with tagline "L'assistant médical intelligent pour l'Afrique" and a "Commencer" button linking to `/chat`.
- **Wrong Redirect (admin)**: After admin login, `router.push` is called with `/${locale}/admin` — expected: `/${locale}` for all roles.
- **Wrong Redirect (medecin)**: After medecin login, `router.push` is called with `/${locale}` — this is already correct, but the admin branch is wrong.
- **Wrong Nav Order**: NavBar renders Home → Q&A Assistant → Guided Diagnosis → Patients → Administration — expected: Q&A Assistant → Diagnostic guidé → Patients → Documents → Admin.
- **Mislabeled Documents**: `nav.admin` key is used for the documents link — expected: `nav.documents` key with value "Documents" in both locales.
- **No Admin Panel**: Navigating to `/admin-panel` returns 404 — expected: admin-only page with three sections.

---

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- `/admin` route continues to render the document upload form and indexed document list with full create/delete functionality.
- NavBar continues to hide admin-only links for non-admin authenticated users.
- NavBar continues to return `null` for unauthenticated users.
- `LanguageSwitcher` and logout button continue to function correctly.
- All i18n keys in `fr.json` and `en.json` outside of `nav.documents` and `nav.adminPanel` additions remain unchanged.
- All existing API contracts (`/api/v1/documents`, `/api/v1/patients`, `/api/v1/diagnose`, `/api/v1/chat`) remain unchanged.
- Mobile hamburger drawer continues to render nav links correctly.
- Active route highlighting continues to work for all routes including `/admin-panel`.
- Already-authenticated users navigating to `/login` continue to be redirected away.

**Scope:**
All inputs that do NOT involve the six bug conditions above are completely unaffected by this fix.

---

## Hypothesized Root Cause

1. **Missing SVG Logo**: The NavBar wordmark is a plain `<span>` with no SVG element. The login page similarly uses a plain `<p>` tag. No logo component exists in the codebase.

2. **Inadequate Splash Screen**: `apps/web/src/app/[locale]/page.tsx` uses `h-64` for the hero container and has no tagline text or CTA button — it only has a nav link list that duplicates the NavBar.

3. **Role-Branching Redirect**: `AuthContext.login` contains an explicit `if (authUser.role === 'admin') { router.push(admin) } else { router.push('/') }` branch. The fix is to remove the branch and always push `/${locale}`. The login page's `useEffect` also branches on role for already-authenticated users.

4. **Wrong Nav Order and Missing Home Removal**: The `links` array in `NavBar.tsx` starts with `{ href: base, label: t('home'), path: '/' }` and uses `t('admin')` for the documents link. The order and keys need updating.

5. **Missing i18n Key**: `nav.documents` does not exist in either `fr.json` or `en.json`. The documents nav link currently uses `nav.admin`, which conflicts with the new admin panel concept.

6. **Absent Admin Panel Route**: No file exists at `apps/web/src/app/[locale]/admin-panel/page.tsx`. **Partially Implemented Admin Backend**: `backend/routers/admin.py` already contains `GET /api/v1/admin/users`, `POST /api/v1/admin/users`, `PUT /api/v1/admin/users/{id}`, and `GET /api/v1/admin/stats`. However, four gaps remain: (a) `GET /api/v1/admin/stats` only returns `total_users`, `users_by_role`, and `total_patients` — it is missing `totalConsultations`, `totalDocuments`, and `activeUsers` counts; (b) there is no `PATCH /api/v1/admin/users/{id}/role` endpoint for role-only updates; (c) there is no `PATCH /api/v1/admin/users/{id}/status` endpoint for activate/deactivate; (d) there is no `GET /api/v1/audit` endpoint to expose the existing `audit_logs` collection; (e) the existing `PUT /api/v1/admin/users/{id}` has no self-demotion or self-deactivation guard.

---

## Correctness Properties

Property 1: Bug Condition — SVG Logo Present in NavBar and Login Page

_For any_ rendered NavBar or login page component where `isBugCondition_NoLogo` returns true, the fixed components SHALL render an `<svg>` element with `role="img"` and `data-logo="diagno-pilot"` representing a medical/African visual identity, positioned adjacent to the "Diagno-Pilot" wordmark.

**Validates: Requirements 2.1, 2.2**

Property 2: Bug Condition — Full-Screen Splash on Home Page

_For any_ rendered home page where `isBugCondition_NoSplash` returns true, the fixed `HomePage` component SHALL render a hero section with `min-h-screen` (or equivalent full-screen class), at least one tagline string, and a call-to-action button/link whose `href` resolves to `/{locale}/chat`.

**Validates: Requirements 2.3**

Property 3: Bug Condition — Post-Login Redirect to Accueil

_For any_ `AuthUser` returned by `fetchMe()` after a successful login (regardless of `user.role`), the fixed `AuthContext.login` function SHALL call `router.push` with `/${locale}` as the target, never branching on role.

**Validates: Requirements 2.9**

Property 4: Bug Condition — Correct NavBar Link Order

_For any_ authenticated admin user, the fixed NavBar SHALL render links in exactly this order: `chat` → `diagnose` → `patients` → `documents` → `admin-panel`, with no `home` link present. For any authenticated non-admin user, the order SHALL be: `chat` → `diagnose` → `patients` → `documents`.

**Validates: Requirements 2.4, 2.5**

Property 5: Bug Condition — nav.documents i18n Key Resolves

_For any_ locale (`fr` or `en`), the fixed i18n files SHALL contain the key `nav.documents` with a non-empty string value ("Documents" in both locales), and the NavBar SHALL use this key for the document-management link label.

**Validates: Requirements 2.5, 2.6**

Property 6: Bug Condition — Admin Panel Route Exists and Is RBAC-Protected

_For any_ request to `/admin-panel` where the authenticated user's role is `admin`, the fixed route SHALL render the admin panel with three sections (user management, statistics, audit log). _For any_ request where the user is not authenticated or has a role other than `admin`, the fixed route SHALL redirect to `/` or `/login` and SHALL NOT render admin panel content.

**Validates: Requirements 2.7, 2.8**

Property 7: Preservation — /admin Document Management Unchanged

_For any_ admin user accessing `/admin`, the fixed codebase SHALL produce exactly the same rendered output and API interactions as the original code, preserving all document upload and delete functionality.

**Validates: Requirements 3.1**

Property 8: Preservation — RBAC and NavBar Visibility Unchanged

_For any_ non-admin authenticated user, the fixed NavBar SHALL NOT render admin-only links. _For any_ unauthenticated state, the fixed NavBar SHALL return `null`. These behaviors must be identical to the original.

**Validates: Requirements 3.2, 3.3**

Property 9: Bug Condition — Self-Demotion and Self-Deactivation Guard

_For any_ `PATCH /api/v1/admin/users/{id}/role` or `PATCH /api/v1/admin/users/{id}/status` request where `id` matches the authenticated admin's own user ID, the backend SHALL return HTTP 403 and SHALL NOT apply the update. This prevents an admin from accidentally locking themselves out.

**Validates: Requirements 2.11, 2.12**

---

## Fix Implementation

### Changes Required

**File 1**: `apps/web/src/components/DiagnoPilotLogo.tsx` *(new file)*

**Purpose**: Reusable SVG logo component used in NavBar and login page.

**Specific Changes**:
1. Create a functional component `DiagnoPilotLogo` accepting `size?: number` and `className?: string` props.
2. SVG design: a stylized medical cross / caduceus silhouette in primary blue (`#2563EB`) with a subtle warm-tone accent (representing African identity), 32×32 viewBox.
3. Include `role="img"`, `aria-label="Diagno-Pilot logo"`, and `data-logo="diagno-pilot"` attributes for testability.

---

**File 2**: `apps/web/src/components/NavBar.tsx` *(modify)*

**Specific Changes**:
1. Import `DiagnoPilotLogo` and wrap the wordmark `<span>` in a `<Link href={base}>` containing the SVG logo + "Diagno-Pilot" text.
2. Remove the `home` entry from the `links` array.
3. Reorder links to: `chat` → `diagnose` → `patients` → `documents` (using `t('documents')`) → `admin-panel` (admin-only, using `t('adminPanel')`).
4. Update the admin-only link to point to `${base}/admin-panel` with key `admin-panel`.

---

**File 3**: `apps/web/src/app/[locale]/login/page.tsx` *(modify)*

**Specific Changes**:
1. Import `DiagnoPilotLogo` and replace the plain `<p>Diagno-Pilot</p>` with `<DiagnoPilotLogo />` + wordmark.
2. Fix the already-authenticated redirect `useEffect`: change `router.replace(user.role === 'admin' ? '../admin' : '..')` to `router.replace('..')` (always go to `/`).

---

**File 4**: `apps/web/src/contexts/AuthContext.tsx` *(modify)*

**Specific Changes**:
1. In the `login` callback, remove the role-based branch and replace with a single `router.push(`/${locale}`)` call for all roles.

---

**File 5**: `apps/web/src/app/[locale]/page.tsx` *(modify)*

**Specific Changes**:
1. Replace the `h-64` hero `<div>` with a `<section>` using `relative min-h-screen flex flex-col items-center justify-center`.
2. Use `IMAGES.hero` as a full-screen background image via `<Image fill className="object-cover" />` with a dark overlay (`bg-black/40`).
3. Add app name heading, tagline (i18n key `home.tagline`), and a CTA `<Link href={`/${locale}/chat`}>` button.
4. Remove the duplicate nav link list (NavBar already handles navigation).

---

**File 6**: `packages/i18n/locales/fr.json` *(modify)*

**Specific Changes**:
1. Add `"documents": "Documents"` to the `nav` object.
2. Add `"adminPanel": "Admin"` to the `nav` object.
3. Add `"home"` section with `"tagline": "L'assistant médical intelligent pour l'Afrique"` and `"cta": "Commencer"`.

---

**File 7**: `packages/i18n/locales/en.json` *(modify)*

**Specific Changes**:
1. Add `"documents": "Documents"` to the `nav` object.
2. Add `"adminPanel": "Admin"` to the `nav` object.
3. Add `"home"` section with `"tagline": "The intelligent medical assistant for Africa"` and `"cta": "Get started"`.

---

**File 8**: `apps/web/src/app/[locale]/admin-panel/page.tsx` *(new file)*

**Purpose**: Admin-only panel with three sections.

**Specific Changes**:
1. RBAC guard: redirect non-admin users to `/` using the same pattern as `apps/web/src/app/[locale]/admin/page.tsx`.
2. Section 1 — User Management: fetch `GET /api/v1/admin/users`, display a table with columns: name, email, role, active status. Provide role-change (`PATCH /api/v1/admin/users/:id/role`) and activate/deactivate (`PATCH /api/v1/admin/users/:id/status`) actions.
3. Section 2 — Statistics Dashboard: fetch `GET /api/v1/admin/stats`, display count cards for: patients, consultations, documents, active users.
4. Section 3 — Audit Log: fetch `GET /api/v1/audit`, display a read-only table with columns: timestamp, actor, action, resource. No write operations.
5. Use `createApiClient` from `@diagno-pilot/api-client` for all API calls, consistent with the existing admin page pattern.

---

**File 9**: `backend/routers/admin.py` *(modify)*

**Purpose**: Extend the existing admin router with missing endpoints and guards.

**Specific Changes**:
1. Add `PATCH /api/v1/admin/users/{id}/role` endpoint — accepts `{ "role": "<role>" }` body, updates only the user's role, returns updated `UserResponse`. Restricted to `admin` role via `require_role(["admin"])`. Guard: if `user_id == str(current_user["_id"])`, raise HTTP 403 with message "Cannot change your own role". Log to audit with `action="update_user_role"`.
2. Add `PATCH /api/v1/admin/users/{id}/status` endpoint — accepts `{ "isActive": true|false }` body, updates only `is_active`, returns updated `UserResponse`. Restricted to `admin` role. Guard: if `user_id == str(current_user["_id"])` and `isActive == false`, raise HTTP 403 with message "Cannot deactivate your own account". Log to audit with `action="update_user_status"`.
3. Extend `GET /api/v1/admin/stats` response to include: `totalConsultations` (count of `consultations` collection), `totalDocuments` (count of `document_chunks` collection distinct by `document_id`), `activeUsers` (count of `users` where `is_active == true`). Keep existing fields (`total_users`, `users_by_role`, `total_patients`) for backward compatibility.
4. Add `GET /api/v1/audit` endpoint — returns paginated audit log from `audit_logs` collection. Query params: `page: int = 1`, `page_size: int = 50` (max 100). Response: `{ "items": [...], "total": int, "page": int, "pageSize": int }`. Each item maps `AuditLog` model fields: `id`, `timestamp` (alias for `created_at`), `actorId` (alias for `user_id`), `actorEmail` (resolved by joining with `users` collection), `action`, `resource`, `resourceId`. Restricted to `admin` role.

---

**File 10**: `backend/routers/admin.py` — Pydantic schemas *(modify)*

**Specific Changes**:
1. Add `PatchRoleRequest` schema: `{ "role": UserRole }`.
2. Add `PatchStatusRequest` schema: `{ "isActive": bool }`.
3. Add `AuditLogResponse` schema: `{ "id": str, "timestamp": datetime, "actorId": str, "actorEmail": str, "action": str, "resource": str, "resourceId": str | None }`.
4. Add `PaginatedAuditResponse` schema: `{ "items": list[AuditLogResponse], "total": int, "page": int, "pageSize": int }`.

---

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate each bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate each bug BEFORE implementing the fix. Confirm or refute the root cause analysis.

**Test Plan**: Write unit/render tests against the UNFIXED components and assert the expected correct behavior — these tests will fail on unfixed code, confirming the bugs.

**Test Cases**:
1. **Logo Absent Test**: Render `NavBar` with an authenticated user — assert no `[data-logo="diagno-pilot"]` SVG is found (will fail on unfixed code, confirming bug 1).
2. **Splash Absent Test**: Render `HomePage` — assert no `min-h-screen` hero section and no `/chat` CTA link (will fail on unfixed code, confirming bug 2).
3. **Wrong Redirect Test (admin)**: Mock `fetchMe` returning `{ role: 'admin' }`, call `login()` — assert `router.push` was called with `/${locale}` not `/${locale}/admin` (will fail on unfixed code, confirming bug 3).
4. **Nav Order Test**: Render `NavBar` for admin user — assert first link key is `chat` not `home` (will fail on unfixed code, confirming bug 4).
5. **Missing i18n Key Test**: Load `fr.json` — assert `nav.documents` key exists (will fail on unfixed code, confirming bug 5).
6. **Missing Route Test**: Assert `apps/web/src/app/[locale]/admin-panel/page.tsx` exists (will fail on unfixed code, confirming bug 6).

**Expected Counterexamples**:
- NavBar renders no SVG logo element.
- Home page hero has `h-64` class, no tagline, no `/chat` link.
- `router.push` called with `/${locale}/admin` for admin users.
- First NavBar link label is "Accueil" / "Home".
- `nav.documents` key missing from locale files.
- `/admin-panel` route file does not exist.

### Fix Checking

**Goal**: Verify that for all inputs where each bug condition holds, the fixed code produces the expected behavior.

**Pseudocode:**
```
FOR ALL X WHERE isBugCondition_NoLogo(X) DO
  result := render_fixed(NavBar | LoginPage)
  ASSERT result.querySelector('[data-logo="diagno-pilot"]') IS NOT NULL
END FOR

FOR ALL X WHERE isBugCondition_NoSplash(X) DO
  result := render_fixed(HomePage)
  ASSERT result.heroSection.hasClass("min-h-screen")
    AND result.heroSection.tagline IS NOT EMPTY
    AND result.heroSection.ctaHref ENDS WITH "/chat"
END FOR

FOR ALL user WHERE isBugCondition_WrongLoginRedirect(user) DO
  result := login_fixed(email, password)
  ASSERT router.lastPushedPath = "/" + locale
END FOR

FOR ALL navState WHERE isBugCondition_WrongNavOrder(navState) DO
  result := render_fixed(NavBar, { user: adminUser })
  ASSERT result.links[0].key = "chat"
    AND result.links[3].key = "documents"
    AND result.links[4].key = "admin-panel"
    AND "home" NOT IN result.links.map(l => l.key)
END FOR

FOR ALL locale WHERE isBugCondition_MislabeledDocuments(locale) DO
  result := loadLocale_fixed(locale)
  ASSERT result["nav.documents"] IS NOT EMPTY
END FOR

FOR ALL request WHERE isBugCondition_NoAdminPanel(request) DO
  result := routeRegistry_fixed
  ASSERT "/admin-panel" IN result.routes
  result_nonAdmin := render_fixed(AdminPanelPage, { user: nonAdminUser })
  ASSERT result_nonAdmin.redirectTarget = "/"
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug conditions do NOT hold, the fixed code produces the same result as the original.

**Pseudocode:**
```
FOR ALL user WHERE user.role = "admin" DO
  ASSERT render_original("/admin", user) = render_fixed("/admin", user)
END FOR

FOR ALL user WHERE user.role ≠ "admin" DO
  ASSERT navBar_original(user).adminLinks = navBar_fixed(user).adminLinks = []
END FOR

FOR ALL state WHERE user IS NULL DO
  ASSERT navBar_original(null) = navBar_fixed(null) = null
END FOR

FOR ALL locale IN ["fr", "en"] DO
  FOR ALL key WHERE key ≠ "nav.documents" AND key ≠ "nav.adminPanel" AND key NOT IN "home.*" DO
    ASSERT localeFile_original[locale][key] = localeFile_fixed[locale][key]
  END FOR
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because it generates many test cases automatically (e.g., random user roles, random locale keys) and catches edge cases that manual tests miss.

**Test Cases**:
1. **Admin Page Preservation**: Render `/admin` with admin user before and after fix — assert identical document list, upload form, and API calls.
2. **RBAC Hiding Preservation**: For non-admin users, assert no admin-only links appear in NavBar after fix.
3. **NavBar Null Preservation**: For unauthenticated state, assert NavBar returns `null` after fix.
4. **i18n Key Preservation**: Load both locale files after fix — assert all pre-existing keys retain their original values.
5. **Logout/LanguageSwitcher Preservation**: Render NavBar after fix — assert logout button and LanguageSwitcher are still present and functional.

### Unit Tests

- Test `DiagnoPilotLogo` renders an SVG with correct `data-logo` attribute.
- Test `NavBar` link order for admin and non-admin users after fix.
- Test `AuthContext.login` calls `router.push` with `/${locale}` for both admin and non-admin users.
- Test `LoginPage` already-authenticated redirect goes to `..` (not role-branched).
- Test `AdminPanelPage` redirects non-admin users to `/`.
- Test `AdminPanelPage` renders three sections for admin users.

### Property-Based Tests

- Generate random `UserRole` values — for all roles, `login()` must push `/${locale}` (Property 3).
- Generate random authenticated user states — for non-admin roles, NavBar must never include `admin-panel` link (Property 8).
- Generate random i18n key paths — all keys not in the addition set must be unchanged between original and fixed locale files (Property 7 / i18n preservation).
- Generate random admin user states — `/admin` page must always render document management sections (Property 7).

### Integration Tests

- Full login flow for admin user: assert landing page is `/` (Accueil splash), not `/admin`.
- Full login flow for medecin user: assert landing page is `/` (Accueil splash).
- Navigate to `/admin-panel` as admin: assert all three sections render with data.
- Navigate to `/admin-panel` as non-admin: assert redirect to `/`.
- Navigate to `/admin` as admin after fix: assert document management still fully functional.
- Switch locale (FR ↔ EN): assert `nav.documents` label updates correctly in both NavBar and mobile drawer.
