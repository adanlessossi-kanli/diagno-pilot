# Requirements Document

## Introduction

Diagno-Pilot is a medical diagnostic assistance application used by healthcare professionals. It runs as a Next.js web app (`apps/web`) and a React Native mobile app (`apps/mobile`). The current UI is functional but visually inconsistent: it mixes ad-hoc Tailwind utility classes on the web side with inline `StyleSheet` objects on mobile, lacks a coherent design token system, and presents a plain appearance that does not convey the trust and professionalism expected in a clinical context.

This feature refactors the UI of both platforms to achieve a professional, consistent look and feel. The refactor must be purely visual — no API contracts, routing logic, authentication flows, or business logic may be altered — and all existing automated tests must continue to pass.

## Glossary

- **Design_System**: The shared set of color tokens, typography scales, spacing values, border radii, and shadow definitions that govern the visual appearance of both platforms.
- **Web_App**: The Next.js application located at `apps/web`.
- **Mobile_App**: The React Native / Expo application located at `apps/mobile`.
- **Component**: A reusable UI element (e.g., NavBar, PatientCard, Toast, Button).
- **Token**: A named design variable (e.g., `color-primary-600`, `radius-md`) that maps to a concrete value.
- **Contrast_Ratio**: The luminance ratio between foreground and background colors as defined by WCAG 2.1.
- **Breaking_Change**: Any modification that alters a public prop interface, exported type, API call, routing path, or authentication behavior.
- **Skeleton_Loader**: The animated placeholder shown while data is being fetched.
- **Toast**: The transient notification component shown after user actions.
- **Alert_Banner**: The component that displays safety alerts (critical / warning / info) in the diagnostic flow.

---

## Requirements

### Requirement 1: Design Token System

**User Story:** As a developer, I want a single source of truth for colors, typography, spacing, and radii, so that visual changes can be made consistently across both platforms without hunting through individual files.

#### Acceptance Criteria

1. THE Design_System SHALL define a primary color palette with at least five shade steps (50, 100, 300, 600, 700) using a blue hue consistent with the existing `#2563eb` brand color.
2. THE Design_System SHALL define a neutral/gray palette with at least six shade steps (50, 100, 200, 500, 700, 900).
3. THE Design_System SHALL define semantic color tokens for `success`, `warning`, `error`, and `info` states, each with a background, border, and text variant.
4. THE Design_System SHALL define a typography scale with at least four named sizes: `xs` (11–12 px), `sm` (13–14 px), `base` (15–16 px), and `lg` (18–20 px).
5. THE Design_System SHALL define a spacing scale using multiples of 4 px (4, 8, 12, 16, 24, 32, 48).
6. THE Design_System SHALL define border-radius tokens: `sm` (4 px), `md` (8 px), `lg` (12 px), `xl` (16 px), `full` (9999 px).
7. THE Design_System SHALL define elevation/shadow tokens for at least three levels: `sm`, `md`, `lg`.
8. WHEN the Design_System tokens are updated, THE Web_App AND Mobile_App SHALL reflect the change without requiring per-component edits.

---

### Requirement 2: Web App — Global Layout and Typography

**User Story:** As a clinician using the web app, I want a clean, well-spaced layout with readable typography, so that I can focus on patient data without visual clutter.

#### Acceptance Criteria

1. THE Web_App SHALL apply a consistent base font family (system-ui or Inter) to all pages via the root layout.
2. THE Web_App SHALL set a maximum content width of 1280 px and center it horizontally on all pages.
3. THE Web_App SHALL use a minimum body background color of `gray-50` (`#f9fafb`) to distinguish content areas from the page background.
4. WHEN a page is rendered, THE Web_App SHALL apply consistent vertical padding of at least 24 px between the NavBar and the page content.
5. THE Web_App SHALL use the typography scale tokens for all heading (`h1`–`h3`) and body text elements.
6. WHEN text is rendered on a colored background, THE Web_App SHALL maintain a Contrast_Ratio of at least 4.5:1 for normal text and 3:1 for large text (≥ 18 px bold or ≥ 24 px regular).

