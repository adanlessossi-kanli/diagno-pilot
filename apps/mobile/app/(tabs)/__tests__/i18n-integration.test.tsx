/// <reference types="@jest/globals" />
/**
 * Integration tests for mobile i18n — English locale
 *
 * Validates: Requirements 9.1, 9.2
 *
 * Renders DiagnoseScreen and ChatScreen with English translations
 * and asserts that no hardcoded French strings appear in the output.
 */
import React from 'react';
import { render, screen } from '@testing-library/react-native';
import DiagnoseScreen from '../diagnose';
import ChatScreen from '../chat';
import en from '../../../src/i18n/en';

// ─── Build a real English t() function ────────────────────────────────────────

const tEn = (key: string, params?: Record<string, string>): string => {
  let value = (en as Record<string, string>)[key] ?? key;
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      value = value.replace(`{${k}}`, v);
    }
  }
  return value;
};

// ─── Mocks ────────────────────────────────────────────────────────────────────

jest.mock('expo-router', () => ({
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), back: jest.fn() }),
  useSegments: () => [],
  Link: ({ children }: { children: React.ReactNode }) => children,
}));

jest.mock('@expo/vector-icons', () => ({
  Ionicons: () => null,
}));

jest.mock('../../../src/utils/probabilityColor', () => ({
  getProbabilityColor: jest.fn(() => '#22c55e'),
}));

jest.mock('@diagno-pilot/ui/src/tokens', () => ({
  colors: {
    primary: { 600: '#2563eb' },
    neutral: { 200: '#e5e7eb', 400: '#9ca3af', 500: '#6b7280', 900: '#111827' },
    error: { bg: '#fef2f2', border: '#fca5a5', text: '#dc2626' },
    warning: { bg: '#fffbeb', border: '#fcd34d', text: '#d97706' },
    info: { bg: '#eff6ff', border: '#93c5fd', text: '#1d4ed8' },
  },
  spacing: { 2: 8, 3: 12, 4: 16 },
  radius: { sm: 4, lg: 10, full: 9999 },
  typography: { xs: 11, sm: 13, base: 15, lg: 18 },
  shadow: { mobile: { sm: 2 } },
}));


// ─── Mock AuthContext ─────────────────────────────────────────────────────────

const mockDiagnose = jest.fn();
const mockGetPrescription = jest.fn();
const mockSendMessageStream = jest.fn();

jest.mock('../../../src/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { id: '1', email: 'doc@test.com', fullName: 'Dr Test', role: 'medecin' },
    token: 'tok',
    isLoading: false,
    login: jest.fn(),
    logout: jest.fn(),
    apiClient: {
      diagnose: {
        getSymptomsDiagnosis: mockDiagnose,
        getPrescription: mockGetPrescription,
      },
      chat: {
        sendMessageStream: mockSendMessageStream,
      },
    },
  }),
}));

jest.mock('../../../src/contexts/I18nContext', () => ({
  useI18n: () => ({
    locale: 'en',
    setLocale: jest.fn(),
    cacheVersion: 0,
    t: tEn,
  }),
}));

// ─── Setup ────────────────────────────────────────────────────────────────────

beforeEach(() => {
  jest.clearAllMocks();
  mockDiagnose.mockResolvedValue({ diagnoses: [] });
  mockGetPrescription.mockResolvedValue({ prescription: null, alerts: [] });
});

// ─── French strings that must NOT appear ──────────────────────────────────────

const FRENCH_DIAGNOSE_STRINGS = [
  'Symptômes',
  'Saisir les symptômes',
  'Diagnostics différentiels',
  'Obtenir les diagnostics',
  'Recommencer',
  'Nouvelle consultation',
  'Changer de diagnostic',
  'Alertes critiques',
  'CIM-10',
  'Symptômes concordants',
];

const FRENCH_CHAT_STRINGS = [
  'Posez une question sur les antibiotiques',
  'Votre question',
  'Envoyer',
];

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('Mobile i18n integration — English locale', () => {
  describe('DiagnoseScreen', () => {
    it('renders English strings and no hardcoded French on symptoms step', () => {
      render(<DiagnoseScreen />);

      // English strings should be present
      expect(screen.getByText('Symptoms')).toBeTruthy();
      expect(screen.getByText('Enter symptoms')).toBeTruthy();
      expect(screen.queryByText(/Get diagnoses/)).toBeTruthy();

      // No French strings should appear
      for (const fr of FRENCH_DIAGNOSE_STRINGS) {
        expect(screen.queryByText(fr)).toBeNull();
      }
    });
  });

  describe('ChatScreen', () => {
    it('renders English strings and no hardcoded French on empty state', () => {
      render(<ChatScreen />);

      // English strings should be present
      expect(screen.queryByText(/Ask a question about antibiotics/)).toBeTruthy();

      // No French strings should appear
      for (const fr of FRENCH_CHAT_STRINGS) {
        expect(screen.queryByText(fr)).toBeNull();
      }
    });
  });
});
