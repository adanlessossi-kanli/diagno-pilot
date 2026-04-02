# Implementation Plan

- [x] 1. Write bug condition exploration tests
  - **Property 1: Bug Condition** - All Six UI/UX Navigation Bugs
  - **CRITICAL**: Write these tests BEFORE implementing any fix — they MUST FAIL on unfixed code
  - **DO NOT attempt to fix the test or the code when it fails**
  - **GOAL**: Surface counterexamples that demonstrate each bug exists
  - **Scoped PBT Approach**: For deterministic bugs, scope each property to the concrete failing case(s)

  **Backend exploration (Hypothesis — `backend/tests/test_admin_bugs.py`):**
  - Test `GET /api/v1/admin/stats` returns only `total_users`, `users_by_role`, `total_patients` — assert `totalConsultations`, `totalDocuments`, `activeUsers` are MISSING (confirms bug 1.11)
  - Test `PATCH /api/v1/admin/users/{id}/role` returns 404/405 — confirms endpoint absent (confirms bug 1.10)
  - Test `PATCH /api/v1/admin/users/{id}/status` returns 404/405 — confirms endpoint absent (confirms bug 1.10)
  - Test `GET /api/v1/audit` returns 404/405 — confirms endpoint absent (confirms bug 1.12)
  - Test `PUT /api/v1/admin/users/{self_id}` with own id and `role=guest` succeeds (200) — confirms self-guard missing (confirms bug 2.11/2.12)
  - Use `@given(st.sampled_from(["admin", "medecin", "guest"]))` for role property test
  - Run on UNFIXED code — **EXPECTED OUTCOME**: Tests FAIL (proves bugs exist)
  - Document counterexamples found (e.g., "stats response has no totalConsultations key")

  **Frontend exploration (Vitest + fast-check — `apps/web/src/components/__tests__/NavBar.bug.test.tsx` and `apps/web/src/__tests__/AuthContext.bug.test.tsx`):**
  - Render `NavBar` with admin user — assert `querySelector('[data-logo="diagno-pilot"]')` returns null (confirms bug 1.1)
  - Render `LoginPage` — assert no `[data-logo="diagno-pilot"]` SVG (confirms bug 1.2)
  - Render `HomePage` — assert no element with class `min-h-screen` in hero and no link to `/chat` (confirms bug 1.3)
  - Render `NavBar` for admin user — assert `links[0].textContent` equals "Accueil"/"Home" not "Assistant Q&A"/"Q&A Assistant" (confirms bug 1.4)
  - Load `fr.json` — assert `nav.documents` key is undefined (confirms bug 1.5)
  - Assert file `apps/web/src/app/[locale]/admin-panel/page.tsx` does not exist (confirms bug 1.7)
  - Mock `fetchMe` returning `{ role: 'admin' }`, call `login()` — assert `router.push` was called with `/${locale}/admin` not `/${locale}` (confirms bug 1.9)
  - Use `fc.constantFrom('admin', 'medecin', 'guest', 'infirmière')` for role property
  - Run on UNFIXED code — **EXPECTED OUTCOME**: Tests FAIL (proves bugs exist)
  - Document counterexamples (e.g., "router.push called with /fr/admin for admin role")
  - Mark task complete when all tests are written, run, and failures are documented
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.7, 1.9, 1.10, 1.11, 1.12_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Existing Behaviors Unchanged
  - **IMPORTANT**: Follow observation-first methodology — run UNFIXED code with non-buggy inputs first
  - **Observe on UNFIXED code:**
    - `GET /admin` renders document upload form and indexed document list
    - NavBar for non-admin user has no admin-only links
    - NavBar for unauthenticated user returns null
    - `fr.json` and `en.json` contain all existing keys with their current values
    - `LanguageSwitcher` and logout button render in NavBar
    - Mobile drawer renders nav links

  **Backend preservation (Hypothesis — `backend/tests/test_admin_preservation.py`):**
  - `@given(st.text())` — for all non-admin-endpoint paths, assert existing API contracts unchanged
  - Assert `GET /api/v1/admin/stats` still returns `total_users`, `users_by_role`, `total_patients` after fix
  - Assert `GET /api/v1/admin/users` still returns user list with same shape
  - Assert `PUT /api/v1/admin/users/{id}` still works for non-self updates
  - Verify tests PASS on UNFIXED code

  **Frontend preservation (Vitest + fast-check — `apps/web/src/components/__tests__/NavBar.preservation.test.tsx`):**
  - `fc.constantFrom('medecin', 'guest', 'infirmière')` — for all non-admin roles, NavBar must never include `admin-panel` link
  - Assert NavBar returns null when user is null/unauthenticated
  - Load both locale files — assert all pre-existing keys retain original values (use `fc.constantFrom(...Object.keys(fr))` excluding addition set)
  - Assert LanguageSwitcher and logout button present in NavBar after fix
  - Assert mobile drawer renders links correctly
  - Verify tests PASS on UNFIXED code
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 3.11_

