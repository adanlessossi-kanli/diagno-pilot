import fc from 'fast-check';
import { describe, it, expect } from 'vitest';
import { resolveLocale, routing, SUPPORTED_LOCALES } from '../routing';

// ─── Unit tests ───────────────────────────────────────────────────────────────

describe('resolveLocale — unit tests', () => {
  it('returns "fr-TG" for the "fr-TG" locale', () => {
    expect(resolveLocale('fr-TG')).toBe('fr-TG');
  });

  it('returns "fr-BJ" for the "fr-BJ" locale', () => {
    expect(resolveLocale('fr-BJ')).toBe('fr-BJ');
  });

  it('returns "en" for the "en" locale', () => {
    expect(resolveLocale('en')).toBe('en');
  });

  it('maps "fr" alias to "fr-TG" (backward compat, Requirement 9.1)', () => {
    expect(resolveLocale('fr')).toBe('fr-TG');
  });

  it('returns "fr-TG" for an unsupported locale', () => {
    expect(resolveLocale('de')).toBe('fr-TG');
    expect(resolveLocale('es')).toBe('fr-TG');
    expect(resolveLocale('zh')).toBe('fr-TG');
  });

  it('returns "fr-TG" for undefined', () => {
    expect(resolveLocale(undefined)).toBe('fr-TG');
  });

  it('returns "fr-TG" for null', () => {
    expect(resolveLocale(null)).toBe('fr-TG');
  });

  it('returns "fr-TG" for empty string', () => {
    expect(resolveLocale('')).toBe('fr-TG');
  });

  it('routing.defaultLocale is "fr-TG"', () => {
    expect(routing.defaultLocale).toBe('fr-TG');
  });

  it('routing.locales contains "fr-TG", "fr-BJ", and "en"', () => {
    expect(routing.locales).toContain('fr-TG');
    expect(routing.locales).toContain('fr-BJ');
    expect(routing.locales).toContain('en');
  });

  it('SUPPORTED_LOCALES contains exactly fr-TG, fr-BJ, en', () => {
    expect(SUPPORTED_LOCALES).toContain('fr-TG');
    expect(SUPPORTED_LOCALES).toContain('fr-BJ');
    expect(SUPPORTED_LOCALES).toContain('en');
    expect(SUPPORTED_LOCALES).toHaveLength(3);
  });
});

// ─── Property tests ───────────────────────────────────────────────────────────

// Feature: i18n-medical-content, Property: For any unsupported locale, resolveLocale returns 'fr-TG'
describe('resolveLocale — Property: Langue de repli vers fr-TG', () => {
  /**
   * Validates: Requirements 1.3, 6.6
   * For any unsupported locale (not 'fr-TG', 'fr-BJ', 'en', or 'fr' alias),
   * the effective locale returned must be 'fr-TG'.
   */
  it('fallback to fr-TG for any unsupported locale', () => {
    fc.assert(
      fc.property(
        fc.string().filter((s) => !['fr-TG', 'fr-BJ', 'en', 'fr'].includes(s)),
        (unsupportedLocale) => {
          const result = resolveLocale(unsupportedLocale);
          return result === 'fr-TG';
        },
      ),
      { numRuns: 100 },
    );
  });

  it('returns the locale as-is for any supported locale', () => {
    fc.assert(
      fc.property(
        fc.constantFrom('fr-TG', 'fr-BJ', 'en'),
        (supportedLocale) => {
          const result = resolveLocale(supportedLocale);
          return result === supportedLocale;
        },
      ),
      { numRuns: 100 },
    );
  });

  it('fr alias always resolves to fr-TG (Requirement 9.1)', () => {
    fc.assert(
      fc.property(
        fc.constant('fr'),
        (frAlias) => resolveLocale(frAlias) === 'fr-TG',
      ),
      { numRuns: 10 },
    );
  });
});
