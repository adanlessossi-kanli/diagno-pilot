# Design Document: UI Professional Refactor

## Overview

Diagno-Pilot currently has a functional but visually inconsistent UI. The web app (`apps/web`) uses ad-hoc Tailwind utility classes with a partial `primary`/`danger`/`warning`/`success` color extension in `tailwind.config.ts`. The mobile app (`apps/mobile`) uses inline `StyleSheet` objects with hardcoded hex values. The shared `@diagno-pilot/ui` package uses inline React `style` objects with hardcoded hex values.

This refactor introduces a single design token module (`packages/ui/src/tokens.ts`) that both platforms consume, then applies those tokens consistently across all components and pages. The constraint is strictly visual: no prop interfaces, API calls, routing paths, auth logic, i18n keys, or accessibility attributes may change.

### Key Findings from Codebase Exploration

- `packages/ui` already exists as a shared package consumed by `apps/web`. It is the natural home for shared tokens.
- `apps/web` already has a partial Tailwind color extension (`primary`, `danger`, `warning`, `success`). The refactor will complete and align this with the token spec.
- `apps/mobile` has no token abstraction at all — all colors and spacing are hardcoded hex/number literals.
- The mobile tab layout (`apps/mobile/app/(tabs)/_layout.tsx`) already uses `#2563eb` for the active tint, which aligns with the brand color.
- The mobile login screen already uses `Alert.alert` for errors — Requirement 14.5 requires replacing this with inline error state.
- Emoji icons are used in the mobile tab bar and `MobileAlertBanner` — these must be replaced with `@expo/vector-icons`.
- The `@diagno-pilot/ui` shared components use inline `style` objects — these will be migrated to reference token constants.

---

## Architecture

The refactor is organized into three layers:

```
┌─────────────────────────────────────────────────────────┐
│              packages/ui/src/tokens.ts                  │
│   (single source of truth — plain JS/TS constants)      │
└────────────────┬────────────────────────────────────────┘
                 │ imported by
        ┌────────┴────────┐
        ▼                 ▼
┌──────────────┐   ┌──────────────────────────────────────┐
│  apps/web    │   │  apps/mobile                         │
│              │   │                                      │
│ tailwind.    │   │  StyleSheet objects reference        │
│ config.ts    │   │  tokens directly (no Tailwind)       │
│ extends with │   │                                      │
│ token values │   └──────────────────────────────────────┘
└──────────────┘
```

**Design decision**: Tokens are plain TypeScript constants (not CSS custom properties, not a theme object requiring a provider). This keeps them usable in both Tailwind config (which runs at build time in Node) and React Native StyleSheets (which run at runtime). No new runtime dependency is introduced.

**Design decision**: The web app continues to use Tailwind utility classes. The token values are injected into `tailwind.config.ts` so that class names like `bg-primary-600` resolve to the canonical token value. This avoids rewriting every className string.

**Design decision**: The `@diagno-pilot/ui` shared components (used by the web app) will migrate from inline `style` objects to Tailwind class names, since the web app already has Tailwind configured. The mobile-specific components in `apps/mobile/src/components/` will reference token constants directly in their StyleSheets.

---

## Components and Interfaces

### New File: `packages/ui/src/tokens.ts`

Exports plain constant objects. No React, no side effects.

```
tokens.colors        — color palette + semantic aliases
tokens.typography    — font size scale
tokens.spacing       — spacing scale
tokens.radius        — border radius scale
tokens.shadow        — elevation/shadow definitions (web CSS strings + mobile elevation numbers)
```

### Modified: `apps/web/tailwind.config.ts`

Extended to map all token values into Tailwind's theme. Existing class names (`bg-blue-600`, `text-red-600`, etc.) that already match token values require no change in component files. New semantic aliases (`bg-primary-600`, `bg-error-bg`, etc.) are added.

### Modified: `packages/ui/src/AlertBanner.tsx`

- Replaces inline `style` objects with Tailwind class names
- Replaces emoji icon with an SVG icon inline (no new dependency for the web package)
- Prop interface `AlertBannerProps` unchanged

### Modified: `packages/ui/src/PatientCard.tsx`

- Replaces inline `style` objects with Tailwind class names
- Replaces emoji avatar with initials derived from `patient.fullName`, styled with primary color background
- Prop interface `PatientCardProps` unchanged

