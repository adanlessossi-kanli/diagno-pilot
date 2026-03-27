# Requirements Document

## Introduction

Diagno-Pilot currently translates only UI strings (via next-intl on the web and an I18nContext on mobile). Medical content — diagnoses returned by the LLM, antibiotic protocols stored in MongoDB, and drug names — is always served in a single language and is not region-aware. This feature extends internationalisation to all medical content and introduces region-specific protocol variations for Togo (fr-TG) and Bénin (fr-BJ), reflecting differences in treatment guidelines, drug availability, and local formularies sourced from CHU Lomé, CHU Abomey-Calavi, OMS AFRO, MSF, and PNLP.

Target locales: `fr-TG` (French / Togo), `fr-BJ` (French / Bénin), `en` (English fallback).

---

## Glossary

- **Medical_Content_Service**: The FastAPI service layer responsible for retrieving and localising medical content (diagnoses, protocols, drug names) before returning it to clients.
- **Protocol_Repository**: The MongoDB collection `antibiotic_protocols` managed by `PrescriptionService`, extended to store per-region protocol variants.
- **LLM_Adapter**: The component that wraps MedicalQwen3 / GPT-5 calls and post-processes LLM responses, including language and region instructions.
- **Content_Localiser**: A new shared module (backend) responsible for selecting the correct localised variant of a medical content object given a locale and region.
- **Drug_Catalogue**: The MongoDB collection storing drug entries with INN names, local trade names, and per-region availability flags.
- **i18n_Package**: The existing `@diagno-pilot/i18n` shared package containing UI translation files (`fr.json`, `en.json`).
- **Locale**: A BCP-47 language tag. Supported values: `fr-TG`, `fr-BJ`, `en`. The base language `fr` is treated as an alias for `fr-TG` for backward compatibility.
- **Region**: The country portion of a locale tag (`TG` for Togo, `BJ` for Bénin). Used to select region-specific protocol variants and drug availability.
- **INN**: International Non-proprietary Name — the WHO-standardised generic drug name.
- **Trade_Name**: A locally marketed brand name for a drug, which may differ between Togo and Bénin.
- **Protocol_Variant**: A region-specific override of an antibiotic protocol (dosing, duration, first-line status, or formulary availability).
- **Fallback_Chain**: The resolution order used when a localised variant is not available: `fr-TG` → `fr` → `en` (or `fr-BJ` → `fr` → `en`).
- **Accept-Language**: The HTTP request header used by clients to communicate the preferred locale to the backend.
- **Diagnosis_Response**: The structured object returned by the LLM_Adapter containing differential diagnoses, ICD-10 codes, and concordant symptoms.
- **PrescriptionService**: The existing Python service that calculates antibiotic prescriptions; extended in this feature to be region-aware.

---

## Requirements

### Requirement 1: Locale and Region Propagation

**User Story:** As a clinician using Diagno-Pilot, I want the application to remember my locale and region so that all medical content is presented in the correct language and follows the protocols relevant to my country.

#### Acceptance Criteria

1. THE Medical_Content_Service SHALL accept a locale parameter on every API endpoint that returns medical content, transmitted via the `Accept-Language` HTTP header.
2. WHEN the `Accept-Language` header contains a supported locale (`fr-TG`, `fr-BJ`, or `en`), THE Medical_Content_Service SHALL use that locale for all content localisation in the response.
3. WHEN the `Accept-Language` header is absent or contains an unsupported locale, THE Medical_Content_Service SHALL fall back to `fr-TG` as the default locale.
4. THE i18n_Package SHALL export the extended locale type including `fr-TG` and `fr-BJ` in addition to the existing `fr` and `en` values.
5. WHEN a client sends locale `fr`, THE Medical_Content_Service SHALL treat it as `fr-TG` for backward compatibility.
6. THE Medical_Content_Service SHALL derive the Region from the locale tag (e.g., `TG` from `fr-TG`) and apply it to Protocol_Variant selection.

---

### Requirement 2: Localised Antibiotic Protocols

**User Story:** As a clinician in Togo or Bénin, I want antibiotic protocols to reflect the treatment guidelines and drug availability specific to my country so that prescriptions are clinically appropriate for my context.

#### Acceptance Criteria

