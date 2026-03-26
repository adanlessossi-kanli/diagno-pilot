# Implementation Plan: UI Professional Refactor

## Overview

Incrementally introduce a shared design token module, apply tokens to the web app (Tailwind config + components + pages), then apply tokens to the mobile app (StyleSheets + icons + login). Each task builds on the previous and ends with all code wired together. Property-based tests using `fast-check` are placed immediately after the code they validate.

## Tasks

- [x] 1. Create the shared design token module
  - Create `packages/ui/src/tokens.ts` exporting `colors`, `typography`, `spacing`, `radius`, and `shadow` as `as const` objects matching the values in the design document
  - Ensure the file has no React imports or side effects — plain TS constants only
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7_

  - [x] 1.1 Write property tests for token structure (P1, P2, P3)
    - Create `packages/ui/src/__tests__/tokens.test.ts`
    - **Property 1: Semantic token completeness** — for each category in `{success, warning, error, info}`, assert `bg`, `border`, `text` sub-keys are non-empty strings
    - **Property 2: Typography values within specified ranges** — assert each named size falls within its design-specified range
    - **Property 3: Spacing values are multiples of 4** — assert every spacing value `% 4 === 0`
    - Run minimum 100 iterations per property; include comment tag `// Feature: ui-professional-refactor, Property N: ...`
    - **Validates: Requirements 1.3, 1.4, 1.5**

  - [x] 1.2 Write property test for WCAG contrast ratio (P4)
    - Add to `packages/ui/src/__tests__/tokens.test.ts`
    - **Property 4: WCAG contrast ratio compliance** — enumerate semantic (foreground, background) pairs and assert contrast ≥ 4.5:1 for normal text
    - Implement a `contrastRatio(hex1, hex2)` helper in the test file
    - **Validates: Requirements 2.6**

- [x] 2. Extend Tailwind config with token values
  - Modify `apps/web/tailwind.config.ts` to import from `packages/ui/src/tokens.ts` and extend `theme.colors`, `theme.borderRadius`, `theme.boxShadow`, and `theme.fontFamily` with token values
  - Add `buttonVariants` utility (primary / secondary / ghost class strings) to `packages/ui/src/buttonVariants.ts`
  - _Requirements: 1.8, 2.1, 4.1_

- [x] 3. Refactor shared UI package components
  - [x] 3.1 Refactor `packages/ui/src/AlertBanner.tsx`
    - Replace all inline `style` objects with Tailwind class names using semantic token classes (`error.*`, `warning.*`, `info.*`)
    - Replace emoji icon with an inline SVG icon; keep `AlertBannerProps` interface identical
    - _Requirements: 6.1, 6.2, 6.3, 15.1_

  - [x] 3.2 Write property test for AlertBanner token usage (P7)
    - Create `packages/ui/src/__tests__/AlertBanner.test.tsx`
    - **Property 7: Alert banner semantic token usage (web)** — for each level in `{critical, warning, info}`, assert the rendered element contains the correct semantic token class strings
    - Generator: `fc.constantFrom('critical', 'warning', 'info')`
    - **Validates: Requirements 6.1, 6.2, 6.3**

  - [x] 3.3 Refactor `packages/ui/src/PatientCard.tsx`
    - Replace inline `style` objects with Tailwind class names; replace emoji avatar with initials derived from `patient.fullName` using `colors.primary[600]` background
    - Keep `PatientCardProps` interface identical
    - _Requirements: 5.1, 5.3, 5.4, 15.1_

  - [x] 3.4 Write property test for card surface styling (P9)
    - Create `packages/ui/src/__tests__/PatientCard.test.tsx`
    - **Property 9: Card surface styling invariant** — for any generated patient record, assert the rendered card has white background class, `rounded-lg`/`rounded-md`, and a shadow class
    - Generator: `fc.record({ fullName: fc.string({ minLength: 1 }), allergies: fc.array(fc.string()) })`
    - **Validates: Requirements 5.1**

  - [x] 3.5 Refactor `packages/ui/src/PrescriptionCard.tsx`
    - Replace inline `style` objects with Tailwind class names; keep `PrescriptionCardProps` interface identical
    - _Requirements: 5.1, 5.3, 15.1_

  - [x] 3.6 Write property test for button variant correctness (P6)
    - Create `packages/ui/src/__tests__/buttonVariants.test.ts`
    - **Property 6: Button variant visual correctness** — for each variant × state combination, assert the class string contains the expected tokens (filled bg for primary, border for secondary, no bg for ghost, opacity ≤ 50% + cursor-not-allowed for disabled)
    - Generator: `fc.constantFrom('primary','secondary','ghost')` × `fc.constantFrom('default','disabled','loading')`
    - **Validates: Requirements 4.1, 4.2, 4.3**

