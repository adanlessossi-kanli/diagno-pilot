# Bugfix Requirements Document

## Introduction

The Diagno-Pilot web application has several UI/UX deficiencies that degrade the user experience and create inconsistencies between the visual identity, navigation structure, and role-based access model. Specifically: the app lacks a branded SVG logo/icon; the home page does not leverage the available African healthcare imagery for a compelling splash screen; the navigation menu order and labels do not match the intended information architecture; the existing `/admin` document-management page is mislabeled as "Administration" instead of "Documents"; there is no dedicated admin panel for user management, statistics, and audit logs; and the backend is missing the three groups of endpoints required by the new `/admin-panel` page (`GET /api/v1/users`, `PATCH /api/v1/users/{id}/role`, `PATCH /api/v1/users/{id}/status`, `GET /api/v1/admin/stats`, `GET /api/v1/audit`). These issues affect all authenticated users and particularly administrators who lack the tooling they need. Additionally, after a successful login the application fails to redirect users to the home page ("Accueil", `/`), resulting in an inconsistent post-login landing experience.

---

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN any page loads THEN the system displays a plain text wordmark "Diagno-Pilot" in the NavBar with no SVG icon or logo, providing no visual brand identity.

1.2 WHEN the login page is displayed THEN the system shows no branded logo, reducing trust and visual coherence.

1.3 WHEN an authenticated user visits the home (`/`) page THEN the system renders a small `h-64` hero image with no full-screen splash, no prominent tagline, and no call-to-action button, failing to make a visually impactful first impression.

1.4 WHEN the NavBar renders its link list THEN the system displays links in the order: Home → Q&A Assistant → Guided Diagnosis → Patients → Administration, which does not match the intended navigation hierarchy.

1.5 WHEN the NavBar renders the document-management link THEN the system labels it "Administration" (i18n key `nav.admin`), causing confusion with the concept of an admin control panel.

1.6 WHEN the `/admin` page title renders THEN the system displays "Administration" (i18n key `admin.title`), which is inconsistent with the page's actual purpose of document management.

1.7 WHEN a user with `admin` role is authenticated THEN the system provides no dedicated admin panel route for user management, statistics, or audit logs.

1.8 WHEN a non-admin user navigates to the admin panel URL THEN the system has no such route to protect, meaning the feature is entirely absent.

1.9 WHEN a user successfully authenticates via the login form THEN the system does NOT redirect them to the home page ("Accueil", route `/`), resulting in an inconsistent post-login landing experience.

1.10 WHEN the frontend admin panel requests user management data THEN the backend has no `GET /api/v1/users` endpoint, no `PATCH /api/v1/users/{id}/role` endpoint, and no `PATCH /api/v1/users/{id}/status` endpoint, making user management impossible.

1.11 WHEN the frontend admin panel requests statistics THEN the backend has no `GET /api/v1/admin/stats` endpoint returning counts of patients, consultations, documents, and active users.

1.12 WHEN the frontend admin panel requests the audit log THEN the backend has no `GET /api/v1/audit` endpoint returning a paginated list of audit events.

---

### Expected Behavior (Correct)

2.1 WHEN any page loads THEN the system SHALL display a custom SVG icon alongside the "Diagno-Pilot" wordmark in the NavBar, reflecting a medical/African visual identity.

2.2 WHEN the login page is displayed THEN the system SHALL render the custom SVG logo prominently, providing brand recognition at the authentication entry point.

2.3 WHEN an authenticated user visits the home (`/`) page THEN the system SHALL display a full-screen or visually prominent splash section using one or more images from `IMAGES` (Unsplash free licence), including the app name, a tagline, and a call-to-action button linking to `/chat`.

2.4 WHEN the NavBar renders its link list THEN the system SHALL display links in the order: Q&A Assistant → Diagnostic guidé → Patients → Documents → Admin (admin-only), matching the intended information architecture. The "Home" / "Accueil" link SHALL be removed from the NavBar link list; navigation to the home page SHALL be achieved via the logo/wordmark which acts as a home link.

2.5 WHEN the NavBar renders the document-management link THEN the system SHALL label it using i18n key `nav.documents` ("Documents" / "Documents"), replacing the former `nav.admin` key for this link.

2.6 WHEN the `/admin` page title renders THEN the system SHALL display the value of i18n key `documents.title` or a dedicated `nav.documents` heading ("Documents" / "Documents") instead of "Administration".

2.7 WHEN a user with `admin` role is authenticated THEN the system SHALL provide a new route (e.g. `/admin-panel`) containing three sections: user management (list, role change, activate/deactivate), statistics dashboard (patients, consultations, documents, active users counts), and a read-only audit log table.

