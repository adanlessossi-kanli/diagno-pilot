import { describe, it, expect } from 'vitest';
import { getMessages, getMessagesSync, locales, defaultLocale } from './index';

// Load the raw locale files for comparison
import frBase from './locales/fr.json';
import frTG from './locales/fr-TG.json';
import frBJ from './locales/fr-BJ.json';
import en from './locales/en.json';

describe('getMessages() merge strategy', () => {
  describe('fr-TG', () => {
    it('includes all base fr keys', async () => {
      const messages = await getMessages('fr-TG');
      // Every top-level key from fr.json must be present
      for (const key of Object.keys(frBase)) {
        expect(messages).toHaveProperty(key);
      }
    });

    it('applies fr-TG region overrides on top of fr base', async () => {
      const messages = await getMessages('fr-TG');
      // The override in fr-TG.json replaces admin.documentTitlePlaceholder
      expect((messages.admin as Record<string, unknown>).documentTitlePlaceholder).toBe(
        frTG.admin.documentTitlePlaceholder,
      );
    });

    it('preserves non-overridden fr keys unchanged', async () => {
      const messages = await getMessages('fr-TG');
      // nav.home is not overridden in fr-TG.json — must equal the fr base value
      expect((messages.nav as Record<string, unknown>).home).toBe(
        (frBase.nav as Record<string, unknown>).home,
      );
    });

    it('includes the _region metadata key', async () => {
      const messages = await getMessages('fr-TG');
      expect(messages._region).toBe('Togo');
    });

    it('does not include keys that exist only in fr-BJ', async () => {
      const messages = await getMessages('fr-TG');
      // _region should be Togo, not Bénin
      expect(messages._region).not.toBe('Bénin');
    });
  });

  describe('fr-BJ', () => {
    it('includes all base fr keys', async () => {
      const messages = await getMessages('fr-BJ');
      for (const key of Object.keys(frBase)) {
        expect(messages).toHaveProperty(key);
      }
    });

    it('applies fr-BJ region overrides on top of fr base', async () => {
      const messages = await getMessages('fr-BJ');
      expect((messages.admin as Record<string, unknown>).documentTitlePlaceholder).toBe(
        frBJ.admin.documentTitlePlaceholder,
      );
    });

    it('preserves non-overridden fr keys unchanged', async () => {
      const messages = await getMessages('fr-BJ');
      expect((messages.nav as Record<string, unknown>).home).toBe(
        (frBase.nav as Record<string, unknown>).home,
      );
    });

    it('includes the _region metadata key', async () => {
      const messages = await getMessages('fr-BJ');
      expect(messages._region).toBe('Bénin');
    });
  });

  describe('fr-TG vs fr-BJ overrides differ', () => {
    it('admin.documentTitlePlaceholder differs between fr-TG and fr-BJ', async () => {
      const tg = await getMessages('fr-TG');
      const bj = await getMessages('fr-BJ');
      expect(
        (tg.admin as Record<string, unknown>).documentTitlePlaceholder,
      ).not.toBe(
        (bj.admin as Record<string, unknown>).documentTitlePlaceholder,
      );
    });
  });

  describe('fr (base locale)', () => {
    it('returns the fr base messages as-is', async () => {
      const messages = await getMessages('fr');
      expect(messages).toEqual(frBase);
    });
  });

  describe('en', () => {
    it('returns the en messages as-is', async () => {
      const messages = await getMessages('en');
      expect(messages).toEqual(en);
    });
  });
});

describe('getMessagesSync() merge strategy', () => {
  it('fr-TG includes all base fr keys', () => {
    const messages = getMessagesSync('fr-TG');
    for (const key of Object.keys(frBase)) {
      expect(messages).toHaveProperty(key);
    }
  });

  it('fr-TG applies region override', () => {
    const messages = getMessagesSync('fr-TG');
    expect((messages.admin as Record<string, unknown>).documentTitlePlaceholder).toBe(
      frTG.admin.documentTitlePlaceholder,
    );
  });

  it('fr-BJ includes all base fr keys', () => {
    const messages = getMessagesSync('fr-BJ');
    for (const key of Object.keys(frBase)) {
      expect(messages).toHaveProperty(key);
    }
  });

  it('fr-BJ applies region override', () => {
    const messages = getMessagesSync('fr-BJ');
    expect((messages.admin as Record<string, unknown>).documentTitlePlaceholder).toBe(
      frBJ.admin.documentTitlePlaceholder,
    );
  });
});

describe('package exports', () => {
  it('locales array includes fr-TG and fr-BJ', () => {
    expect(locales).toContain('fr-TG');
    expect(locales).toContain('fr-BJ');
  });

  it('defaultLocale is fr-TG', () => {
    expect(defaultLocale).toBe('fr-TG');
  });
});