- [x] 3. Fix backend: extend admin.py with new endpoints and guards

  - [x] 3.1 Add Pydantic schemas to `backend/routers/admin.py`
    - Add `PatchRoleRequest(BaseModel)`: field `role: UserRole`
    - Add `PatchStatusRequest(BaseModel)`: field `is_active: bool`
    - Add `AuditLogResponse(BaseModel)`: fields `id`, `timestamp`, `actor_id`, `actor_email`, `action`, `resource`, `resource_id`
    - Add `PaginatedAuditResponse(BaseModel)`: fields `items: list[AuditLogResponse]`, `total`, `page`, `page_size`
    - _Bug_Condition: isBugCondition_MissingAdminEndpoints — schemas required by new endpoints_
    - _Requirements: 2.10, 2.11, 2.12, 2.13, 2.14_

  - [x] 3.2 Add `PATCH /api/v1/admin/users/{id}/role` endpoint
    - Accept `PatchRoleRequest` body, update only `role` field
    - Self-guard: if `user_id == str(current_user["_id"])` raise HTTP 403 "Cannot change your own role"
    - Log to audit with `action="update_user_role"`
    - Return updated `UserResponse`
    - Restrict to `require_role(["admin"])`
    - _Bug_Condition: isBugCondition_MissingAdminEndpoints(X) where PATCH /users/{id}/role NOT IN X.routes_
    - _Expected_Behavior: PATCH returns 200 with updated user; self-patch returns 403_
    - _Requirements: 2.11_

  - [x] 3.3 Add `PATCH /api/v1/admin/users/{id}/status` endpoint
    - Accept `PatchStatusRequest` body, update only `is_active` field
    - Self-guard: if `user_id == str(current_user["_id"])` and `is_active == False` raise HTTP 403 "Cannot deactivate your own account"
    - Log to audit with `action="update_user_status"`
    - Return updated `UserResponse`
    - Restrict to `require_role(["admin"])`
    - _Bug_Condition: isBugCondition_MissingAdminEndpoints(X) where PATCH /users/{id}/status NOT IN X.routes_
    - _Expected_Behavior: PATCH returns 200 with updated user; self-deactivation returns 403_
    - _Requirements: 2.12_

  - [x] 3.4 Extend `GET /api/v1/admin/stats` response
    - Add `total_consultations`: count of `consultations` collection
    - Add `total_documents`: count of distinct `document_id` values in `document_chunks` collection
    - Add `active_users`: count of `users` where `is_active == True`
    - Keep existing fields (`total_users`, `users_by_role`, `total_patients`) unchanged for backward compatibility
    - _Bug_Condition: isBugCondition_MissingAdminEndpoints — stats missing totalConsultations, totalDocuments, activeUsers_
    - _Expected_Behavior: GET /api/v1/admin/stats returns all six count fields_
    - _Preservation: existing fields total_users, users_by_role, total_patients must remain in response_
    - _Requirements: 2.13, 3.11_

  - [x] 3.5 Add `GET /api/v1/audit` endpoint
    - Query params: `page: int = 1`, `page_size: int = 50` (max 100, clamp if exceeded)
    - Fetch from `audit_logs` collection sorted by `created_at` descending
    - For each entry, resolve `actor_email` by joining with `users` collection on `user_id`
    - Return `PaginatedAuditResponse` with `items`, `total`, `page`, `page_size`
    - Restrict to `require_role(["admin"])`
    - _Bug_Condition: isBugCondition_MissingAdminEndpoints(X) where GET /api/v1/audit NOT IN X.routes_
    - _Expected_Behavior: GET returns paginated audit log; non-admin gets 403_
    - _Requirements: 2.14_

  - [x] 3.6 Verify bug condition exploration test (backend) now passes
    - **Property 1: Expected Behavior** - Backend Admin Endpoints Present and Self-Guard Active
    - **IMPORTANT**: Re-run the SAME tests from task 1 (backend section) — do NOT write new tests
    - Run `backend/tests/test_admin_bugs.py` against fixed code
    - **EXPECTED OUTCOME**: All backend exploration tests PASS
    - _Requirements: 2.10, 2.11, 2.12, 2.13, 2.14_

  - [x] 3.7 Verify backend preservation tests still pass
    - **Property 2: Preservation** - Existing Backend Contracts Unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 2 (backend section) — do NOT write new tests
    - Run `backend/tests/test_admin_preservation.py`
    - **EXPECTED OUTCOME**: All preservation tests PASS (no regressions)
    - _Requirements: 3.7, 3.11_