1. THE Protocol_Repository SHALL store each antibiotic protocol with a `region` field accepting values `TG`, `BJ`, or `ALL` (applies to all regions).
2. WHEN a prescription is requested for a patient, THE PrescriptionService SHALL select the Protocol_Variant matching the request's Region before falling back to the `ALL` variant.
3. WHEN no region-specific Protocol_Variant exists for a given antibiotic and Region, THE PrescriptionService SHALL use the `ALL` variant as the fallback.
4. THE Protocol_Repository SHALL store localised display names for each protocol in a `names` map keyed by locale (e.g., `{"fr": "Amoxicilline", "en": "Amoxicillin"}`).
5. WHEN a prescription response is serialised, THE Medical_Content_Service SHALL include the localised drug display name for the requested locale.
6. THE Protocol_Repository SHALL store a `available_regions` list per protocol entry; WHEN a protocol is not listed as available in the request's Region, THE PrescriptionService SHALL exclude it from the selectable antibiotic list and suggest the nearest available alternative.
7. WHEN protocols are loaded from MongoDB at startup, THE PrescriptionService SHALL index them by `(name, region)` composite key to enable O(1) region-aware lookup.

---

### Requirement 3: Localised Drug Catalogue with Trade Names

**User Story:** As a clinician, I want to see both the INN and the local trade name of a drug so that I can identify the correct product available in my country's pharmacies.

#### Acceptance Criteria

1. THE Drug_Catalogue SHALL store each drug entry with an `inn` field (INN name), a `trade_names` map keyed by Region (e.g., `{"TG": "Amoxil-TG", "BJ": "Clamoxyl"}`), and a `display_names` map keyed by locale for the INN label.
2. WHEN a prescription response is returned, THE Medical_Content_Service SHALL include both the INN and the Trade_Name for the request's Region.
3. WHEN no Trade_Name exists for the request's Region, THE Medical_Content_Service SHALL return only the INN without error.
4. THE Drug_Catalogue SHALL be queryable by INN name and by Region to retrieve availability and trade name information.
5. WHEN a drug is not available in the request's Region according to the Drug_Catalogue, THE Medical_Content_Service SHALL include an `unavailable_in_region` flag in the prescription response and propose an available alternative.

---

### Requirement 4: Localised LLM Diagnosis Responses

**User Story:** As a clinician, I want differential diagnoses and clinical explanations returned by the AI to be in my preferred language so that I can read and act on them without translation effort.

#### Acceptance Criteria

1. WHEN a diagnosis request is received, THE LLM_Adapter SHALL include the target locale and Region in the system prompt sent to the LLM, instructing it to respond in the corresponding language and to reference region-appropriate clinical guidelines.
2. WHEN the locale is `fr-TG` or `fr-BJ`, THE LLM_Adapter SHALL instruct the LLM to respond in French and to prioritise guidelines from CHU Lomé (TG) or CHU Abomey-Calavi (BJ) respectively.
3. WHEN the locale is `en`, THE LLM_Adapter SHALL instruct the LLM to respond in English and to reference OMS AFRO / MSF guidelines.
4. THE LLM_Adapter SHALL include the locale in the structured Diagnosis_Response metadata so that downstream consumers can verify the language of the content.
5. IF the LLM returns a response in a language that does not match the requested locale, THEN THE LLM_Adapter SHALL log a language mismatch warning and include a `language_mismatch: true` flag in the Diagnosis_Response.
6. THE LLM_Adapter SHALL pass the Region to the RAG retrieval step so that region-specific source documents (CHU Lomé vs CHU Abomey-Calavi) are prioritised in the context window.

---

### Requirement 5: Content_Localiser Module

**User Story:** As a backend developer, I want a single, reusable module that handles all medical content localisation logic so that locale/region resolution is consistent across all services.

#### Acceptance Criteria

1. THE Content_Localiser SHALL expose a `localise(content_object, locale)` function that selects the correct localised string from a `translations` map within the content object.
2. WHEN the exact locale key is not present in the `translations` map, THE Content_Localiser SHALL apply the Fallback_Chain (`fr-TG` → `fr` → `en`) before returning a `null` value.
3. THE Content_Localiser SHALL expose a `parse_locale(accept_language_header)` function that parses a BCP-47 `Accept-Language` header and returns the best matching supported locale.
4. FOR ALL valid locale strings in `{"fr-TG", "fr-BJ", "en", "fr"}`, parsing then formatting then parsing the locale SHALL produce an equivalent locale value (round-trip property).
5. THE Content_Localiser SHALL expose a `extract_region(locale)` function that returns the ISO 3166-1 alpha-2 country code from a locale tag, or `None` for locales without a region subtag.
6. IF an unsupported locale is passed to `localise`, THEN THE Content_Localiser SHALL apply the Fallback_Chain rather than raising an exception.