---

### Requirement 3: Web App — NavBar Refinement

**User Story:** As a clinician, I want a polished navigation bar with clear active-state indicators and a professional brand presence, so that I always know where I am in the application.

#### Acceptance Criteria

1. THE NavBar SHALL display the application name "Diagno-Pilot" as a branded logo/wordmark on the left side, visible on all screen sizes.
2. THE NavBar SHALL use a subtle bottom border and a white background to visually separate it from page content.
3. WHEN a navigation link is active, THE NavBar SHALL highlight it using the primary color token with an underline or pill indicator that meets the 3:1 Contrast_Ratio requirement.
4. WHEN a navigation link is hovered, THE NavBar SHALL apply a smooth color transition within 150 ms.
5. THE NavBar SHALL display the authenticated user's full name and role in a visually distinct but non-intrusive style (e.g., muted text, avatar initials badge).
6. WHEN the viewport width is below 768 px, THE NavBar SHALL render a mobile drawer that opens with a slide-in animation of at most 250 ms.
7. THE NavBar SHALL preserve all existing accessibility attributes (`aria-label`, `aria-expanded`, `aria-current`) without modification.

---

### Requirement 4: Web App — Button and Form Control Styles

**User Story:** As a clinician filling in patient data or submitting a diagnosis, I want buttons and form controls that are visually consistent and clearly communicate their state, so that I can interact confidently without errors.

#### Acceptance Criteria

1. THE Web_App SHALL define at least three button variants: `primary` (filled), `secondary` (outlined), and `ghost` (text-only).
2. WHEN a button is in the `disabled` state, THE Web_App SHALL render it with reduced opacity (≤ 50 %) and a `not-allowed` cursor.
3. WHEN a button is in the `loading` state, THE Web_App SHALL display a spinner icon alongside the label text.
4. THE Web_App SHALL apply consistent focus-ring styles (2 px offset ring using the primary color token) to all interactive form controls.
5. THE Web_App SHALL apply consistent border, padding, and border-radius tokens to all `<input>`, `<select>`, and `<textarea>` elements.
6. WHEN a form field has a validation error, THE Web_App SHALL render a red border and an error message below the field using the `error` semantic color tokens.
7. WHEN a form field receives focus, THE Web_App SHALL apply a visible focus indicator that meets the 3:1 Contrast_Ratio requirement against the surrounding background.

---

### Requirement 5: Web App — Card and Surface Styles

**User Story:** As a clinician viewing patient records or diagnosis results, I want cards and content surfaces that are visually elevated and easy to scan, so that I can quickly identify relevant information.

#### Acceptance Criteria

1. THE Web_App SHALL apply a white background, `md` border-radius token, and `sm` shadow token to all card-style surfaces (PatientCard, PrescriptionDetails, diagnosis result items).
2. WHEN a PatientCard is hovered, THE Web_App SHALL apply a `md` shadow token transition within 200 ms.
3. THE Web_App SHALL use consistent internal padding of 16–24 px for all card surfaces.
4. THE Web_App SHALL visually distinguish section headers within cards using a slightly larger font size and `font-semibold` weight.
5. THE Web_App SHALL render the probability progress bar in the diagnosis results using the primary color token with rounded ends.

---

### Requirement 6: Web App — Alert Banner and Toast Styles

**User Story:** As a clinician reviewing safety alerts, I want alert banners and toast notifications that are immediately recognizable by severity level, so that I can act on critical information without delay.

#### Acceptance Criteria