### Modified: `packages/ui/src/PrescriptionCard.tsx`

- Replaces inline `style` objects with Tailwind class names
- Prop interface `PrescriptionCardProps` unchanged

### Modified: `apps/web/src/components/NavBar.tsx`

- Adds "Diagno-Pilot" wordmark on the left (currently absent — only links are shown)
- Adds `transition-colors duration-150` to hover states
- Adds slide-in animation to mobile drawer via CSS transition
- Prop interface `NavBarProps` unchanged; all existing `aria-*` attributes preserved

### Modified: `apps/web/src/components/Toast.tsx`

- Replaces hardcoded `bg-green-600`/`bg-red-600`/`bg-blue-600` with semantic token classes
- Adds `animate-slide-in-top` (defined in `globals.css`) for entrance animation ≤ 300 ms
- Prop interface `ToastProps` unchanged

### Modified: `apps/web/src/components/Pagination.tsx`

- Applies `rounded-md` (token `radius.md`) to all page buttons
- Active page uses `bg-primary-600 text-white`
- Disabled nav buttons use `opacity-40 cursor-not-allowed`
- Prop interface `PaginationProps` unchanged

### Modified: `apps/web/src/components/EmptyState.tsx`

- Action button uses `primary` button variant classes
- Icon uses `text-primary-600` accent
- Prop interface `EmptyStateProps` unchanged

### Modified: `apps/web/src/components/SkeletonLoader.tsx`

- Uses `bg-gray-100` base and `bg-gray-200` shimmer (already correct, animation duration confirmed 1.5–2 s)
- Prop interface `SkeletonLoaderProps` unchanged

### Modified: `apps/web/src/app/[locale]/layout.tsx`

- Adds `font-sans` (Inter/system-ui) to `<body>`
- Adds `bg-gray-50` to `<body>`
- Adds `max-w-[1280px] mx-auto px-4 pt-6` wrapper around `{children}`

### Modified: `apps/web/src/app/[locale]/login/page.tsx`

- Adds "Diagno-Pilot" brand heading above the form
- Applies `rounded-xl shadow-md` to the form card (token `radius.lg` + `shadow.md`)
- Error block gets left-border accent treatment
- Submit button uses `primary` variant
- No changes to form logic, auth calls, or routing

### Modified: `apps/web/src/app/[locale]/patients/page.tsx`

- `PatientCard` (inline component) gets `rounded-lg shadow-sm` and hover shadow transition
- Buttons use `primary`/`secondary` variants
- No changes to API calls, pagination logic, or modal behavior

### Modified: `apps/web/src/app/[locale]/diagnose/page.tsx`

- Diagnosis result cards get colored left-border accent based on probability
- Probability bar uses `bg-primary-600` with `rounded-full`
- Alert banners use semantic color tokens
- No changes to form logic or API calls

### Modified: `apps/mobile/app/(tabs)/_layout.tsx`

- Replaces emoji `tabBarIcon` with `@expo/vector-icons` (Ionicons)
- `tabBarActiveTintColor` → token `colors.primary[600]`
- `tabBarInactiveTintColor` → token `colors.neutral[400]`

### Modified: `apps/mobile/app/login.tsx`

- Replaces `Alert.alert` error with inline `Text` error state using `error` semantic tokens
- Applies token values for spacing, radius, shadow
- No changes to auth logic or routing

### Modified: `apps/mobile/src/components/MobileAlertBanner.tsx`

- Replaces emoji icons with `@expo/vector-icons` (Ionicons)
- References token constants for all colors
- Prop interface `MobileAlertBannerProps` unchanged

### Modified: `apps/mobile/src/components/MobilePatientCard.tsx`

- Replaces emoji avatar with initials view using `colors.primary[600]` background
- References token constants for all colors, spacing, radius
- Prop interface `MobilePatientCardProps` unchanged

### Modified: `apps/mobile/src/components/MobilePrescriptionCard.tsx`

- References token constants for all colors, spacing, radius
- Prop interface `MobilePrescriptionCardProps` unchanged

---

## Data Models

### Token Structure (`packages/ui/src/tokens.ts`)