---

### Requirement 6: Frontend Locale Extension (Web)

**User Story:** As a web frontend developer, I want the next-intl configuration to support the new region-specific locales so that the web application can route and render content correctly for fr-TG and fr-BJ users.

#### Acceptance Criteria

1. THE i18n_Package SHALL provide locale message files for `fr-TG`, `fr-BJ`, and `en`, where `fr-TG` and `fr-BJ` files extend the base `fr.json` with region-specific overrides.
2. WHEN the Next.js middleware resolves a request locale, THE Web_App SHALL support `fr-TG`, `fr-BJ`, and `en` as valid routing locales.
3. THE Web_App SHALL pass the resolved locale as the `Accept-Language` header on all API requests to the backend.
4. WHEN a user's browser locale matches `fr-TG` or `fr-BJ`, THE Web_App SHALL automatically select the corresponding locale without requiring manual selection.
5. WHERE a user explicitly selects a locale in the profile settings, THE Web_App SHALL persist the selection and use it on subsequent requests, overriding browser detection.

---

### Requirement 7: Mobile Locale Extension

**User Story:** As a mobile developer, I want the React Native i18n context to support fr-TG and fr-BJ so that mobile users receive region-appropriate medical content.

#### Acceptance Criteria

1. THE Mobile_App SHALL extend the existing I18nContext to support `fr-TG`, `fr-BJ`, and `en` locale values.
2. WHEN the device locale matches `fr-TG` or `fr-BJ`, THE Mobile_App SHALL automatically select the corresponding locale.
3. THE Mobile_App SHALL include the active locale as the `Accept-Language` header on all API requests.
4. WHEN the active locale changes, THE Mobile_App SHALL re-fetch any cached medical content to ensure localised data is displayed.
5. IF the device locale is not in the supported list, THEN THE Mobile_App SHALL default to `fr-TG`.

---

### Requirement 8: Region-Aware Protocol Administration

**User Story:** As an administrator, I want to manage region-specific protocol variants through the admin interface so that I can keep Togo and Bénin guidelines up to date independently.

#### Acceptance Criteria

1. THE Admin_Interface SHALL allow an administrator to create, update, and delete Protocol_Variants scoped to a specific Region (`TG`, `BJ`, or `ALL`).
2. WHEN a Protocol_Variant is saved, THE PrescriptionService SHALL reload the protocol cache within 5 seconds without requiring a service restart.
3. THE Admin_Interface SHALL display the Region and locale-specific display names for each protocol entry.
4. WHEN an administrator uploads a medical document, THE Admin_Interface SHALL require the administrator to specify the source Region (`TG`, `BJ`, or `ALL`) so that the RAG retrieval step can filter by region.
5. THE Admin_Interface SHALL prevent deletion of a Protocol_Variant if it is the only available variant for a given antibiotic across all regions, and SHALL display an explanatory error message.

---

### Requirement 9: Backward Compatibility

**User Story:** As a developer maintaining existing integrations, I want the i18n changes to be backward compatible so that existing clients using `fr` or `en` locales continue to work without modification.

#### Acceptance Criteria

1. WHEN an existing client sends `Accept-Language: fr`, THE Medical_Content_Service SHALL return content localised for `fr-TG` without error.
2. WHEN an existing client sends `Accept-Language: en`, THE Medical_Content_Service SHALL return content localised for `en` without error.
3. THE Protocol_Repository migration SHALL preserve all existing protocol documents by assigning them `region: "ALL"` if no region field is present.
4. THE Locale type in the i18n_Package SHALL remain assignable from the existing `'fr' | 'en'` union type so that existing TypeScript consumers do not require immediate updates.
5. WHEN the `names` map is absent from a protocol document (legacy document), THE Medical_Content_Service SHALL return the raw `name` field as the display name without error.