1. THE Web_App SHALL render `critical` Alert_Banners with a red left-border accent (4 px), red background token, and bold red text using the `error` semantic color tokens.
2. THE Web_App SHALL render `warning` Alert_Banners with an amber left-border accent, amber background token, and amber text using the `warning` semantic color tokens.
3. THE Web_App SHALL render `info` Alert_Banners with a blue left-border accent, blue background token, and blue text using the `info` semantic color tokens.
4. THE Toast SHALL use the `success`, `error`, and `info` semantic color tokens for its three variants.
5. WHEN a Toast appears, THE Web_App SHALL animate it with a slide-in-from-top or fade-in transition of at most 300 ms.
6. THE Web_App SHALL render the critical alert confirmation block with a visually prominent double-border or elevated card treatment to draw attention.

---

### Requirement 7: Web App — Empty State and Skeleton Loader

**User Story:** As a clinician waiting for data or viewing an empty list, I want informative empty states and smooth loading placeholders, so that the application feels responsive and polished.

#### Acceptance Criteria

1. THE EmptyState component SHALL use the primary color token for its icon/illustration accent color.
2. THE EmptyState component SHALL render the action button using the `primary` button variant defined in Requirement 4.
3. THE Skeleton_Loader SHALL use the `gray-100` and `gray-200` tokens for its base and shimmer colors.
4. WHEN the Skeleton_Loader is rendered, THE Web_App SHALL apply a smooth pulse animation with a cycle duration between 1.5 s and 2 s.

---

### Requirement 8: Web App — Pagination Styles

**User Story:** As a clinician browsing a large patient list, I want a pagination control that is easy to read and clearly shows the current page, so that I can navigate efficiently.

#### Acceptance Criteria

1. THE Pagination component SHALL render the active page button using the primary color token (filled background, white text).
2. THE Pagination component SHALL render inactive page buttons with a neutral border and hover state using the `gray-50` background token.
3. WHEN a navigation button (previous/next) is disabled, THE Pagination component SHALL render it with reduced opacity (≤ 40 %) and a `not-allowed` cursor.
4. THE Pagination component SHALL apply the `md` border-radius token to all page buttons.

---

### Requirement 9: Web App — Login Page

**User Story:** As a clinician opening the application for the first time, I want a professional login page that conveys trust and brand identity, so that I feel confident entering my credentials.

#### Acceptance Criteria

1. THE Web_App login page SHALL display the "Diagno-Pilot" brand name prominently above the login form.
2. THE Web_App login page SHALL use a two-column layout on viewports ≥ 1024 px wide, with a branded side image and the login form.
3. THE Web_App login page SHALL apply the `lg` border-radius token and `md` shadow token to the login form card.
4. WHEN login credentials are invalid, THE Web_App SHALL display the error using the `error` semantic color tokens with a left-border accent.
5. THE Web_App login page SHALL apply the `primary` button variant to the submit button.

---

### Requirement 10: Mobile App — Design Token Adoption

**User Story:** As a developer maintaining the mobile app, I want the mobile components to use the shared design tokens, so that visual updates are applied consistently without editing each StyleSheet individually.

#### Acceptance Criteria

1. THE Mobile_App SHALL reference the Design_System color tokens for all background, border, and text colors in component StyleSheets.
2. THE Mobile_App SHALL reference the Design_System spacing tokens for all padding and margin values in component StyleSheets.
3. THE Mobile_App SHALL reference the Design_System border-radius tokens for all `borderRadius` values in component StyleSheets.
4. WHEN a Design_System token value is changed, THE Mobile_App components SHALL reflect the updated value without requiring individual StyleSheet edits.

---

### Requirement 11: Mobile App — Tab Bar and Header Refinement

**User Story:** As a clinician using the mobile app, I want a polished tab bar and screen headers that match the brand identity, so that the app feels professional and trustworthy.

#### Acceptance Criteria

