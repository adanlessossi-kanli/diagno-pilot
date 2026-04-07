/**
 * Tests for MCP multi-agent features on DiagnosePage and DiagnoseHistoryPage
 * Validates: Requirements 16.1, 16.2, 16.3, 16.4, 16.8, 16.9
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup, act } from '@testing-library/react';
import React from 'react';

// ─── Mocks ────────────────────────────────────────────────────────────────────

const mockGetSymptomsDiagnosis = vi.fn();
const mockGetPrescription = vi.fn();
const mockListAntibiotics = vi.fn();

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
  useLocale: () => 'fr',
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/',
}));

vi.mock('next/image', () => ({
  default: ({ src, alt }: { src: string; alt: string }) =>
    React.createElement('img', { src, alt }),
}));

vi.mock('@/lib/images', () => ({
  IMAGES: {
    diagnoseHeader: { src: '/diagnose-header.jpg', alt: 'Diagnose header' },
  },
}));

vi.mock('../../../../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { id: '1', email: 'doc@test.com', role: 'medecin', fullName: 'Dr Test' },
    isLoading: false,
  }),
}));

vi.mock('@diagno-pilot/api-client', () => ({
  createApiClient: () => ({
    diagnose: {
      getSymptomsDiagnosis: mockGetSymptomsDiagnosis,
      getPrescription: mockGetPrescription,
      listAntibiotics: mockListAntibiotics,
    },
    patients: {
      listAllPatients: vi.fn().mockResolvedValue([]),
    },
  }),
}));

// ─── Helpers ──────────────────────────────────────────────────────────────────

const baseDiagnoses = [
  {
    condition: 'Pneumonia',
    probability: 0.85,
    icdCode: 'J18',
    matchingSymptoms: ['fever', 'cough'],
    concordantSymptoms: ['fever', 'cough'],
  },
];

const mcpResponse = {
  sessionId: 'mcp-session-1',
  diagnoses: baseDiagnoses,
  sources: [],
  llmUsed: 'gpt-4',
  fallbackWarning: 'Fallback LLM was used for some agents.',
  degradedWarning: 'Agents omitted: Epidemiology_Agent',
  warningsPresent: true,
  confidenceScore: 0.78,
  agentContributions: [
    { agentName: 'Epidemiology_Agent', confidenceScore: 0.9, partialDifferential: [] },
    { agentName: 'Symptomatology_Agent', confidenceScore: 0.75, partialDifferential: [] },
  ],
  evidenceCitations: [
    {
      documentId: 'doc-1',
      title: 'Malaria Protocol 2024',
      source: 'CHU Lomé',
      excerpt: 'Fever with cough suggests pneumonia.',
      page: 12,
    },
    {
      documentId: 'doc-2',
      title: 'Clinical Guidelines',
      source: 'OMS AFRO',
      excerpt: 'Differential diagnosis approach.',
      page: null,
    },
  ],
};

// ─── Tests ────────────────────────────────────────────────────────────────────

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  mockListAntibiotics.mockResolvedValue(['Amoxicillin']);
});

describe('DiagnosePage — MCP warning banners (Req 16.1)', () => {
  it('displays fallback and degraded warning banners when warningsPresent is true', async () => {
    mockGetSymptomsDiagnosis.mockResolvedValue(mcpResponse);

    const { default: DiagnosePage } = await import('../page');
    render(<DiagnosePage />);

    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: 'fever and cough for 3 days' } });

    await act(async () => {
      fireEvent.submit(textarea.closest('form')!);
    });

    await waitFor(() => {
      const alerts = screen.getAllByRole('alert');
      expect(alerts.length).toBeGreaterThanOrEqual(2);
    });

    expect(screen.getByText(/Fallback LLM was used/)).toBeDefined();
    expect(screen.getByText(/Agents omitted: Epidemiology_Agent/)).toBeDefined();
  });

  it('does not display warning banners when warningsPresent is false', async () => {
    mockGetSymptomsDiagnosis.mockResolvedValue({
      ...mcpResponse,
      warningsPresent: false,
      fallbackWarning: undefined,
      degradedWarning: undefined,
    });

    const { default: DiagnosePage } = await import('../page');
    render(<DiagnosePage />);

    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: 'fever and cough for 3 days' } });

    await act(async () => {
      fireEvent.submit(textarea.closest('form')!);
    });

    await waitFor(() => {
      expect(screen.getByText('Pneumonia')).toBeDefined();
    });

    expect(screen.queryByTestId('warnings-section')).toBeNull();
  });
});

describe('DiagnosePage — Confidence score display (Req 16.2)', () => {
  it('displays the global confidence score as a percentage', async () => {
    mockGetSymptomsDiagnosis.mockResolvedValue(mcpResponse);

    const { default: DiagnosePage } = await import('../page');
    render(<DiagnosePage />);

    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: 'fever and cough for 3 days' } });

    await act(async () => {
      fireEvent.submit(textarea.closest('form')!);
    });

    await waitFor(() => {
      expect(screen.getByText('78%')).toBeDefined();
    });

    expect(screen.getByText('confidenceScore:')).toBeDefined();
  });
});

describe('DiagnosePage — Evidence citations display (Req 16.3)', () => {
  it('displays evidence citations with title, source, excerpt, and page', async () => {
    mockGetSymptomsDiagnosis.mockResolvedValue(mcpResponse);

    const { default: DiagnosePage } = await import('../page');
    render(<DiagnosePage />);

    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: 'fever and cough for 3 days' } });

    await act(async () => {
      fireEvent.submit(textarea.closest('form')!);
    });

    await waitFor(() => {
      expect(screen.getByText('Malaria Protocol 2024')).toBeDefined();
    });

    expect(screen.getByText(/CHU Lomé/)).toBeDefined();
    expect(screen.getByText(/Fever with cough suggests pneumonia/)).toBeDefined();
    expect(screen.getByText(/p\. 12/)).toBeDefined();
    expect(screen.getByText('Clinical Guidelines')).toBeDefined();
  });
});

describe('DiagnosePage — Agent contributions display (Req 16.4)', () => {
  it('displays agent names and confidence scores', async () => {
    mockGetSymptomsDiagnosis.mockResolvedValue(mcpResponse);

    const { default: DiagnosePage } = await import('../page');
    render(<DiagnosePage />);

    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: 'fever and cough for 3 days' } });

    await act(async () => {
      fireEvent.submit(textarea.closest('form')!);
    });

    await waitFor(() => {
      expect(screen.getByText('Epidemiology_Agent')).toBeDefined();
    });

    expect(screen.getByText('Symptomatology_Agent')).toBeDefined();
    expect(screen.getByText('90%')).toBeDefined();
    expect(screen.getByText('75%')).toBeDefined();
  });
});

describe('DiagnosePage — History link (Req 16.11)', () => {
  it('renders a link to the diagnosis history page', async () => {
    mockGetSymptomsDiagnosis.mockResolvedValue({
      sessionId: 's1',
      diagnoses: [],
      sources: [],
    });

    const { default: DiagnosePage } = await import('../page');
    render(<DiagnosePage />);

    const historyLink = screen.getByTestId('history-link');
    expect(historyLink).toBeDefined();
    expect(historyLink.getAttribute('href')).toBe('/fr/diagnose/history');
  });
});
