# Requirements Document

## Introduction

This document specifies UX improvements for the Diagno-Pilot application, a web and mobile healthcare platform for infectious disease diagnosis and antibiotic prescription targeting healthcare professionals in West Africa (Togo, Benin). The improvements span login experience, diagnosis workflow, chat interfaces, patient management, shared UI components, navigation, accessibility, and error handling. All changes apply to both the Next.js web application and the React Native (Expo) mobile application unless stated otherwise.

## Glossary

- **Login_Page**: The authentication page at `apps/web/src/app/[locale]/login/page.tsx` where healthcare professionals enter credentials to access Diagno-Pilot
- **Diagnose_Page**: The guided diagnosis page at `apps/web/src/app/[locale]/diagnose/page.tsx` (web) and `apps/mobile/app/(tabs)/diagnose.tsx` (mobile) where clinicians input symptoms and receive differential diagnoses
- **Chat_Page**: The Q&A chat page at `apps/web/src/app/[locale]/chat/page.tsx` (web) and `apps/mobile/app/(tabs)/chat.tsx` (mobile) for medical question-answering
- **Patients_Page**: The patient management page at `apps/web/src/app/[locale]/patients/page.tsx` for listing, creating, and viewing patient records
- **SymptomInput**: The shared symptom input component at `packages/ui/src/SymptomInput.tsx` used for structured symptom entry
- **PrescriptionCard**: The shared prescription display component at `packages/ui/src/PrescriptionCard.tsx`
- **PatientCard**: The shared patient display component at `packages/ui/src/PatientCard.tsx`
- **AlertBanner**: The shared alert display component at `packages/ui/src/AlertBanner.tsx` for safety alerts
- **Toast**: The notification component at `apps/web/src/components/Toast.tsx` for transient status messages
- **ConfirmDialog**: The confirmation dialog component at `apps/web/src/components/ConfirmDialog.tsx`
- **SessionHistoryPanel**: The session history sidebar at `apps/web/src/components/SessionHistoryPanel.tsx`
- **LanguageSwitcher**: The locale toggle component at `apps/web/src/components/LanguageSwitcher.tsx`
- **NavBar**: The main navigation bar at `apps/web/src/components/NavBar.tsx`
- **Design_Token_System**: The centralized design tokens defined in `packages/ui/src/tokens.ts` consumed by both web (Tailwind) and mobile (StyleSheet) platforms
- **i18n_System**: The internationalization system using next-intl for web and a custom I18nContext for mobile, supporting French and English locales
- **Healthcare_Professional**: A doctor, nurse, or pharmacist using Diagno-Pilot in a clinical setting

## Requirements

### Requirement 1: Login Page Usability

**User Story:** As a Healthcare_Professional, I want a polished and helpful login experience, so that I can authenticate quickly and recover from mistakes without frustration.

#### Acceptance Criteria

1. WHEN the Login_Page password field is rendered, THE Login_Page SHALL display a toggle button that switches the password field between masked and visible text modes
2. WHEN the Healthcare_Professional clicks the password visibility toggle, THE Login_Page SHALL change the input type between "password" and "text" and update the toggle icon accordingly
3. THE Login_Page SHALL display a "Forgot password" link below the login form that navigates to a placeholder password reset page at `/{locale}/forgot-password`. NOTE: The actual password reset backend flow is out of scope for this spec; the link SHALL render a static page explaining that the feature is coming soon or directing the Healthcare_Professional to contact an administrator
4. WHEN the Healthcare_Professional navigates to the forgot password page, THE page SHALL display the Diagno-Pilot logo, a localized heading, a localized message directing the Healthcare_Professional to contact their administrator, and a link back to the login page
5. WHEN the Healthcare_Professional submits the login form, THE Login_Page SHALL display a localized loading label (e.g., "Signing in…") on the submit button instead of the current contextless "…"
6. WHEN the Healthcare_Professional submits the login form with an empty email field, THE Login_Page SHALL display an inline validation error message below the email field before sending any network request
7. WHEN the Healthcare_Professional submits the login form with an empty password field, THE Login_Page SHALL display an inline validation error message below the password field before sending any network request
8. WHEN the Healthcare_Professional submits the login form with an invalid email format, THE Login_Page SHALL display an inline validation error message indicating the expected format

### Requirement 2: Diagnose Page Progress and Workflow

**User Story:** As a Healthcare_Professional, I want clear visual progress indicators and confirmation safeguards on the diagnosis page, so that I understand where I am in the workflow and do not accidentally lose my results.

#### Acceptance Criteria