2.8 WHEN a non-admin user attempts to access `/admin-panel` THEN the system SHALL redirect them away (to `/` or `/login`) and SHALL NOT render the admin panel content.

2.9 WHEN a user successfully authenticates via the login form THEN the system SHALL redirect them to the home page (`/`) — the "Accueil" splash screen — regardless of their role.

2.10 WHEN an admin user requests `GET /api/v1/users` THEN the backend SHALL return a list of all users with fields: `id`, `fullName`, `email`, `role`, `isActive`. The endpoint SHALL be restricted to `admin` role only.

2.11 WHEN an admin user sends `PATCH /api/v1/users/{id}/role` with a valid role payload THEN the backend SHALL update the user's role and return the updated user object. The endpoint SHALL be restricted to `admin` role only and SHALL NOT allow an admin to demote themselves.

2.12 WHEN an admin user sends `PATCH /api/v1/users/{id}/status` with `{ "isActive": true|false }` THEN the backend SHALL activate or deactivate the user account and return the updated user object. The endpoint SHALL be restricted to `admin` role only and SHALL NOT allow an admin to deactivate themselves.

2.13 WHEN an admin user requests `GET /api/v1/admin/stats` THEN the backend SHALL return a JSON object with integer counts for: `totalPatients`, `totalConsultations`, `totalDocuments`, `activeUsers`.

2.14 WHEN an admin user requests `GET /api/v1/audit` THEN the backend SHALL return a paginated list of audit events, each with fields: `id`, `timestamp`, `actorId`, `actorEmail`, `action`, `resource`, `resourceId`. The endpoint SHALL be restricted to `admin` role only.

2.15 WHEN the NavBar renders the admin panel link (admin-only) THEN the system SHALL use i18n key `nav.adminPanel` with value "Admin" in both FR and EN locales.

2.16 WHEN the home page splash section renders THEN the tagline and call-to-action button label SHALL use i18n keys `home.tagline` and `home.cta` respectively, with values defined in both `fr.json` and `en.json`.

---

### Unchanged Behavior (Regression Prevention)

3.1 WHEN a user navigates to `/admin` THEN the system SHALL CONTINUE TO display the document upload form and indexed document list with full create/delete functionality.

3.2 WHEN the NavBar renders for a non-admin user THEN the system SHALL CONTINUE TO hide any admin-only links, preserving existing RBAC logic.

3.3 WHEN the NavBar renders for an unauthenticated user THEN the system SHALL CONTINUE TO return null (hide the NavBar entirely).

3.4 WHEN the LanguageSwitcher or logout button is used THEN the system SHALL CONTINUE TO function correctly regardless of nav label changes.

3.5 WHEN the FR locale is active THEN the system SHALL CONTINUE TO display all nav labels, page titles, and UI strings in French using the `fr.json` i18n file.

3.6 WHEN the EN locale is active THEN the system SHALL CONTINUE TO display all nav labels, page titles, and UI strings in English using the `en.json` i18n file.

3.7 WHEN existing API calls to `/api/v1/documents`, `/api/v1/patients`, `/api/v1/diagnose`, or `/api/v1/chat` are made THEN the system SHALL CONTINUE TO use the same request/response contracts without modification.

3.8 WHEN the mobile hamburger drawer is opened THEN the system SHALL CONTINUE TO render the reordered nav links correctly within the drawer.

3.9 WHEN the active route highlighting logic runs THEN the system SHALL CONTINUE TO correctly highlight the current page link for all routes including the new `/admin-panel` route.

3.10 WHEN a user is already authenticated and navigates directly to `/login` THEN the system SHALL CONTINUE TO redirect them away from the login page (no regression on existing auth guard behavior).

3.11 WHEN existing backend endpoints (`/api/v1/auth`, `/api/v1/patients`, `/api/v1/diagnose`, `/api/v1/chat`, `/api/v1/documents`, `/api/v1/files`, `/api/v1/alerts`) are called THEN the system SHALL CONTINUE TO respond with the same request/response contracts as before — the new admin endpoints SHALL NOT affect existing routes.

---

## Bug Condition Pseudocode

### Bug Condition Functions