```typescript
export const colors = {
  primary: {
    50:  '#EFF6FF',
    100: '#DBEAFE',
    300: '#93C5FD',
    600: '#2563EB',
    700: '#1D4ED8',
  },
  neutral: {
    50:  '#F9FAFB',
    100: '#F3F4F6',
    200: '#E5E7EB',
    400: '#9CA3AF',
    500: '#6B7280',
    700: '#374151',
    900: '#111827',
  },
  // Semantic tokens — each has bg, border, text
  success: {
    bg:     '#F0FDF4',
    border: '#16A34A',
    text:   '#14532D',
  },
  warning: {
    bg:     '#FFFBEB',
    border: '#D97706',
    text:   '#78350F',
  },
  error: {
    bg:     '#FEF2F2',
    border: '#DC2626',
    text:   '#7F1D1D',
  },
  info: {
    bg:     '#EFF6FF',
    border: '#2563EB',
    text:   '#1E3A5F',
  },
} as const;

export const typography = {
  xs:   12,   // px / sp
  sm:   14,
  base: 16,
  lg:   20,
} as const;

export const spacing = {
  1:  4,
  2:  8,
  3:  12,
  4:  16,
  6:  24,
  8:  32,
  12: 48,
} as const;

export const radius = {
  sm:   4,
  md:   8,
  lg:   12,
  xl:   16,
  full: 9999,
} as const;

export const shadow = {
  // Web: CSS box-shadow strings
  web: {
    sm: '0 1px 2px 0 rgb(0 0 0 / 0.05)',
    md: '0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)',
    lg: '0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1)',
  },
  // Mobile: React Native elevation integers
  mobile: {
    sm: 2,
    md: 4,
    lg: 8,
  },
} as const;
```

### Tailwind Config Extension

`tailwind.config.ts` will be updated to reference token values:

```typescript
theme: {
  extend: {
    colors: {
      primary: { 50, 100, 300, 600, 700 },   // from tokens.colors.primary
      neutral: { 50, 100, 200, 400, 500, 700, 900 },
      success: { bg, border, text },
      warning: { bg, border, text },
      error:   { bg, border, text },
      info:    { bg, border, text },
    },
    borderRadius: {
      sm: '4px', md: '8px', lg: '12px', xl: '16px',
    },
    boxShadow: {
      sm: '...', md: '...', lg: '...',
    },
    fontFamily: {
      sans: ['Inter', 'system-ui', 'sans-serif'],
    },
  },
}
```

### Button Variant Classes (web)

Defined as Tailwind class strings in a utility helper `packages/ui/src/buttonVariants.ts` (or inlined in components):

| Variant   | Classes |
|-----------|---------|
| primary   | `bg-primary-600 text-white hover:bg-primary-700 rounded-md px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed` |
| secondary | `border border-neutral-200 text-neutral-700 hover:bg-neutral-50 rounded-md px-4 py-2 text-sm font-medium transition-colors` |
| ghost     | `text-primary-600 hover:text-primary-700 px-4 py-2 text-sm font-medium transition-colors` |

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*


### Property 1: Semantic token completeness

*For any* semantic color category in `{success, warning, error, info}`, the token object must expose `bg`, `border`, and `text` sub-keys, each containing a non-empty string value.

**Validates: Requirements 1.3**

### Property 2: Typography values within specified ranges

*For any* named typography size in `{xs, sm, base, lg}`, the pixel value must fall within its specified range: `xs` ∈ [11, 12], `sm` ∈ [13, 14], `base` ∈ [15, 16], `lg` ∈ [18, 20].

**Validates: Requirements 1.4**

### Property 3: Spacing values are multiples of 4

*For any* value in the spacing token object, the value must be divisible by 4 with no remainder.

**Validates: Requirements 1.5**

### Property 4: WCAG contrast ratio compliance

*For any* (foreground, background) color pair drawn from the semantic token system (e.g., `error.text` on `error.bg`, `primary[600]` on white), the computed WCAG 2.1 contrast ratio must be ≥ 4.5:1 for normal-sized text pairings and ≥ 3:1 for large-text pairings.

**Validates: Requirements 2.6**

### Property 5: NavBar accessibility attributes preserved

