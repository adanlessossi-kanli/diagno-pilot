/**
 * Bug condition exploration tests — RBAC Fix bugfix spec (Medecin interface)
 *
 * These tests assert the EXPECTED (correct) behavior and will FAIL on unfixed
 * code, proving each bug exists. DO NOT fix the code when these fail.
 *
 * **Validates: Requirements 1.4, 2.4**
 *
 * Bugs confirmed by this file:
 *   - Bug 6: Medecin interface has no create-nurse form (form is absent)
 *
 * Expected counterexamples (on unfixed code):
 *   - No medecin page exists at apps/web/src/app/[locale]/medecin/page.tsx
 *   - No CreateNurseForm component exists
 *   - No create-nurse route exists
 */

import { describe, it, expect } from 'vitest';
import * as fs from 'fs';
import * as path from 'path';

// ─── Bug 6: Medecin interface has no create-nurse form ────────────────────────

describe('Bug 6 — Create-nurse form present in medecin interface', () => {
  /**
   * **Validates: Requirements 1.4, 2.4**
   * Medecin interface MUST have a create-nurse form accessible.
   * EXPECTED TO FAIL on unfixed code — no medecin page or create-nurse form exists.
   * Counterexample: medecin page file does not exist.
   */

  it('medecin page file exists (create-nurse route)', () => {
    // Check for medecin page or create-nurse page
    const medecinPagePath = path.resolve(
      __dirname,
      '../../page.tsx',
    );
    const createNursePath = path.resolve(
      __dirname,
      '../../create-nurse/page.tsx',
    );
    // BUG 6: neither file exists on unfixed code
    const medecinExists = fs.existsSync(medecinPagePath);
    const createNurseExists = fs.existsSync(createNursePath);
    expect(medecinExists || createNurseExists).toBe(true);
  });

  it('create-nurse form component or page exists', () => {
    // Check multiple possible locations for the create-nurse form
    const possiblePaths = [
      path.resolve(__dirname, '../../page.tsx'),
      path.resolve(__dirname, '../../create-nurse/page.tsx'),
      path.resolve(__dirname, '../../../../../components/CreateNurseForm.tsx'),
    ];

    const anyExists = possiblePaths.some((p) => fs.existsSync(p));
    // BUG 6: no create-nurse form exists on unfixed code
    expect(anyExists).toBe(true);
  });

  it('create-nurse page contains a form element for nurse creation', () => {
    const possiblePaths = [
      path.resolve(__dirname, '../../create-nurse/page.tsx'),
      path.resolve(__dirname, '../../page.tsx'),
    ];

    const existingPath = possiblePaths.find((p) => fs.existsSync(p));
    // BUG 6: no file exists on unfixed code → this assertion fails
    expect(existingPath).toBeDefined();

    if (existingPath) {
      const content = fs.readFileSync(existingPath, 'utf-8');
      // The page should contain a form for creating nurses
      const hasForm = content.includes('<form') || content.includes('CreateNurse') ||
        content.includes('create-nurse') || content.includes('infirmière') ||
        content.includes('nurse');
      // BUG 6: no nurse creation form content on unfixed code
      expect(hasForm).toBe(true);
    }
  });
});
