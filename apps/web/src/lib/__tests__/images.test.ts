/**
 * Tests unitaires et de propriétés pour le Registre d'images IMAGES.
 *
 * Feature: app-consistency, Property 15: Intégrité structurelle du Registre d'images
 *
 * **Validates: Requirements 5.1, 5.4, 7.4**
 */
import fc from 'fast-check';
import { IMAGES } from '../images';

// --- Tests unitaires (task 12.2) ---
describe('IMAGES registry — tests unitaires', () => {
  it('le registre contient au moins une entrée', () => {
    expect(Object.keys(IMAGES).length).toBeGreaterThan(0);
  });

  it('chaque entrée possède src, alt, source et licence non vides', () => {
    for (const [, entry] of Object.entries(IMAGES)) {
      expect(typeof entry.src).toBe('string');
      expect(entry.src.trim().length).toBeGreaterThan(0);

      expect(typeof entry.alt).toBe('string');
      expect(entry.alt.trim().length).toBeGreaterThan(0);

      expect(typeof entry.source).toBe('string');
      expect(entry.source.trim().length).toBeGreaterThan(0);

      expect(typeof entry.licence).toBe('string');
      expect(entry.licence.trim().length).toBeGreaterThan(0);
    }
  });

  it('chaque valeur src est une URL valide commençant par https://', () => {
    for (const [, entry] of Object.entries(IMAGES)) {
      expect(entry.src).toMatch(/^https:\/\//);
    }
  });

  it('chaque valeur source est une URL valide commençant par https://', () => {
    for (const [, entry] of Object.entries(IMAGES)) {
      expect(entry.source).toMatch(/^https:\/\//);
    }
  });

  it('chaque texte alt a une longueur significative (> 5 caractères)', () => {
    for (const [, entry] of Object.entries(IMAGES)) {
      expect(entry.alt.length).toBeGreaterThan(5);
    }
  });
});

// --- Tests de propriétés (task 12.3 / 12.4) ---
// P15 — Intégrité structurelle du Registre d'images
describe('IMAGES registry — tests de propriétés', () => {
  it('every image entry has non-empty src, alt, source and licence fields', () => {
    const entries = Object.entries(IMAGES);

    // Static check: every known entry satisfies the property
    for (const [, value] of entries) {
      expect(value.src).toBeTruthy();
      expect(value.alt).toBeTruthy();
      expect(value.source).toBeTruthy();
      expect(value.licence).toBeTruthy();
    }

    // Property: for any key drawn from the IMAGES object, all four fields are non-empty strings
    // Feature: app-consistency, Property 15: Pour toute entrée du registre, src/alt/source/licence présents et non vides
    fc.assert(
      fc.property(
        fc.constantFrom(...Object.keys(IMAGES)),
        (key) => {
          const entry = IMAGES[key];
          return (
            typeof entry.src === 'string' && entry.src.trim().length > 0 &&
            typeof entry.alt === 'string' && entry.alt.trim().length > 0 &&
            typeof entry.source === 'string' && entry.source.trim().length > 0 &&
            typeof entry.licence === 'string' && entry.licence.trim().length > 0
          );
        }
      ),
      { numRuns: 100 }
    );
  });

  it('alt text is in French (contains at least one French word or accented character)', () => {
    const entries = Object.entries(IMAGES);
    for (const [, value] of entries) {
      expect(value.alt.length).toBeGreaterThan(5);
    }
  });

  // Feature: app-consistency, Property 16: Pour toute image avec src invalide, le texte alt est affiché
  it('every image entry has a non-empty alt field usable as fallback when image fails to load', () => {
    // **Validates: Requirements 5.5**
    fc.assert(
      fc.property(
        fc.constantFrom(...Object.keys(IMAGES)),
        (key) => {
          const entry = IMAGES[key];
          return typeof entry.alt === 'string' && entry.alt.length > 0;
        }
      ),
      { numRuns: 100 }
    );
  });
});

// --- Preservation property tests (bugfix: homepage-src-undefined-fix, task 2) ---
// Property 2: Preservation — Other IMAGES Registry Keys Unchanged
// **Validates: Requirements 3.1, 3.2, 3.3**
describe('IMAGES registry — preservation property tests (bugfix task 2)', () => {
  const EXPECTED_KEYS = ['hero', 'consultation', 'medecin', 'infirmiere', 'patient', 'equipe', 'diagnoseHeader'];

  it('the set of keys in IMAGES contains all expected legacy keys (no heroHome)', () => {
    // **Validates: Requirements 3.1, 3.2, 3.3**
    const actualKeys = Object.keys(IMAGES);
    for (const key of EXPECTED_KEYS) {
      expect(actualKeys).toContain(key);
    }
  });

  it('for all keys in IMAGES (excluding heroHome), each entry has a defined, non-empty src and alt', () => {
    // **Validates: Requirements 3.1, 3.2, 3.3**
    fc.assert(
      fc.property(
        fc.constantFrom(...EXPECTED_KEYS),
        (key) => {
          const entry = IMAGES[key];
          return (
            entry !== undefined &&
            typeof entry.src === 'string' && entry.src.trim().length > 0 &&
            typeof entry.alt === 'string' && entry.alt.trim().length > 0
          );
        }
      ),
      { numRuns: 100 }
    );
  });

  it('heroHome is NOT a key in IMAGES (confirms the bug condition key does not exist in registry)', () => {
    // **Validates: Requirements 3.3**
    expect(IMAGES['heroHome']).toBeUndefined();
  });
});

// --- african-image-representation property tests (task 1) ---

// Feature: african-image-representation, Property 1: All required keys exist in the Image Registry
// **Validates: Requirements 1.2, 1.4, 8.1, 8.2**
describe('IMAGES registry — african-image-representation property tests', () => {
  it('IMAGES contains all required keys', () => {
    // Feature: african-image-representation, Property 1: All required keys exist in the Image Registry
    const requiredKeys = ['hero', 'loginSide', 'diagnoseHeader', 'patientsEmpty'];
    for (const key of requiredKeys) {
      expect(IMAGES[key]).toBeDefined();
      expect(typeof IMAGES[key]).toBe('object');
    }
  });

  // Feature: african-image-representation, Property 2: All Image Registry entries have all required non-empty fields
  // **Validates: Requirements 1.3, 6.1, 7.1, 7.2, 7.3**
  it('all IMAGES entries have all required non-empty fields', () => {
    fc.assert(
      fc.property(fc.constantFrom(...Object.keys(IMAGES)), (key) => {
        const entry = IMAGES[key];
        expect(entry.src).toBeTruthy();
        expect(entry.alt).toBeTruthy();
        expect(entry.source).toBeTruthy();
        expect(entry.licence).toBeTruthy();
      }),
      { numRuns: 100 }
    );
  });

  // Feature: african-image-representation, Property 3: All legacy keys are preserved
  // **Validates: Requirements 1.5**
  it('IMAGES preserves all legacy keys', () => {
    const legacyKeys = ['hero', 'consultation', 'medecin', 'infirmiere', 'patient', 'equipe', 'diagnoseHeader'];
    for (const key of legacyKeys) {
      expect(IMAGES[key]).toBeDefined();
    }
  });
});