1. THE Mobile_App tab bar SHALL use the primary color token (`#2563eb`) for the active tab icon and label tint.
2. THE Mobile_App tab bar SHALL use the `gray-400` token for inactive tab icon and label tint.
3. THE Mobile_App screen headers SHALL use the primary color token as the background color and white as the title color.
4. THE Mobile_App tab bar icons SHALL be replaced with vector icons (e.g., from `@expo/vector-icons`) instead of emoji characters, maintaining the same semantic meaning.
5. WHEN a tab is selected, THE Mobile_App SHALL apply a smooth color transition of at most 200 ms.

---

### Requirement 12: Mobile App — Card and List Item Styles

**User Story:** As a clinician viewing patient cards and diagnosis results on mobile, I want visually elevated cards with clear information hierarchy, so that I can scan data quickly on a small screen.

#### Acceptance Criteria

1. THE MobilePatientCard SHALL apply the `lg` border-radius token, a white background, and the `sm` shadow/elevation token.
2. THE MobilePatientCard SHALL render the patient avatar using the primary color token as the background with white initials text instead of an emoji.
3. THE MobilePrescriptionCard SHALL apply the `lg` border-radius token and a white background with a subtle border using the `gray-200` token.
4. THE Mobile_App diagnosis cards SHALL use a colored left-border accent (4 px) whose color maps to the probability level: green (≥ 70 %), amber (40–69 %), red (< 40 %).
5. WHEN a patient card or diagnosis card is pressed, THE Mobile_App SHALL apply a visual press feedback (opacity reduction to 0.7) within 100 ms.

---

### Requirement 13: Mobile App — Alert Banner Refinement

**User Story:** As a clinician reviewing safety alerts on mobile, I want alert banners that are visually consistent with the web app and immediately recognizable by severity, so that critical information is never missed.

#### Acceptance Criteria

1. THE MobileAlertBanner SHALL use the `error` semantic color tokens for `critical` level alerts.
2. THE MobileAlertBanner SHALL use the `warning` semantic color tokens for `warning` level alerts.
3. THE MobileAlertBanner SHALL use the `info` semantic color tokens for `info` level alerts.
4. THE MobileAlertBanner SHALL replace emoji icons with vector icons from `@expo/vector-icons` for `critical`, `warning`, and `info` levels.
5. THE MobileAlertBanner SHALL apply a 4 px left-border accent using the corresponding semantic border color token.

---

### Requirement 14: Mobile App — Login Screen

**User Story:** As a clinician opening the mobile app for the first time, I want a professional login screen that matches the web app's brand identity, so that the experience feels cohesive.

#### Acceptance Criteria

1. THE Mobile_App login screen SHALL display the "Diagno-Pilot" brand name using the primary color token and a font size of at least 24 px.
2. THE Mobile_App login screen SHALL apply the `lg` border-radius token and a shadow/elevation of at least 3 to the login card.
3. THE Mobile_App login screen SHALL apply the `primary` button style (primary color background, white text, `md` border-radius) to the login button.
4. THE Mobile_App login screen SHALL use the `gray-50` token as the screen background color.
5. WHEN login fails, THE Mobile_App SHALL display an inline error message using the `error` semantic color tokens instead of a native Alert dialog.

---

### Requirement 15: No Breaking Changes

**User Story:** As a developer, I want the UI refactor to be purely visual, so that no existing functionality, API contracts, or test coverage is broken.

#### Acceptance Criteria

1. THE Web_App SHALL export the same component prop interfaces after the refactor as before.
2. THE Mobile_App SHALL export the same component prop interfaces after the refactor as before.
3. WHEN the full test suite is executed after the refactor, THE Web_App test suite SHALL pass with zero failures.
4. WHEN the full test suite is executed after the refactor, THE Mobile_App test suite SHALL pass with zero failures.
5. THE refactor SHALL NOT modify any API client calls, routing paths, authentication logic, or i18n message keys.
6. THE refactor SHALL NOT alter any `aria-label`, `aria-expanded`, `aria-current`, `role`, or `aria-live` attributes already present in the codebase.