*For any* render of the `NavBar` component (authenticated or unauthenticated, open or closed drawer), all aria attributes that existed before the refactor (`aria-label` on the nav, `aria-label` and `aria-expanded` on the hamburger button, `aria-current` on active links, `aria-label` on the close button, `aria-hidden` on the overlay) must be present with their original values.

**Validates: Requirements 3.7, 15.6**

### Property 6: Button variant visual correctness

*For any* button variant in `{primary, secondary, ghost}` and any state in `{default, disabled, loading}`, the rendered button element must contain the class strings appropriate for that variant/state combination: `primary` has a filled background using the primary color token; `secondary` has a border and neutral background; `ghost` has no background; `disabled` has opacity ≤ 50% and `cursor-not-allowed`; `loading` contains a spinner element.

**Validates: Requirements 4.1, 4.2, 4.3**

### Property 7: Alert banner semantic token usage (web)

*For any* alert level in `{critical, warning, info}`, the rendered `AlertBanner` component must apply the corresponding semantic color token classes: `critical` uses `error.*` tokens, `warning` uses `warning.*` tokens, `info` uses `info.*` tokens.

**Validates: Requirements 6.1, 6.2, 6.3**

### Property 8: Toast semantic token usage

*For any* toast type in `{success, error, info}`, the rendered `Toast` component must apply the corresponding semantic color token classes.

**Validates: Requirements 6.4**

### Property 9: Card surface styling invariant

*For any* render of a card-style component (`PatientCard`, `PrescriptionCard`, diagnosis result card), the rendered element must have a white background class, the `rounded-lg` (or `rounded-md`) border-radius class, and a shadow class corresponding to the `sm` or `md` shadow token.

**Validates: Requirements 5.1**

### Property 10: Pagination button token usage

*For any* pagination render with a given current page and total, the active page button must have the primary color background class and white text; all inactive page buttons must have a neutral border class; all page buttons must have the `rounded-md` class; disabled previous/next buttons must have opacity ≤ 40% and `cursor-not-allowed`.

**Validates: Requirements 8.1, 8.2, 8.3, 8.4**

### Property 11: Mobile alert banner semantic token and border usage

*For any* alert level in `{critical, warning, info}`, the rendered `MobileAlertBanner` must have `borderLeftWidth` equal to 4, `borderLeftColor` equal to the semantic border token for that level, `backgroundColor` equal to the semantic bg token for that level, and must render an `Ionicons` component rather than a `Text` component with an emoji character.

**Validates: Requirements 13.1, 13.2, 13.3, 13.4, 13.5**

### Property 12: Mobile diagnosis card probability color mapping

*For any* probability value `p` in [0, 1], the left-border color of the diagnosis card must be the green token when `p ≥ 0.7`, the amber/warning token when `0.4 ≤ p < 0.7`, and the red/error token when `p < 0.4`.

**Validates: Requirements 12.4**

### Property 13: Component prop interface preservation

*For any* component that is modified by this refactor (both web and mobile), the TypeScript prop interface exported from that component must be structurally identical to the pre-refactor interface — no props added, removed, or type-changed.

**Validates: Requirements 15.1, 15.2**

---

## Error Handling

### Token Import Errors

- The `tokens.ts` module uses `as const` assertions and exports plain objects. There are no runtime errors possible from importing it. TypeScript will catch any typo in token key access at compile time.

### Missing Token Keys

- Components that reference token keys that don't exist will fail TypeScript compilation. This is intentional — it surfaces missing tokens at build time rather than runtime.

### Mobile `@expo/vector-icons` Unavailability

- If `@expo/vector-icons` is not installed, the app will fail to compile. The package is already a transitive dependency of `expo` and does not need to be added explicitly. If an icon name is invalid, Ionicons renders nothing silently — the component should include a fallback `accessibilityLabel` on the icon element.

### Tailwind Class Purging

- Tailwind's content scanner must include all files that use token-derived class names. The existing `tailwind.config.ts` content array already covers `src/**/*.{tsx,ts}`. No change needed.

### Login Error State (Mobile)

- The mobile login screen currently uses `Alert.alert` for errors. After the refactor, errors are stored in a `useState` variable and rendered as an inline `Text` element. If the error state is not cleared on retry, the old error remains visible — the `handleLogin` function must clear the error state at the start of each attempt.

