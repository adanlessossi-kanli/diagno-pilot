# Implementation Plan

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - heroHome Key Undefined Bug
  - **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior - it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the bug exists
  - **Scoped PBT Approach**: Scope the property to the concrete failing case — `IMAGES.heroHome` accessed in `HomePage` render
  - Test that `IMAGES['heroHome']` is `undefined` (confirms the key mismatch from Bug Condition in design)
  - Test that rendering `HomePage` throws `TypeError: Cannot read properties of undefined (reading 'src')`
  - The test assertions should match the Expected Behavior Properties from design: `IMAGES.hero` resolves to a valid `ImageEntry`
  - Run test on UNFIXED code
  - **EXPECTED OUTCOME**: Test FAILS (this is correct - it proves the bug exists)
  - Document counterexamples found: `IMAGES.heroHome` is `undefined`, accessing `.src` throws `TypeError`
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 1.2_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Other IMAGES Registry Keys Unchanged
  - **IMPORTANT**: Follow observation-first methodology
  - Observe: `IMAGES['hero']`, `IMAGES['consultation']`, `IMAGES['diagnoseHeader']` all resolve to valid `ImageEntry` objects on unfixed code
  - Observe: Each valid key has a non-empty `src` string and non-empty `alt` string
  - Write property-based test: for all keys in `IMAGES` (excluding `heroHome`), each entry has a defined, non-empty `src` and `alt` (from Preservation Requirements in design)
  - Write property-based test: the set of keys in `IMAGES` is exactly `['hero', 'consultation', 'medecin', 'infirmiere', 'patient', 'equipe', 'diagnoseHeader']`
  - Verify tests pass on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (this confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3_

- [x] 3. Fix IMAGES.heroHome → IMAGES.hero in page.tsx

  - [x] 3.1 Implement the fix
    - In `apps/web/src/app/[locale]/page.tsx`, replace `IMAGES.heroHome.src` with `IMAGES.hero.src`
    - In `apps/web/src/app/[locale]/page.tsx`, replace `IMAGES.heroHome.alt` with `IMAGES.hero.alt`
    - No changes needed to `apps/web/src/lib/images.ts` — the registry is correct as-is
    - _Bug_Condition: isBugCondition(input) where input === 'heroHome' AND IMAGES['heroHome'] === undefined_
    - _Expected_Behavior: IMAGES.hero resolves to a valid ImageEntry; Image renders with correct src and alt_
    - _Preservation: All other IMAGES key accesses and page behaviors remain unaffected_
    - _Requirements: 2.1, 2.2, 3.1, 3.2, 3.3_

  - [x] 3.2 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - heroHome Key Undefined Bug
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - The test from task 1 encodes the expected behavior
    - When this test passes, it confirms `IMAGES.hero` resolves correctly and `HomePage` renders without error
    - Run bug condition exploration test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed)
    - _Requirements: 2.1, 2.2_

  - [x] 3.3 Verify preservation tests still pass
    - **Property 2: Preservation** - Other IMAGES Registry Keys Unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
    - Run preservation property tests from step 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
    - Confirm all registry keys still resolve correctly and no keys were added or removed

- [x] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.