- [x] 4. Fix i18n: add missing keys to fr.json and en.json

  - [x] 4.1 Update `packages/i18n/locales/fr.json`
    - Add `"documents": "Documents"` to the `nav` object
    - Add `"adminPanel": "Admin"` to the `nav` object
    - Add top-level `"home"` object with `"tagline": "L'assistant médical intelligent pour l'Afrique"` and `"cta": "Commencer"`
    - Do NOT modify any existing keys
    - _Bug_Condition: isBugCondition_MislabeledDocuments — nav.documents NOT IN fr.json_
    - _Expected_Behavior: nav.documents resolves to "Documents", nav.adminPanel resolves to "Admin"_
    - _Preservation: all pre-existing fr.json keys retain their original values_
    - _Requirements: 2.5, 2.15, 2.16, 3.5_

  - [x] 4.2 Update `packages/i18n/locales/en.json`
    - Add `"documents": "Documents"` to the `nav` object
    - Add `"adminPanel": "Admin"` to the `nav` object
    - Add top-level `"home"` object with `"tagline": "The intelligent medical assistant for Africa"` and `"cta": "Get started"`
    - Do NOT modify any existing keys
    - _Bug_Condition: isBugCondition_MislabeledDocuments — nav.documents NOT IN en.json_
    - _Expected_Behavior: nav.documents resolves to "Documents" in EN locale_
    - _Preservation: all pre-existing en.json keys retain their original values_
    - _Requirements: 2.5, 2.15, 2.16, 3.6_

- [x] 5. Fix frontend: create DiagnoPilotLogo component

  - [x] 5.1 Create `apps/web/src/components/DiagnoPilotLogo.tsx`
    - Functional component accepting `size?: number` (default 32) and `className?: string` props
    - SVG with `role="img"`, `aria-label="Diagno-Pilot logo"`, `data-logo="diagno-pilot"`, `viewBox="0 0 32 32"`
    - Design: stylized medical cross in primary blue `#2563EB` with warm-tone accent circle (African identity)
    - Export as default
    - _Bug_Condition: isBugCondition_NoLogo — no SVG with data-logo="diagno-pilot" in NavBar or login page_
    - _Expected_Behavior: component renders SVG with correct data-logo attribute_
    - _Requirements: 2.1, 2.2_