- [x] 4. Checkpoint — ensure packages/ui tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Refactor web app components
  - [x] 5.1 Refactor `apps/web/src/components/NavBar.tsx`
    - Add "Diagno-Pilot" wordmark on the left; add `transition-colors duration-150` to hover states; add slide-in CSS transition to mobile drawer via `globals.css`
    - Preserve all existing `aria-*` attributes unchanged; keep `NavBarProps` interface identical
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.6, 3.7, 15.1, 15.6_

  - [x] 5.2 Write property test for NavBar aria attributes (P5)
    - Create `apps/web/src/components/__tests__/NavBar.test.tsx`
    - **Property 5: NavBar accessibility attributes preserved** — for any combination of `isOpen` (boolean) and active path, assert all original `aria-*` attributes are present with their original values
    - Generator: `fc.boolean()` for isOpen, `fc.constantFrom(...links)` for active path
    - **Validates: Requirements 3.7, 15.6**

  - [x] 5.3 Refactor `apps/web/src/components/Toast.tsx`
    - Replace hardcoded color classes with semantic token classes; add `animate-slide-in-top` (define keyframe in `globals.css`, duration ≤ 300 ms); keep `ToastProps` interface identical
    - _Requirements: 6.4, 6.5, 15.1_

  - [x] 5.4 Write property test for Toast token usage (P8)
    - Create `apps/web/src/components/__tests__/Toast.test.tsx`
    - **Property 8: Toast semantic token usage** — for each type in `{success, error, info}`, assert the rendered Toast contains the correct semantic token class
    - Generator: `fc.constantFrom('success', 'error', 'info')`
    - **Validates: Requirements 6.4**

  - [x] 5.5 Refactor `apps/web/src/components/Pagination.tsx`
    - Apply `rounded-md` to all page buttons; active page uses `bg-primary-600 text-white`; disabled nav buttons use `opacity-40 cursor-not-allowed`; keep `PaginationProps` interface identical
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 15.1_

  - [x] 5.6 Write property test for Pagination button tokens (P10)
    - Create `apps/web/src/components/__tests__/Pagination.test.tsx`
    - **Property 10: Pagination button token usage** — for any current page and total, assert active button has primary bg + white text, all buttons have `rounded-md`, disabled buttons have opacity ≤ 40% + `cursor-not-allowed`
    - Generator: `fc.integer({min:1,max:10})` for page, `fc.integer({min:1,max:200})` for total
    - **Validates: Requirements 8.1, 8.2, 8.3, 8.4**

  - [x] 5.7 Refactor `apps/web/src/components/EmptyState.tsx`
    - Apply `text-primary-600` to icon; apply `primary` button variant to action button; keep `EmptyStateProps` interface identical
    - _Requirements: 7.1, 7.2, 15.1_

  - [x] 5.8 Refactor `apps/web/src/components/SkeletonLoader.tsx`
    - Confirm `bg-gray-100` base and `bg-gray-200` shimmer classes are present; confirm animation duration is 1.5–2 s; keep `SkeletonLoaderProps` interface identical
    - _Requirements: 7.3, 7.4, 15.1_

- [x] 6. Refactor web app pages
  - [x] 6.1 Modify `apps/web/src/app/[locale]/layout.tsx`
    - Add `font-sans` and `bg-gray-50` to `<body>`; wrap `{children}` in `max-w-[1280px] mx-auto px-4 pt-6` container
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [x] 6.2 Modify `apps/web/src/app/[locale]/login/page.tsx`
    - Add "Diagno-Pilot" brand heading above the form; apply `rounded-xl shadow-md` to the form card; apply left-border accent to error block using `error` tokens; apply `primary` button variant to submit button
    - No changes to form logic, auth calls, or routing
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 15.5_

  - [x] 6.3 Modify `apps/web/src/app/[locale]/patients/page.tsx`
    - Apply `rounded-lg shadow-sm` and hover shadow transition to PatientCard; apply `primary`/`secondary` variants to buttons
    - No changes to API calls, pagination logic, or modal behavior
    - _Requirements: 5.1, 5.2, 4.1, 15.5_

  - [x] 6.4 Modify `apps/web/src/app/[locale]/diagnose/page.tsx`
    - Apply colored left-border accent (4 px) to diagnosis result cards based on probability (green ≥ 70%, amber 40–69%, red < 40%); apply `bg-primary-600 rounded-full` to probability bar; apply semantic token classes to alert banners
    - No changes to form logic or API calls
    - _Requirements: 5.5, 6.1, 6.2, 6.3, 12.4, 15.5_