1. WHILE the Healthcare_Professional is on the web Diagnose_Page, THE Diagnose_Page SHALL display a visual step progress bar showing the current step within the diagnosis workflow (symptom input, results review, prescription). Each step SHALL be rendered in one of three visual states: completed (checkmark), current (highlighted), or upcoming (dimmed). The step indicators SHALL be display-only and not clickable for navigation
2. WHEN the Healthcare_Professional clicks the "New Diagnosis" button on the Diagnose_Page while results are displayed, THE Diagnose_Page SHALL show a ConfirmDialog asking the Healthcare_Professional to confirm before clearing the current results
3. WHEN the Healthcare_Professional confirms the "New Diagnosis" action in the ConfirmDialog, THE Diagnose_Page SHALL clear all current results and reset the form to the initial state
4. WHEN the Healthcare_Professional cancels the "New Diagnosis" action in the ConfirmDialog, THE Diagnose_Page SHALL keep the current results and form state unchanged
5. WHEN the Diagnose_Page renders structured symptom input fields, THE Diagnose_Page SHALL display visible `<label>` elements above each input field (symptom name, severity, duration) with matching `for`/`id` attribute pairs, instead of relying solely on placeholder text

### Requirement 3: Chat Page Enhancements

**User Story:** As a Healthcare_Professional, I want a richer chat experience with empty state guidance, input feedback, and message utilities, so that I can interact with the medical assistant efficiently.

#### Acceptance Criteria

1. WHEN the web Chat_Page has no messages, THE Chat_Page SHALL display an empty state illustration with a localized prompt guiding the Healthcare_Professional to ask a question
2. WHILE the Healthcare_Professional is typing in the mobile Chat_Page input field, THE Chat_Page SHALL display a character count indicator showing the current character count relative to the 1000-character maximum
3. WHILE the Chat_Page is waiting for a response from the backend, THE Chat_Page SHALL display a "connecting" indicator during the initial phase (before the first SSE token is received) and transition to a "thinking" indicator once the first token arrives. The detection SHALL be client-side based on SSE token receipt timing, requiring no backend changes
4. WHEN the Healthcare_Professional hovers over an assistant message on the web Chat_Page, THE Chat_Page SHALL display a "Copy" button that copies the message content to the clipboard. This copy feature SHALL also apply to assistant messages in the DocumentChat component on the documents page
5. WHEN the Healthcare_Professional clicks the "Copy" button on a chat message, THE Chat_Page SHALL copy the message text to the clipboard and display a brief localized confirmation feedback (e.g., "Copied!")

### Requirement 4: Patient Management Improvements

**User Story:** As a Healthcare_Professional, I want localized patient management controls, loading feedback, search capability, and unsaved-changes protection, so that I can manage patient records reliably in my preferred language.

#### Acceptance Criteria

1. THE Patients_Page SHALL render all user-visible strings through the i18n_System, replacing any hardcoded French strings such as "Créer une infirmière", "Créez votre premier dossier patient pour commencer.", and Zod validation messages (e.g., "Le nom est obligatoire", "Le poids doit être un nombre positif") with localized translation keys
2. WHILE the CreatePatientModal form is being submitted, THE Patients_Page SHALL disable all form inputs and display a spinner overlay on the modal content to indicate the submission is in progress
3. THE Patients_Page SHALL provide a search input field that performs client-side filtering of the currently loaded patient list by patient name in real time as the Healthcare_Professional types. NOTE: Server-side search across all patients is out of scope for this spec
4. WHEN the Healthcare_Professional has unsaved changes in the CreatePatientModal and attempts to close the modal or navigate away, THE Patients_Page SHALL display a ConfirmDialog warning about unsaved changes before proceeding

### Requirement 5: Shared UI Component Quality

**User Story:** As a Healthcare_Professional, I want consistent, localized, and visually distinct UI components, so that the interface is predictable and accessible across all pages.

#### Acceptance Criteria

1. THE SymptomInput component SHALL use the Design_Token_System (colors, spacing, radius, typography from `packages/ui/src/tokens.ts`) instead of inline CSS styles for all visual properties
2. THE PrescriptionCard component SHALL accept label text as props (Dose, Frequency, Duration, Route, "Capped to adult dose") so that consuming pages can pass localized strings from their respective i18n_System, instead of rendering hardcoded English strings. This prop-based approach is required because `packages/ui` is shared between web (next-intl) and mobile (I18nContext) which use different i18n mechanisms
3. THE PatientCard component SHALL accept label text as props (Weight, Date of birth, Allergies, Comorbidities, Medications, "Unknown patient", "None", "known", "active") so that consuming pages can pass localized strings from their respective i18n_System, instead of rendering hardcoded English strings
4. THE Toast component SHALL display a dismiss button that allows the Healthcare_Professional to manually close the notification before the auto-dismiss timer expires
5. WHEN the Toast dismiss button is clicked, THE Toast SHALL immediately hide and invoke the onClose callback
6. THE AlertBanner component SHALL render a visually distinct icon for the "critical" level (e.g., a stop/error icon) that is different from the "warning" level icon (e.g., a triangle/caution icon)

