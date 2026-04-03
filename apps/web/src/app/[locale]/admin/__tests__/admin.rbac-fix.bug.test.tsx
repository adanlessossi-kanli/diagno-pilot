/**
 * Bug condition exploration tests — RBAC Fix bugfix spec (Admin panel)
 *
 * These tests assert the EXPECTED (correct) behavior and will FAIL on unfixed
 * code, proving each bug exists. DO NOT fix the code when these fail.
 *
 * **Validates: Requirements 1.5, 2.5**
 *
 * Bugs confirmed by this file:
 *   - Bug 7: Admin panel has no dedicated create-doctor form
 *
 * Expected counterexamples (on unfixed code):
 *   - Admin panel page.tsx exists but has no dedicated "Créer un médecin" form
 *   - No CreateDoctorForm component or section exists in admin panel
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import React from 'react';
import * as fs from 'fs';
import * as path from 'path';

// ─── Mocks ────────────────────────────────────────────────────────────────────

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

vi.mock('next/link', () => ({
  default: ({
    href,
    children,
    className,
  }: {
    href: string;
    children: React.ReactNode;
    className?: string;
  }) => (
    <a href={href} className={className}>
      {children}
    </a>
  ),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useParams: () => ({ locale: 'fr' }),
}));

const mockAuthValue = {
  user: null as null | { id: string; email: string; role: string; fullName: string },
  isLoading: false,
  login: vi.fn(),
  logout: vi.fn(),
  fetchWithRefresh: vi.fn(),
};

vi.mock('../../../../contexts/AuthContext', () => ({
  useAuth: () => mockAuthValue,
}));

// Mock fetch for admin API calls
global.fetch = vi.fn().mockResolvedValue({
  ok: true,
  json: vi.fn().mockResolvedValue([]),
  status: 200,
} as unknown as Response);

// ─── Helpers ──────────────────────────────────────────────────────────────────

beforeEach(() => {
  cleanup();
  mockAuthValue.isLoading = false;
  mockAuthValue.user = null;
  vi.clearAllMocks();
  global.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: vi.fn().mockResolvedValue([]),
    status: 200,
  } as unknown as Response);
});

// ─── Bug 7: Admin panel has no dedicated create-doctor form ───────────────────

describe('Bug 7 — Admin panel has dedicated create-doctor form', () => {
  /**
   * **Validates: Requirements 1.5, 2.5**
   * Admin panel MUST have a dedicated "Créer un médecin" form.
   * EXPECTED TO FAIL on unfixed code — admin panel has no dedicated create-doctor form.
   * Counterexample: admin panel page.tsx has no "Créer un médecin" section.
   */

  it('admin panel page.tsx source contains create-doctor form content', () => {
    const adminPagePath = path.resolve(__dirname, '../page.tsx');
    expect(fs.existsSync(adminPagePath)).toBe(true);

    const content = fs.readFileSync(adminPagePath, 'utf-8');
    // BUG 7: admin panel has no dedicated create-doctor form on unfixed code
    // The page should contain a dedicated section for creating medecin accounts
    const hasCreateDoctorForm =
      content.includes('CreateDoctor') ||
      content.includes('create-doctor') ||
      content.includes('Créer un médecin') ||
      content.includes('creer-medecin') ||
      content.includes('CreateDoctorForm') ||
      (content.includes('medecin') && content.includes('form'));

    expect(hasCreateDoctorForm).toBe(true);
  });

  it('admin panel renders a dedicated create-doctor section', async () => {
    mockAuthValue.user = {
      id: 'admin-1',
      email: 'admin@test.com',
      role: 'admin',
      fullName: 'Admin User',
    };

    const { default: AdminPanelPage } = await import('../page');
    render(<AdminPanelPage />);

    // BUG 7: no dedicated create-doctor form rendered on unfixed code
    // Look for any element that indicates a create-doctor form
    const createDoctorHeading =
      screen.queryByText(/créer un médecin/i) ??
      screen.queryByText(/create.*doctor/i) ??
      screen.queryByText(/nouveau médecin/i) ??
      screen.queryByText(/ajouter.*médecin/i);

    expect(createDoctorHeading).not.toBeNull();
  });

  it('admin panel source has a form with role pre-selected as medecin', () => {
    const adminPagePath = path.resolve(__dirname, '../page.tsx');
    const content = fs.readFileSync(adminPagePath, 'utf-8');

    // BUG 7: no dedicated medecin creation form on unfixed code
    // The dedicated form should have medecin role pre-selected
    const hasMedecinRolePreselected =
      content.includes("role: 'medecin'") ||
      content.includes('role="medecin"') ||
      content.includes("value='medecin'") ||
      content.includes('value="medecin"') ||
      (content.includes('medecin') && content.includes('pre') && content.includes('select'));

    expect(hasMedecinRolePreselected).toBe(true);
  });
});
