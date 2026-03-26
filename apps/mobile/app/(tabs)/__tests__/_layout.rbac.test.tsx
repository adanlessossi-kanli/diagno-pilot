/// <reference types="@jest/globals" />
/**
 * RBAC tests for TabsLayout mobile
 *
 * Feature: role-based-access-control
 *
 * Property 12: Onglets mobiles corrects pour les rôles médicaux (REQ 8.1, 8.2)
 * Property 13: Onglet QA uniquement pour les guests mobiles (REQ 8.3)
 * Property 14: Redirection mobile vers Profil pour écrans non autorisés (REQ 8.5)
 *
 * Unit tests:
 *  - Admin voit tous les onglets (REQ 8.4)
 *  - Guest ne voit pas les onglets médicaux (REQ 8.3)
 */
import React from 'react';
import { render, screen } from '@testing-library/react-native';
import * as fc from 'fast-check';
import type { UserRole } from '@diagno-pilot/types';
import { MEDICAL_ROLES, SCREEN_PERMISSIONS } from '../_layout';

// ─── Mocks ────────────────────────────────────────────────────────────────────

const mockReplace = jest.fn();
const mockUseSegments = jest.fn(() => [] as string[]);

jest.mock('expo-router', () => {
  const { View: RNView, Text: RNText } = require('react-native');
  const TabsScreen = ({ name, options }: { name: string; options?: { href?: string | null } }) => {
    if (options?.href === null) return null;
    return (
      <RNView testID={`tab-${name}`}>
        <RNText>{name}</RNText>
      </RNView>
    );
  };
  const Tabs = Object.assign(
    ({ children }: { children: React.ReactNode }) => <RNView>{children}</RNView>,
    { Screen: TabsScreen }
  );
  return {
    Tabs,
    useRouter: () => ({ replace: mockReplace }),
    useSegments: () => mockUseSegments(),
  };
});

jest.mock('@expo/vector-icons', () => ({
  Ionicons: () => null,
}));

jest.mock('@diagno-pilot/ui/src/tokens', () => ({
  colors: {
    primary: { 600: '#000' },
    neutral: { 400: '#ccc' },
  },
}));

// ─── Mock useAuth with configurable role ──────────────────────────────────────

let mockRole: UserRole = 'medecin';

jest.mock('../../../src/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { id: '1', email: 'test@test.com', fullName: 'Test', role: mockRole },
    token: 'tok',
    isLoading: false,
    login: jest.fn(),
    logout: jest.fn(),
    apiClient: {},
  }),
}));

// ─── Helpers ──────────────────────────────────────────────────────────────────

import TabsLayout from '../_layout';

function renderLayout(role: UserRole, segments: string[] = []) {
  mockRole = role;
  mockUseSegments.mockReturnValue(segments);
  mockReplace.mockClear();
  return render(<TabsLayout />);
}

/** Returns the set of visible tab names from the rendered output */
function visibleTabs(): string[] {
  const tabs = ['diagnose', 'chat', 'patients', 'qa', 'profile'];
  return tabs.filter(name => {
    try {
      return screen.queryByText(name) !== null || screen.getByText(name) !== null;
    } catch {
      return false;
    }
  });
}

// ─── Setup ────────────────────────────────────────────────────────────────────

beforeEach(() => {
  jest.clearAllMocks();
  mockUseSegments.mockReturnValue([]);
});

// ─── Property 12: Onglets mobiles corrects pour les rôles médicaux ────────────
// Feature: role-based-access-control, Property 12: Onglets mobiles corrects pour les rôles médicaux

describe('Property 12 — Onglets médicaux présents pour medecin et infirmière', () => {
  it('fc.property: medecin et infirmière voient les 4 onglets médicaux', () => {
    fc.assert(
      fc.property(fc.constantFrom<UserRole>('medecin', 'infirmière'), (role) => {
        const { unmount } = renderLayout(role);

        // All medical tabs must be visible
        expect(screen.queryByText('diagnose')).not.toBeNull();
        expect(screen.queryByText('chat')).not.toBeNull();
        expect(screen.queryByText('patients')).not.toBeNull();
        expect(screen.queryByText('profile')).not.toBeNull();

        unmount();
      }),
      { numRuns: 100 }
    );
  });
});

// ─── Property 13: Onglet QA uniquement pour les guests mobiles ────────────────
// Feature: role-based-access-control, Property 13: Onglet QA uniquement pour les guests mobiles