### Requirement 6: Navigation and Layout Enhancements

**User Story:** As a Healthcare_Professional, I want breadcrumb navigation, session search, proper icons, and scroll-to-top functionality, so that I can navigate the application efficiently on both web and mobile.

#### Acceptance Criteria

1. WHEN the Healthcare_Professional navigates to a nested page (patient detail at `/patients/:id`), THE page layout SHALL display a breadcrumb trail showing the navigation path from the root to the current page. Other nested pages (admin sub-pages, etc.) are out of scope for this spec
2. THE SessionHistoryPanel SHALL provide a search input field that filters displayed session entries by preview text as the Healthcare_Professional types
3. WHEN the Healthcare_Professional scrolls down more than one viewport height on the web Diagnose_Page, Patients_Page, or patient detail page, THE page layout SHALL display a "back to top" floating button. Mobile pages and chat pages (which have their own scroll containers) are excluded
4. WHEN the Healthcare_Professional clicks the "back to top" button, THE page layout SHALL smoothly scroll the page to the top

### Requirement 7: Accessibility Improvements

**User Story:** As a Healthcare_Professional, I want accessible form inputs, adequately sized interactive elements, and non-color-dependent indicators, so that the application is usable by clinicians with varying abilities and in diverse clinical environments.

#### Acceptance Criteria

1. THE shared SymptomInput component in `packages/ui/src/SymptomInput.tsx` SHALL display visible `<label>` elements above each input field (symptom name, severity, duration) with matching `for`/`id` attribute pairs, instead of relying solely on `aria-label` attributes and placeholder text
2. THE LanguageSwitcher buttons SHALL have a minimum touch target size of 44×44 CSS pixels and a minimum font size of 14px to meet accessibility guidelines
3. WHEN the mobile Diagnose_Page displays probability indicators for diagnoses, THE Diagnose_Page SHALL include a text label (e.g., "High", "Medium", "Low") alongside the color indicator so that color-blind Healthcare_Professionals can interpret the probability
4. THE ConfirmDialog component SHALL render the title and message text through the i18n_System instead of hardcoded English strings, so that the dialog is displayed in the Healthcare_Professional's selected locale
5. THE SessionHistoryPanel ConfirmDialog for session deletion SHALL render its title, message, confirm label, and cancel label through the i18n_System

### Requirement 8: Error Handling and Resilience

**User Story:** As a Healthcare_Professional, I want actionable error messages, connectivity awareness, and loading timeout feedback, so that I can understand and recover from failures in this network-dependent medical application.

#### Acceptance Criteria

1. WHEN a non-streaming network request fails on the Patients_Page, Diagnose_Page, or Documents_Page, THE application SHALL display an error message that includes a specific description of what went wrong and a suggested recovery action (e.g., "Unable to load patient list. Check your internet connection and try again."). Streaming chat requests retain their existing error handling patterns (retry buttons, stream interruption messages)
2. WHILE the application detects that the device has no network connectivity, THE application SHALL display a persistent offline indicator banner informing the Healthcare_Professional that the application requires an internet connection. On web, detection SHALL use the `navigator.onLine` API supplemented by a periodic lightweight health-check fetch to the backend. On mobile, detection SHALL use the `@react-native-community/netinfo` library
3. WHEN network connectivity is restored, THE application SHALL automatically hide the offline indicator banner
4. WHEN a non-streaming network request has been pending for more than 15 seconds without a response, THE application SHALL display a timeout feedback message informing the Healthcare_Professional that the request is taking longer than expected and offering an option to retry or cancel
5. IF a non-streaming network request exceeds 30 seconds without a response, THEN THE application SHALL automatically cancel the request via AbortController and display an error message with a retry option

### Requirement 9: Mobile Internationalization Gaps

**User Story:** As a Healthcare_Professional using the mobile app, I want all interface text displayed in my selected language, so that I can use the application comfortably in French or English.

#### Acceptance Criteria

1. THE mobile Diagnose_Page SHALL render all user-visible strings — including step indicator labels ("Symptômes", "Diagnostic", "Prescription"), section titles ("Saisir les symptômes", "Diagnostics différentiels"), button labels ("Obtenir les diagnostics →", "Recommencer", "Nouvelle consultation", "Changer de diagnostic"), alert headings ("Alertes critiques"), and inline text ("CIM-10", "Symptômes concordants") — through the i18n_System instead of hardcoded French strings
2. THE mobile Chat_Page SHALL render all user-visible strings (e.g., "Posez une question sur les antibiotiques ou les maladies infectieuses.", "Votre question…", "Sources :", "Désolé, une erreur est survenue. Veuillez réessayer.") through the i18n_System instead of hardcoded French strings
