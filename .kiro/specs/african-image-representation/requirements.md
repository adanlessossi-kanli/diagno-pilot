# Requirements Document

## Introduction

The Diagno-Pilot web application must consistently represent African medical professionals and patients across all pages that display images. Currently the centralised image registry (`apps/web/src/lib/images.ts`) contains entries whose alt-text claims African subjects, but the actual Unsplash photo IDs may resolve to non-African subjects. This feature ensures every image entry in the registry — and every page that consumes it (login, homepage, diagnose, patients) — exclusively features African people and African healthcare contexts.

## Glossary

- **Image_Registry**: The TypeScript module `apps/web/src/lib/images.ts` that exports the `IMAGES` constant used by all pages.
- **Image_Entry**: A single record in the `IMAGES` constant containing `src`, `alt`, `source`, and `licence` fields.
- **African_Subject**: A photograph whose primary subjects are visibly of African descent and/or set in an African healthcare environment.
- **Page_Component**: Any Next.js page component under `apps/web/src/app/[locale]/` that renders an `<Image>` element sourced from the Image_Registry.
- **Alt_Text**: The `alt` field of an Image_Entry, used for accessibility and describing image content.
- **Unsplash**: The image hosting service used as the source for all application images.

## Requirements

### Requirement 1: All Image Registry Entries Must Feature African Subjects

**User Story:** As a product owner, I want every image in the registry to depict African medical professionals or patients, so that the application authentically represents the African healthcare context it serves.

#### Acceptance Criteria

1. THE Image_Registry SHALL contain only Image_Entry records whose `src` URLs resolve to photographs featuring African subjects.
2. THE Image_Registry SHALL include entries for all keys currently consumed by Page_Components: `hero`, `loginSide`, `diagnoseHeader`, and `patientsEmpty`.
3. WHEN a new Image_Entry is added to the Image_Registry, THE Image_Registry SHALL require the entry to include a `src`, `alt`, `source`, and `licence` field.
4. THE Image_Registry SHALL define the `patientsEmpty` key that is referenced by the patients page, so that no runtime `undefined` access occurs.
5. WHEN the Image_Registry is updated, all existing Image_Entry keys (`hero`, `consultation`, `medecin`, `infirmiere`, `patient`, `equipe`, `diagnoseHeader`) SHALL be preserved and remain accessible to any component that references them.

### Requirement 2: Login Page Image Must Depict an African Healthcare Scene

**User Story:** As a user opening the login page, I want to see an image of an African healthcare professional, so that the application feels relevant to my context from the first screen.

#### Acceptance Criteria

1. WHEN the login page is rendered, THE Login_Page SHALL display the `loginSide` Image_Entry from the Image_Registry.
2. THE `loginSide` Image_Entry SHALL reference a photograph of an African medical professional or healthcare scene.
3. THE `loginSide` Image_Entry SHALL have an `alt` value that accurately describes the African subject depicted.

### Requirement 3: Homepage Hero Image Must Depict an African Healthcare Scene

**User Story:** As a user on the homepage, I want to see an African medical professional in the hero image, so that the application's identity is immediately clear.

#### Acceptance Criteria

1. WHEN the homepage is rendered, THE Homepage SHALL display the `hero` Image_Entry from the Image_Registry.
2. THE `hero` Image_Entry SHALL reference a photograph of an African medical professional or patient interaction.
3. THE `hero` Image_Entry SHALL have an `alt` value that accurately describes the African subject depicted.

### Requirement 4: Diagnose Page Header Image Must Depict an African Healthcare Scene

**User Story:** As a clinician using the diagnose page, I want the header image to show an African doctor at work, so that the interface reflects the real-world context of use.

#### Acceptance Criteria

1. WHEN the diagnose page is rendered, THE Diagnose_Page SHALL display the `diagnoseHeader` Image_Entry from the Image_Registry.
2. THE `diagnoseHeader` Image_Entry SHALL reference a photograph of an African medical professional conducting a clinical assessment.
3. THE `diagnoseHeader` Image_Entry SHALL have an `alt` value that accurately describes the African subject depicted.

### Requirement 5: Patients Page Empty-State Image Must Depict an African Healthcare Scene

**User Story:** As a clinician on the patients page with no records yet, I want the empty-state illustration to show an African healthcare context, so that the experience remains culturally consistent.

#### Acceptance Criteria

1. WHEN the patients page renders an empty patient list, THE Patients_Page SHALL display the `patientsEmpty` Image_Entry from the Image_Registry.
2. THE `patientsEmpty` Image_Entry SHALL reference a photograph or illustration featuring an African healthcare context.
3. THE `patientsEmpty` Image_Entry SHALL have an `alt` value that accurately describes the African subject depicted.

### Requirement 6: Alt Text Accuracy and Accessibility

**User Story:** As a user relying on assistive technology, I want all image alt texts to accurately describe the African subjects shown, so that I receive an equivalent experience.

#### Acceptance Criteria

1. THE Image_Registry SHALL ensure every Image_Entry `alt` field describes the actual content of the photograph, including the African identity of the subjects where visible.
2. WHEN an Image_Entry `alt` field claims an African subject, THE Image_Registry SHALL reference a `src` URL that resolves to a photograph matching that description.
3. THE Image_Registry SHALL not use generic or misleading alt text that misrepresents the image content.

### Requirement 7: Image Source Traceability

**User Story:** As a developer maintaining the registry, I want each image entry to document its source URL and licence, so that compliance and attribution can be verified at any time.

#### Acceptance Criteria

1. THE Image_Registry SHALL include a `source` field for every Image_Entry containing the direct Unsplash page URL for the photograph.
2. THE Image_Registry SHALL include a `licence` field for every Image_Entry stating the applicable licence (e.g., "Unsplash Licence libre").
3. WHEN a developer adds or updates an Image_Entry, THE Image_Registry SHALL require both `source` and `licence` fields to be populated.

### Requirement 8: Missing `loginSide` Key Must Be Added to the Image Registry

**User Story:** As a developer, I want the `loginSide` key to exist in the Image_Registry, so that the login page renders without a runtime crash.

#### Acceptance Criteria

1. WHEN the `LoginPage` component renders, THE system SHALL NOT throw `TypeError: Cannot read properties of undefined (reading 'src')`.
2. THE Image_Registry SHALL define a `loginSide` key containing a valid `ImageEntry` with `src`, `alt`, `source`, and `licence` fields.
3. THE `loginSide` Image_Entry SHALL reference an African healthcare photograph consistent with Requirement 2.

### Requirement 9: API Client Must Forward Session Cookies on All Requests

**User Story:** As a user with an active session, I want the application to correctly restore my session on page load, so that I am not unexpectedly logged out.

#### Acceptance Criteria

1. WHEN `AuthContext` mounts and calls `GET /api/v1/auth/me`, THE system SHALL NOT receive `ERR_EMPTY_RESPONSE`.
2. THE `get()` helper in the API client (`packages/api-client/index.ts`) SHALL include `credentials: 'include'` in every `fetch` call so that httpOnly session cookies are forwarded to the backend.
3. THE `post()`, `put()`, `del()`, and `postForm()` helpers SHALL also include `credentials: 'include'` to ensure consistent cookie forwarding across all request types.
4. WHEN a user is not authenticated and `auth/me` returns a 401, THE system SHALL CONTINUE TO set `user` to `null` and redirect to the login page.