- [x] 6. Fix frontend: update NavBar

  - [x] 6.1 Modify `apps/web/src/components/NavBar.tsx`
    - Import `DiagnoPilotLogo` from `./DiagnoPilotLogo`
    - Replace plain `<span>Diagno-Pilot</span>` wordmark with `<Link href={base}><DiagnoPilotLogo size={28} /> <span>Diagno-Pilot</span></Link>`
    - Remove `{ href: base, label: t('home'), path: '/' }` from the `links` array
    - Reorder links to: `chat` → `diagnose` → `patients` → `documents` (using `t('documents')`, path `/documents`) → `admin-panel` (admin-only, using `t('adminPanel')`, path `/admin-panel`)
    - Update admin-only link href to `${base}/admin-panel`
    - Keep all other NavBar logic unchanged (RBAC hiding, mobile drawer, LanguageSwitcher, logout)
    - _Bug_Condition: isBugCondition_NoLogo AND isBugCondition_WrongNavOrder_
    - _Expected_Behavior: SVG logo present; links[0].key="chat"; links[3].key="documents"; no home link_
    - _Preservation: non-admin users see no admin-panel link; unauthenticated returns null; mobile drawer works_
    - _Requirements: 2.1, 2.4, 2.5, 2.15, 3.2, 3.3, 3.4, 3.8, 3.9_

- [x] 7. Fix frontend: update login page

  - [x] 7.1 Modify `apps/web/src/app/[locale]/login/page.tsx`
    - Import `DiagnoPilotLogo` from `../../../components/DiagnoPilotLogo`
    - Replace `<p className="text-primary-600 font-bold text-2xl mb-2">Diagno-Pilot</p>` with `<DiagnoPilotLogo size={40} className="mb-2" />` followed by the wordmark span
    - Fix already-authenticated redirect `useEffect`: change `router.replace(user.role === 'admin' ? '../admin' : '..')` to `router.replace('..')`
    - _Bug_Condition: isBugCondition_NoLogo AND isBugCondition_WrongLoginRedirect_
    - _Expected_Behavior: SVG logo present on login page; already-authenticated users always redirect to `..`_
    - _Preservation: login form, error handling, side image, and submit flow unchanged_
    - _Requirements: 2.2, 2.9, 3.10_

- [x] 8. Fix frontend: update AuthContext redirect

  - [x] 8.1 Modify `apps/web/src/contexts/AuthContext.tsx`
    - In the `login` callback, remove the role-based branch:
      ```
      if (authUser.role === 'admin') { router.push(`/${locale}/admin`); } else { router.push(`/${locale}`); }
      ```
    - Replace with single: `router.push(`/${locale}`)`
    - _Bug_Condition: isBugCondition_WrongLoginRedirect — router.push branches on role_
    - _Expected_Behavior: for ALL roles, router.push called with /${locale} after login_
    - _Preservation: fetchMe, logout, fetchWithRefresh, session restore logic all unchanged_
    - _Requirements: 2.9_

- [x] 9. Fix frontend: replace home page with full-screen splash

  - [x] 9.1 Modify `apps/web/src/app/[locale]/page.tsx`
    - Change `useTranslations('nav')` to `useTranslations('home')` (or import both)
    - Replace `<main className="min-h-screen p-8">` and its `h-64` hero `<div>` with a `<section className="relative min-h-screen flex flex-col items-center justify-center overflow-hidden">`
    - Use `<Image src={IMAGES.hero.src} alt={IMAGES.hero.alt} fill className="object-cover" priority />` as background
    - Add dark overlay `<div className="absolute inset-0 bg-black/40" aria-hidden="true" />`
    - Add app name heading, tagline using `t('tagline')` (i18n key `home.tagline`), and CTA `<Link href={`/${locale}/chat`}>` button using `t('cta')` (i18n key `home.cta`)
    - Remove the duplicate `<nav>` link list (NavBar handles navigation)
    - Accept `params: { locale: string }` prop for the locale-aware CTA href
    - _Bug_Condition: isBugCondition_NoSplash — hero is h-64, no tagline, no CTA_
    - _Expected_Behavior: hero section has min-h-screen, tagline non-empty, CTA href ends with /chat_
    - _Requirements: 2.3, 2.16_

