# homepage-src-undefined-fix Bugfix Design

## Overview

The `HomePage` component in `apps/web/src/app/[locale]/page.tsx` crashes on render because it references `IMAGES.heroHome`, a key that does not exist in the image registry at `apps/web/src/lib/images.ts`. The registry defines the hero image under the key `hero`. Accessing `.src` on the resulting `undefined` throws a `TypeError` and prevents the page from loading. The fix is a single-line change: replace `IMAGES.heroHome` with `IMAGES.hero` in both the `src` and `alt` attribute references.

## Glossary

- **Bug_Condition (C)**: The condition that triggers the bug — `IMAGES.heroHome` is accessed, which is `undefined` in the registry
- **Property (P)**: The desired behavior — `IMAGES.hero` is accessed and returns a valid `ImageEntry` with `src` and `alt`
- **Preservation**: All other `IMAGES` key accesses and page behaviors that must remain unchanged by the fix
- **IMAGES**: The centralized image registry exported from `apps/web/src/lib/images.ts`
- **heroHome**: The non-existent key mistakenly referenced in `page.tsx`
- **hero**: The correct key in `IMAGES` that holds the hero image entry

## Bug Details

### Bug Condition

The bug manifests when `HomePage` renders and accesses `IMAGES.heroHome`. Since `heroHome` is not a key in the `IMAGES` registry, the lookup returns `undefined`. Accessing `.src` or `.alt` on `undefined` throws a `TypeError`, crashing the page.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type string (IMAGES key being accessed)
  OUTPUT: boolean

  RETURN input === 'heroHome'
         AND IMAGES['heroHome'] === undefined
END FUNCTION
```

### Examples

- `IMAGES.heroHome.src` → `TypeError: Cannot read properties of undefined (reading 'src')` (bug)
- `IMAGES.heroHome.alt` → `TypeError: Cannot read properties of undefined (reading 'alt')` (bug)
- `IMAGES.hero.src` → `"https://images.unsplash.com/photo-1559839734-2b71ea197ec2?w=800&q=80"` (correct)
- `IMAGES.hero.alt` → `"Médecin africain en consultation avec un patient"` (correct)

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- All other pages accessing valid `IMAGES` keys (e.g., `IMAGES.consultation`, `IMAGES.diagnoseHeader`) must continue to resolve correctly
- The `IMAGES` registry itself must remain unmodified — no keys added or removed
- The `HomePage` layout, navigation links, and all non-image elements must render identically after the fix

**Scope:**
All code that does NOT reference `IMAGES.heroHome` should be completely unaffected by this fix. This includes:
- Any component accessing `IMAGES.consultation`, `IMAGES.medecin`, `IMAGES.infirmiere`, `IMAGES.patient`, `IMAGES.equipe`, `IMAGES.diagnoseHeader`
- The Next.js `Image` component usage pattern (fill, priority, sizes props)
- The `useTranslations` hook and nav link rendering

## Hypothesized Root Cause

Based on the bug description, the most likely cause is:

1. **Key Name Mismatch**: The developer used `heroHome` as the key when writing `page.tsx`, but the registry was defined with the key `hero`. This is a simple typo/naming inconsistency — no logic error, just a wrong string key.

2. **No TypeScript Guard**: The `IMAGES` object is typed as `Record<string, ImageEntry>`, which allows any string key without a compile-time error. A stricter type (e.g., a union of known keys) would have caught this at build time.

## Correctness Properties

Property 1: Bug Condition - Valid Hero Image Resolution

_For any_ render of `HomePage` where `IMAGES.heroHome` was previously accessed (isBugCondition returns true), the fixed component SHALL access `IMAGES.hero` instead, returning a valid `ImageEntry` object so that `.src` and `.alt` resolve without error and the `Image` component renders successfully.

**Validates: Requirements 2.1, 2.2**

Property 2: Preservation - Other Image Registry Accesses Unchanged

_For any_ code that accesses IMAGES keys other than `heroHome` (isBugCondition returns false), the fixed code SHALL produce exactly the same result as the original code, preserving all existing image resolution behavior across the application.

**Validates: Requirements 3.1, 3.2, 3.3**

## Fix Implementation

### Changes Required

**File**: `apps/web/src/app/[locale]/page.tsx`

**Function**: `HomePage` (default export)

**Specific Changes**:
1. **Replace key reference on line with `src`**: Change `IMAGES.heroHome.src` → `IMAGES.hero.src`
2. **Replace key reference on line with `alt`**: Change `IMAGES.heroHome.alt` → `IMAGES.hero.alt`

No changes are needed to `apps/web/src/lib/images.ts` — the registry is correct as-is.

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm the root cause (key name mismatch).

**Test Plan**: Write a unit test that renders `HomePage` and asserts the `Image` component receives a valid `src`. Run on the UNFIXED code to observe the `TypeError`.

**Test Cases**:
1. **Hero Image Render Test**: Render `HomePage` and assert `Image` receives a non-undefined `src` (will fail on unfixed code with `TypeError`)
2. **Key Existence Test**: Assert `IMAGES['heroHome']` is `undefined` and `IMAGES['hero']` is defined (confirms the mismatch)
3. **Alt Text Test**: Render `HomePage` and assert `Image` receives a non-undefined `alt` (will fail on unfixed code)

**Expected Counterexamples**:
- `TypeError: Cannot read properties of undefined (reading 'src')` thrown during render
- Possible cause: key name mismatch between `page.tsx` and `images.ts`

### Fix Checking

**Goal**: Verify that after the fix, `HomePage` renders without error and the `Image` component receives the correct `src` and `alt`.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  result := render(HomePage_fixed)
  ASSERT result does not throw TypeError
  ASSERT Image.src === IMAGES.hero.src
  ASSERT Image.alt === IMAGES.hero.alt
END FOR
```

### Preservation Checking

**Goal**: Verify that all other `IMAGES` key accesses and page behaviors are unaffected.

**Pseudocode:**
```
FOR ALL key WHERE NOT isBugCondition(key) DO
  ASSERT IMAGES[key]_original === IMAGES[key]_fixed
END FOR
```

**Testing Approach**: Property-based testing is well-suited here because:
- It can generate all valid IMAGES keys and verify each resolves correctly
- It catches any accidental mutation of the registry
- It provides strong guarantees that no other key was affected

**Test Plan**: Observe that all other IMAGES keys resolve correctly on unfixed code, then write property-based tests to verify this is preserved after the fix.

**Test Cases**:
1. **Registry Preservation**: For every key in IMAGES except `heroHome`, assert the entry is unchanged after the fix
2. **Other Page Render Preservation**: Verify components using `IMAGES.consultation` and `IMAGES.diagnoseHeader` still render correctly
3. **No New Keys**: Assert the set of keys in IMAGES is identical before and after the fix

### Unit Tests

- Test that `IMAGES.hero` exists and has valid `src` and `alt` properties
- Test that `IMAGES.heroHome` is `undefined` (confirms the bug condition)
- Test that `HomePage` renders without throwing after the fix
- Test that the rendered `Image` component receives `IMAGES.hero.src` as its `src` prop

### Property-Based Tests

- Generate all keys in the `IMAGES` registry and verify each has a non-empty `src` and `alt`
- Verify that no key in the registry is `undefined` after the fix is applied
- Verify that the set of registry keys is unchanged (no additions or removals)

### Integration Tests

- Render the full `HomePage` in a test environment and assert no runtime errors
- Verify the hero image section renders with a valid image URL
- Verify navigation links and heading still render correctly alongside the fixed image
