# Implementation Plan: African Image Representation

## Overview

Two targeted fixes: add missing `loginSide` and `patientsEmpty` keys to the image registry, and add `credentials: 'include'` to all fetch helpers in the API client.

## Tasks

- [x] 1. Add missing image registry entries
  - Add `loginSide` key to `IMAGES` in `apps/web/src/lib/images.ts` with a valid African healthcare photograph and all required fields (`src`, `alt`, `source`, `licence`)
  - Add `patientsEmpty` key to `IMAGES` with a valid African healthcare photograph and all required fields
  - Verify all existing keys (`hero`, `consultation`, `medecin`, `infirmiere`, `patient`, `equipe`, `diagnoseHeader`) remain present and unchanged
  - _Requirements: 1.2, 1.4, 1.5, 2.2, 2.3, 5.2, 5.3, 7.1, 7.2, 8.2, 8.3_

  - [x] 1.1 Write property test for all required keys existing in the Image Registry
    - **Property 1: All required keys exist in the Image Registry**
    - **Validates: Requirements 1.2, 1.4, 8.1, 8.2**

  - [x] 1.2 Write property test for all Image Registry entries having required non-empty fields
    - **Property 2: All Image Registry entries have all required non-empty fields**
    - **Validates: Requirements 1.3, 6.1, 7.1, 7.2, 7.3**

  - [x] 1.3 Write property test for legacy key preservation
    - **Property 3: All legacy keys are preserved**
    - **Validates: Requirements 1.5**

- [x] 2. Add `credentials: 'include'` to all API client fetch helpers
  - Update `get`, `post`, `put`, `del`, and `postForm` in `packages/api-client/index.ts` to include `credentials: 'include'` in each `fetch` call
  - _Requirements: 9.2, 9.3_

  - [x] 2.1 Write property test for all fetch helpers including credentials
    - **Property 4: All API client fetch helpers include credentials**
    - **Validates: Requirements 9.2, 9.3**

  - [x] 2.2 Write unit test for 401 from auth/me setting user to null
    - Test that `AuthContext` sets `user` to `null` and redirects to login when `auth/me` returns 401
    - _Requirements: 9.4_

- [x] 3. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Write unit tests for page components rendering correct images
  - [x] 4.1 Write unit test for LoginPage rendering `loginSide` image
    - _Requirements: 2.1_
  - [x] 4.2 Write unit test for PatientsPage empty state rendering `patientsEmpty` image
    - _Requirements: 5.1_

- [x] 5. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP
- Property tests use `fast-check` as specified in the design document
- Each property test must include the comment tag: `// Feature: african-image-representation, Property <N>: <property_text>`