- [x] 7. Checkpoint — ensure apps/web tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Refactor mobile app components
  - [x] 8.1 Refactor `apps/mobile/src/components/MobileAlertBanner.tsx`
    - Replace emoji icons with `Ionicons` from `@expo/vector-icons`; replace all hardcoded colors with token constants; apply 4 px left-border using semantic border token; keep `MobileAlertBannerProps` interface identical
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 15.2_

  - [x] 8.2 Write property test for MobileAlertBanner (P11)
    - Create `apps/mobile/src/components/__tests__/MobileAlertBanner.test.tsx`
    - **Property 11: Mobile alert banner semantic token and border usage** — for each level in `{critical, warning, info}`, assert `borderLeftWidth === 4`, `borderLeftColor` equals the semantic border token, `backgroundColor` equals the semantic bg token, and an `Ionicons` component is rendered (not a Text emoji)
    - Generator: `fc.constantFrom('critical', 'warning', 'info')`
    - **Validates: Requirements 13.1, 13.2, 13.3, 13.4, 13.5**

  - [x] 8.3 Refactor `apps/mobile/src/components/MobilePatientCard.tsx`
    - Replace emoji avatar with initials view using `colors.primary[600]` background and white text; replace all hardcoded colors/spacing/radius with token constants; keep `MobilePatientCardProps` interface identical
    - _Requirements: 12.1, 12.2, 10.1, 10.2, 10.3, 15.2_

  - [x] 8.4 Write unit tests for MobilePatientCard
    - Add to `apps/mobile/src/components/__tests__/MobilePatientCard.test.tsx`
    - Assert initials avatar renders (not emoji); assert token-based background color is applied
    - _Requirements: 12.1, 12.2_

  - [x] 8.5 Refactor `apps/mobile/src/components/MobilePrescriptionCard.tsx`
    - Replace all hardcoded colors/spacing/radius with token constants; keep `MobilePrescriptionCardProps` interface identical
    - _Requirements: 12.3, 10.1, 10.2, 10.3, 15.2_

- [x] 9. Refactor mobile app screens and layout
  - [x] 9.1 Modify `apps/mobile/app/(tabs)/_layout.tsx`
    - Replace emoji `tabBarIcon` functions with `Ionicons` components from `@expo/vector-icons`; set `tabBarActiveTintColor` to `colors.primary[600]`; set `tabBarInactiveTintColor` to `colors.neutral[400]`
    - _Requirements: 11.1, 11.2, 11.4, 15.2_

  - [x] 9.2 Modify `apps/mobile/app/login.tsx`
    - Add "Diagno-Pilot" brand heading using `colors.primary[600]` and font size ≥ 24; apply token values for spacing, radius, shadow to the login card; apply primary button style to login button; replace `Alert.alert` error with inline `Text` error state using `error` semantic tokens; clear error state at the start of each login attempt
    - No changes to auth logic or routing
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 15.5_

  - [x] 9.3 Write property test for probability color mapping (P12)
    - Create `apps/mobile/src/__tests__/probabilityColor.test.ts`
    - Extract the probability → border color mapping into a pure function `getProbabilityColor(p: number): string`
    - **Property 12: Mobile diagnosis card probability color mapping** — for any `p` in [0, 1], assert green token when `p ≥ 0.7`, amber/warning token when `0.4 ≤ p < 0.7`, red/error token when `p < 0.4`
    - Generator: `fc.float({min: 0, max: 1})`
    - **Validates: Requirements 12.4**

  - [x] 9.4 Write unit tests for mobile login screen
    - Add to `apps/mobile/app/__tests__/login.test.tsx` (create if absent)
    - Assert brand name renders with primary color; assert inline error renders on failure; assert `Alert.alert` is NOT called
    - _Requirements: 14.1, 14.5_

- [x] 10. Final checkpoint — ensure all test suites pass
  - Run `cd packages/ui && npm test` — must pass with zero failures
  - Run `cd apps/web && npm test` — must pass with zero failures
  - Run `cd apps/mobile && npx jest --runInBand` — must pass with zero failures
  - Run `tsc --noEmit` in `packages/ui`, `apps/web`, and `apps/mobile` — must produce zero errors (validates Property 13: prop interface preservation)
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP
- Property tests require `fast-check`; it is already a dev dependency in `apps/web` — add it to `apps/mobile` and `packages/ui` if not present
- Each property test must include the comment tag `// Feature: ui-professional-refactor, Property N: <property_text>`
- Property 13 (prop interface preservation) is validated by `tsc --noEmit` in the final checkpoint rather than a runtime test
- The `tokens.ts` module must remain free of React imports so it can be consumed by both Tailwind config (Node build-time) and React Native StyleSheets (runtime)
- The mobile login `handleLogin` function must clear error state at the start of each attempt to avoid stale error display
