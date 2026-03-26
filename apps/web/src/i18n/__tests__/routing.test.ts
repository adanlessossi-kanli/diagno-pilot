import fc from 'fast-check';
import { describe, it, expect } from 'vitest';
import { resolveLocale, routing } from '../routing';

// ─── Unit tests ───────────────────────────────────────────────────────────────

describe('resolveLocale — unit tests', () => {
  it('returns "fr" for the "fr" locale', () => {
    expect(resolveLocale('fr')).toBe('fr');
  });

  it('returns "en" for the "en" locale', () => {
    expect(resolveLocale('en')).toBe('en');
  });

  it('returns "fr" for an unsupported locale', () => {
    expect(resolveLocale('de')).toBe('fr');
    expect(resolveLocale('es')).toBe('fr');
    expect(resolveLocale('zh')).toBe('fr');
  });

  it('returns "fr" for undefined', () => {
    expect(resolveLocale(undefined)).toBe('fr');
  });

  it('returns "fr" for null', () => {
    expect(resolveLocale(null)).toBe('fr');
  });

  it('returns "fr" for empty string', () => {
    expect(resolveLocale('')).toBe('fr');
  });

  it('routing.defaultLocale is "fr"', () => {
    expect(routing.defaultLocale).toBe('fr');
  });

  it('routing.locales contains "fr" and "en"', () => {
    expect(routing.locales).toContain('fr');
    expect(routing.locales).toContain('en');
  });
});

// ─── Property 6 ───────────────────────────────────────────────────────────────

// Feature: app-consistency, Property 6: Pour toute locale non supportée, la locale effective est 'fr'
describe('resolveLocale — Property 6: Langue de repli vers le français', () => {
  /**
   * **Validates: Requirement 2.7**
   * Property 6: For any unsupported locale (not 'fr' or 'en'), the effective
   * locale returned must be 'fr'.
   */
  it('fallback to fr for any unsupported locale', () => {
    fc.assert(
      fc.property(
        fc.string().filter((s) => s !== 'fr' && s !== 'en'),
        (unsupportedLocale) => {
          const result = resolveLocale(unsupportedLocale);
          return result === 'fr';
        },
      ),
      { numRuns: 100 },
    );
  });

  it('returns the locale as-is for any supported locale', () => {
    fc.assert(
      fc.property(
        fc.constantFrom('fr', 'en'),
        (supportedLocale) => {
          const result = resolveLocale(supportedLocale);
          return result === supportedLocale;
        },
      ),
      { numRuns: 100 },
    );
  });
});