describe('Property 13 — Guest ne voit que l\'onglet QA', () => {
  it('fc.property: guest voit QA et ne voit pas les onglets médicaux', () => {
    fc.assert(
      fc.property(fc.constant<UserRole>('guest'), (role) => {
        const { unmount } = renderLayout(role);

        // QA must be visible
        expect(screen.queryByText('qa')).not.toBeNull();

        // Medical tabs must be hidden
        expect(screen.queryByText('diagnose')).toBeNull();
        expect(screen.queryByText('chat')).toBeNull();
        expect(screen.queryByText('patients')).toBeNull();

        // Profile must be hidden for guest
        expect(screen.queryByText('profile')).toBeNull();

        unmount();
      }),
      { numRuns: 100 }
    );
  });
});

// ─── Property 14: Redirection mobile vers Profil pour écrans non autorisés ────
// Feature: role-based-access-control, Property 14: Redirection mobile vers Profil pour écrans non autorisés

describe('Property 14 — Redirection vers Profil pour écrans non autorisés', () => {
  const ALL_ROLES: UserRole[] = ['admin', 'medecin', 'infirmière', 'guest'];
  const ALL_SCREENS = Object.keys(SCREEN_PERMISSIONS);

  it('fc.property: navigation non autorisée → replace vers /(tabs)/profile', () => {
    fc.assert(
      fc.property(
        fc.tuple(
          fc.constantFrom<UserRole>(...ALL_ROLES),
          fc.constantFrom(...ALL_SCREENS)
        ),
        ([role, screen]) => {
          const allowed = SCREEN_PERMISSIONS[screen];
          const isUnauthorized = !allowed.includes(role);

          if (!isUnauthorized) return; // skip authorized combos

          mockReplace.mockClear();
          const { unmount } = renderLayout(role, ['(tabs)', screen]);

          expect(mockReplace).toHaveBeenCalledWith('/(tabs)/profile');

          unmount();
        }
      ),
      { numRuns: 100 }
    );
  });

  it('fc.property: navigation autorisée → pas de redirection', () => {
    fc.assert(
      fc.property(
        fc.tuple(
          fc.constantFrom<UserRole>(...ALL_ROLES),
          fc.constantFrom(...ALL_SCREENS)
        ),
        ([role, screen]) => {
          const allowed = SCREEN_PERMISSIONS[screen];
          const isAuthorized = allowed.includes(role);

          if (!isAuthorized) return; // skip unauthorized combos

          mockReplace.mockClear();
          const { unmount } = renderLayout(role, ['(tabs)', screen]);

          expect(mockReplace).not.toHaveBeenCalled();

          unmount();
        }
      ),
      { numRuns: 100 }
    );
  });
});

// ─── Unit tests ───────────────────────────────────────────────────────────────

describe('TabsLayout — tests unitaires', () => {
  it('admin voit tous les onglets (REQ 8.4)', () => {
    renderLayout('admin');

    expect(screen.queryByText('diagnose')).not.toBeNull();
    expect(screen.queryByText('chat')).not.toBeNull();
    expect(screen.queryByText('patients')).not.toBeNull();
    expect(screen.queryByText('qa')).not.toBeNull();
    expect(screen.queryByText('profile')).not.toBeNull();
  });

  it('guest ne voit pas les onglets médicaux (REQ 8.3)', () => {
    renderLayout('guest');

    expect(screen.queryByText('diagnose')).toBeNull();
    expect(screen.queryByText('chat')).toBeNull();
    expect(screen.queryByText('patients')).toBeNull();
    expect(screen.queryByText('profile')).toBeNull();
    // QA is visible
    expect(screen.queryByText('qa')).not.toBeNull();
  });

  it('medecin voit les onglets médicaux et profil, pas de redirection (REQ 8.1)', () => {
    renderLayout('medecin');

    expect(screen.queryByText('diagnose')).not.toBeNull();
    expect(screen.queryByText('chat')).not.toBeNull();
    expect(screen.queryByText('patients')).not.toBeNull();
    expect(screen.queryByText('profile')).not.toBeNull();
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it('infirmière voit les onglets médicaux et profil (REQ 8.2)', () => {
    renderLayout('infirmière');

    expect(screen.queryByText('diagnose')).not.toBeNull();
    expect(screen.queryByText('chat')).not.toBeNull();
    expect(screen.queryByText('patients')).not.toBeNull();
    expect(screen.queryByText('profile')).not.toBeNull();
  });

  it('guest naviguant vers diagnose → redirigé vers profil (REQ 8.5)', () => {
    renderLayout('guest', ['(tabs)', 'diagnose']);

    expect(mockReplace).toHaveBeenCalledWith('/(tabs)/profile');
  });

  it('medecin naviguant vers diagnose → pas de redirection (REQ 8.5)', () => {
    renderLayout('medecin', ['(tabs)', 'diagnose']);

    expect(mockReplace).not.toHaveBeenCalled();
  });
});