```pascal
FUNCTION isBugCondition_NoLogo(X)
  INPUT: X = rendered NavBar or login page component
  OUTPUT: boolean
  RETURN X contains no SVG logo element
END FUNCTION

FUNCTION isBugCondition_NoSplash(X)
  INPUT: X = rendered home page component
  OUTPUT: boolean
  RETURN X.heroHeight < viewport_height AND X.hasCallToAction = false
END FUNCTION

FUNCTION isBugCondition_WrongNavOrder(X)
  INPUT: X = rendered NavBar links array
  OUTPUT: boolean
  RETURN X[0].label ≠ "Q&A Assistant" OR X[3].label ≠ "Documents"
END FUNCTION

FUNCTION isBugCondition_MislabeledDocuments(X)
  INPUT: X = i18n key used for document-management nav link
  OUTPUT: boolean
  RETURN X = "nav.admin" (instead of "nav.documents")
END FUNCTION

FUNCTION isBugCondition_NoAdminPanel(X)
  INPUT: X = route registry
  OUTPUT: boolean
  RETURN "/admin-panel" NOT IN X.routes
END FUNCTION

FUNCTION isBugCondition_WrongLoginRedirect(X)
  INPUT: X = post-login navigation target
  OUTPUT: boolean
  RETURN X.redirectTarget ≠ "/"
END FUNCTION

FUNCTION isBugCondition_MissingAdminEndpoints(X)
  INPUT: X = backend route registry
  OUTPUT: boolean
  RETURN "GET /api/v1/users" NOT IN X.routes
         OR "PATCH /api/v1/users/{id}/role" NOT IN X.routes
         OR "PATCH /api/v1/users/{id}/status" NOT IN X.routes
         OR "GET /api/v1/admin/stats" NOT IN X.routes
         OR "GET /api/v1/audit" NOT IN X.routes
END FUNCTION
```

### Fix Checking Properties

```pascal
// Property: Logo present in NavBar and login page
FOR ALL X WHERE isBugCondition_NoLogo(X) DO
  result ← render'(X)
  ASSERT result contains SVG logo element with medical/African design
END FOR

// Property: Splash screen on home page
FOR ALL X WHERE isBugCondition_NoSplash(X) DO
  result ← renderHomePage'(X)
  ASSERT result.splashSection.isFullScreenOrProminent = true
    AND result.splashSection.hasTagline = true
    AND result.splashSection.hasCallToAction = true
END FOR

// Property: Correct nav order
FOR ALL X WHERE isBugCondition_WrongNavOrder(X) DO
  result ← renderNavBar'(X)
  ASSERT result.links[0].key = "chat"
    AND result.links[1].key = "diagnose"
    AND result.links[2].key = "patients"
    AND result.links[3].key = "documents"
END FOR

// Property: Documents label replaces Administration
FOR ALL X WHERE isBugCondition_MislabeledDocuments(X) DO
  result ← resolveI18nKey'("nav.documents")
  ASSERT result.fr = "Documents" AND result.en = "Documents"
END FOR

// Property: Admin panel route exists and is RBAC-protected
FOR ALL X WHERE isBugCondition_NoAdminPanel(X) DO
  result ← routeRegistry'
  ASSERT "/admin-panel" IN result.routes
    AND result.routes["/admin-panel"].requiredRole = "admin"
END FOR

// Property: Post-login redirect to Accueil
FOR ALL X WHERE isBugCondition_WrongLoginRedirect(X) DO
  result ← handleLoginSuccess'(X)
  ASSERT result.redirectTarget = "/"
END FOR

// Property: Admin backend endpoints exist and are RBAC-protected
FOR ALL X WHERE isBugCondition_MissingAdminEndpoints(X) DO
  ASSERT GET /api/v1/users WITH admin token → 200 with user list
  ASSERT PATCH /api/v1/users/{id}/role WITH admin token → 200 with updated user
  ASSERT PATCH /api/v1/users/{id}/status WITH admin token → 200 with updated user
  ASSERT GET /api/v1/admin/stats WITH admin token → 200 with stats object
  ASSERT GET /api/v1/audit WITH admin token → 200 with paginated audit events
  ASSERT GET /api/v1/users WITH non-admin token → 403
  ASSERT GET /api/v1/admin/stats WITH non-admin token → 403
  ASSERT GET /api/v1/audit WITH non-admin token → 403
END FOR
```

### Preservation Checking

```pascal
// Property: Preservation Checking
FOR ALL X WHERE NOT isBugCondition_*(X) DO
  ASSERT F(X) = F'(X)
  // Specifically:
  // - /admin document management still works
  // - RBAC hiding of admin links for non-admin users unchanged
  // - NavBar hidden for unauthenticated users unchanged
  // - i18n FR/EN translations for all other keys unchanged
  // - All existing API contracts unchanged
END FOR
```