- [x] 10. Fix frontend: create admin panel page

  - [x] 10.1 Create `apps/web/src/app/[locale]/admin-panel/page.tsx`
    - RBAC guard at top: if `user.role !== 'admin'` redirect to `/${locale}` (same pattern as `/admin/page.tsx`)
    - Use `createApiClient` from `@diagno-pilot/api-client` for all API calls
    - Section 1 — User Management: fetch `GET /api/v1/admin/users`, render table with columns: name, email, role, active status; provide role-change action (`PATCH /api/v1/admin/users/:id/role`) and activate/deactivate action (`PATCH /api/v1/admin/users/:id/status`)
    - Section 2 — Statistics Dashboard: fetch `GET /api/v1/admin/stats`, display count cards for `total_patients`, `total_consultations`, `total_documents`, `active_users`
    - Section 3 — Audit Log: fetch `GET /api/v1/audit`, render read-only table with columns: timestamp, actorEmail, action, resource, resourceId
    - Show loading state while fetching; show error message on failure
    - _Bug_Condition: isBugCondition_NoAdminPanel — /admin-panel NOT IN route registry_
    - _Expected_Behavior: admin sees three sections; non-admin redirected to /_
    - _Preservation: /admin document management page completely unchanged_
    - _Requirements: 2.7, 2.8, 3.1_

- [x] 11. Verify all bug condition exploration tests now pass

  - [x] 11.1 Re-run frontend exploration tests
    - **Property 1: Expected Behavior** - All Six Frontend Bugs Fixed
    - **IMPORTANT**: Re-run the SAME tests from task 1 (frontend section) — do NOT write new tests
    - Run `apps/web/src/components/__tests__/NavBar.bug.test.tsx` and `apps/web/src/__tests__/AuthContext.bug.test.tsx`
    - **EXPECTED OUTCOME**: All frontend exploration tests PASS
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.7, 2.9_

  - [x] 11.2 Re-run backend exploration tests
    - **Property 1: Expected Behavior** - All Backend Bugs Fixed
    - **IMPORTANT**: Re-run the SAME tests from task 1 (backend section) — do NOT write new tests
    - Run `backend/tests/test_admin_bugs.py`
    - **EXPECTED OUTCOME**: All backend exploration tests PASS
    - _Requirements: 2.10, 2.11, 2.12, 2.13, 2.14_

- [x] 12. Verify all preservation tests still pass

  - [x] 12.1 Re-run frontend preservation tests
    - **Property 2: Preservation** - No Frontend Regressions
    - **IMPORTANT**: Re-run the SAME tests from task 2 (frontend section) — do NOT write new tests
    - Run `apps/web/src/components/__tests__/NavBar.preservation.test.tsx`
    - **EXPECTED OUTCOME**: All preservation tests PASS
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.8, 3.9, 3.10_

  - [x] 12.2 Re-run backend preservation tests
    - **Property 2: Preservation** - No Backend Regressions
    - **IMPORTANT**: Re-run the SAME tests from task 2 (backend section) — do NOT write new tests
    - Run `backend/tests/test_admin_preservation.py`
    - **EXPECTED OUTCOME**: All preservation tests PASS
    - _Requirements: 3.7, 3.11_

- [x] 13. Checkpoint — Ensure all tests pass
  - Run full frontend test suite: `cd apps/web && npx vitest --run`
  - Run full backend test suite: `cd backend && pytest`
  - Confirm zero failures across all test files
  - Verify active route highlighting works for `/admin-panel` (req 3.9)
  - Verify locale switch FR ↔ EN updates `nav.documents` label in NavBar and mobile drawer (req 3.5, 3.6, 3.8)
  - Ask the user if any questions arise before closing the spec
