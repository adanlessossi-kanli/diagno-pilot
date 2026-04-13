/**
 * Unit tests for Breadcrumb component.
 *
 * Validates:
 * - Req 6.1: Breadcrumb trail on nested pages
 */

import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import React from 'react';

// ─── Mocks ────────────────────────────────────────────────────────────────────

vi.mock('next/link', () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...props}>{children}</a>
  ),
}));

// ─── Import component under test ─────────────────────────────────────────────

import Breadcrumb from '../components/Breadcrumb';

// ─── Teardown ─────────────────────────────────────────────────────────────────

afterEach(() => {
  cleanup();
});

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('Breadcrumb', () => {
  it('renders all breadcrumb items', () => {
    const items = [
      { label: 'Home', href: '/' },
      { label: 'Patients', href: '/patients' },
      { label: 'Alice Dupont' },
    ];
    render(<Breadcrumb items={items} />);

    expect(screen.getByText('Home')).toBeDefined();
    expect(screen.getByText('Patients')).toBeDefined();
    expect(screen.getByText('Alice Dupont')).toBeDefined();
  });

  it('items with href render as links', () => {
    const items = [
      { label: 'Home', href: '/' },
      { label: 'Patients', href: '/patients' },
      { label: 'Detail' },
    ];
    render(<Breadcrumb items={items} />);

    const homeLink = screen.getByText('Home').closest('a');
    expect(homeLink).not.toBeNull();
    expect(homeLink!.getAttribute('href')).toBe('/');

    const patientsLink = screen.getByText('Patients').closest('a');
    expect(patientsLink).not.toBeNull();
    expect(patientsLink!.getAttribute('href')).toBe('/patients');
  });

  it('last item renders as plain text (not a link)', () => {
    const items = [
      { label: 'Home', href: '/' },
      { label: 'Current Page' },
    ];
    render(<Breadcrumb items={items} />);

    const lastItem = screen.getByText('Current Page');
    expect(lastItem.tagName).toBe('SPAN');
    expect(lastItem.closest('a')).toBeNull();
  });

  it('last item has aria-current="page"', () => {
    const items = [
      { label: 'Home', href: '/' },
      { label: 'Patients', href: '/patients' },
      { label: 'Detail Page' },
    ];
    render(<Breadcrumb items={items} />);

    const lastItem = screen.getByText('Detail Page');
    expect(lastItem.getAttribute('aria-current')).toBe('page');
  });

  it('renders separator between items', () => {
    const items = [
      { label: 'Home', href: '/' },
      { label: 'Patients', href: '/patients' },
      { label: 'Detail' },
    ];
    const { container } = render(<Breadcrumb items={items} />);

    const separators = container.querySelectorAll('[aria-hidden="true"]');
    // 3 items → 2 separators (between 1st-2nd and 2nd-3rd)
    expect(separators.length).toBe(2);
    separators.forEach((sep) => {
      expect(sep.textContent).toBe('/');
    });
  });

  it('single item renders without separator', () => {
    const items = [{ label: 'Home' }];
    const { container } = render(<Breadcrumb items={items} />);

    const separators = container.querySelectorAll('[aria-hidden="true"]');
    expect(separators.length).toBe(0);
  });
});