---

## Testing Strategy

### Dual Testing Approach

Both unit tests and property-based tests are required. They are complementary:

- **Unit tests** verify specific examples, integration points, and edge cases (e.g., "the login page renders the brand name", "the NavBar renders the drawer when the hamburger is clicked").
- **Property-based tests** verify universal invariants across generated inputs (e.g., "for any alert level, the correct semantic tokens are applied", "for any probability value, the correct color is chosen").

### Property-Based Testing Library

- **Web (`apps/web`, `packages/ui`)**: `fast-check` (already installed as a dev dependency in `apps/web`)
- **Mobile (`apps/mobile`)**: `fast-check` (add as dev dependency)

Each property-based test must run a minimum of **100 iterations**.

Each test must include a comment tag in the format:
```
// Feature: ui-professional-refactor, Property N: <property_text>
```

### Property Test Implementations

| Property | Test Location | Generator |
|----------|--------------|-----------|
| P1: Semantic token completeness | `packages/ui/src/__tests__/tokens.test.ts` | Enumerate `{success, warning, error, info}` |
| P2: Typography ranges | `packages/ui/src/__tests__/tokens.test.ts` | Enumerate `{xs, sm, base, lg}` |
| P3: Spacing multiples of 4 | `packages/ui/src/__tests__/tokens.test.ts` | Enumerate spacing values |
| P4: WCAG contrast ratio | `packages/ui/src/__tests__/tokens.test.ts` | Enumerate semantic color pairs |
| P5: NavBar aria attributes | `apps/web/src/components/__tests__/NavBar.test.tsx` | `fc.boolean()` for isOpen, `fc.constantFrom(links)` for active path |
| P6: Button variant correctness | `packages/ui/src/__tests__/buttonVariants.test.ts` | `fc.constantFrom('primary','secondary','ghost')` × `fc.constantFrom('default','disabled','loading')` |
| P7: Alert banner tokens (web) | `packages/ui/src/__tests__/AlertBanner.test.tsx` | `fc.constantFrom('critical','warning','info')` |
| P8: Toast tokens | `apps/web/src/components/__tests__/Toast.test.tsx` | `fc.constantFrom('success','error','info')` |
| P9: Card surface styling | `packages/ui/src/__tests__/PatientCard.test.tsx` | `fc.record({ fullName: fc.string(), allergies: fc.array(fc.string()) })` |
| P10: Pagination button tokens | `apps/web/src/components/__tests__/Pagination.test.tsx` | `fc.integer({min:1,max:10})` for page, `fc.integer({min:1,max:200})` for total |
| P11: Mobile alert banner | `apps/mobile/src/components/__tests__/MobileAlertBanner.test.tsx` | `fc.constantFrom('critical','warning','info')` |
| P12: Probability color mapping | `apps/mobile/src/__tests__/probabilityColor.test.ts` | `fc.float({min:0,max:1})` |
| P13: Prop interface preservation | TypeScript compilation (CI) | N/A — verified by `tsc --noEmit` |

### Unit Test Coverage

Unit tests (using Vitest for web, Jest/jest-expo for mobile) should cover:

- **NavBar**: renders wordmark, renders user info, opens/closes drawer, active link highlighting
- **Toast**: renders message, auto-dismisses after duration, calls `onClose`
- **Pagination**: renders correct page range text, calls `goToPage` on button click, hides when total=0
- **EmptyState**: renders title, description, action button; action button calls `onClick`
- **SkeletonLoader**: renders correct number of skeleton items
- **Login page (web)**: renders brand name, renders two-column layout class, shows error with correct styling
- **Login screen (mobile)**: renders brand name with primary color, shows inline error on failure, does not call `Alert.alert`
- **MobilePatientCard**: renders initials avatar (not emoji), applies token-based styles
- **Tab layout**: uses Ionicons components, correct tint colors

### Non-Regression Verification

After all changes:
1. Run `cd apps/web && npm test` — must pass with zero failures
2. Run `cd apps/mobile && npx jest --runInBand` — must pass with zero failures
3. Run `cd packages/ui && npm test` — must pass with zero failures
4. Run `tsc --noEmit` in `apps/web`, `apps/mobile`, and `packages/ui` — must produce zero errors
