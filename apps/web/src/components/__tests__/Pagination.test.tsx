import fc from 'fast-check';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, cleanup, screen, fireEvent } from '@testing-library/react';
import React from 'react';

// ─── Mock next/navigation ─────────────────────────────────────────────────────

const mockPush = vi.fn();
const mockPathname = '/patients';
const mockSearchParams = new URLSearchParams();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
  usePathname: () => mockPathname,
  useSearchParams: () => mockSearchParams,
}));

import Pagination from '../Pagination';

// ─── Helpers ──────────────────────────────────────────────────────────────────

afterEach(() => {
  cleanup();
  mockPush.mockClear();
});

function totalPages(total: number, pageSize: number): number {
  return Math.max(1, Math.ceil(total / pageSize));
}

// ─── Unit tests ───────────────────────────────────────────────────────────────

describe('Pagination — unit tests', () => {
  it('renders correct range text', () => {
    render(<Pagination page={2} pageSize={10} total={50} />);
    expect(screen.getByText('11–20 sur 50')).toBeTruthy();
  });

  it('hides when total=0', () => {
    const { container } = render(<Pagination page={1} pageSize={10} total={0} />);
    expect(container.firstChild).toBeNull();
  });

  it('calls router.push when a page button is clicked', () => {
    render(<Pagination page={1} pageSize={10} total={50} />);
    // Page 2 button should be visible
    const btn = screen.getByText('2');
    fireEvent.click(btn);
    expect(mockPush).toHaveBeenCalledWith(expect.stringContaining('page=2'));
  });

  it('previous button is disabled on first page', () => {
    render(<Pagination page={1} pageSize={10} total={50} />);
    const prevBtn = screen.getByLabelText('Page précédente');
    expect(prevBtn).toHaveProperty('disabled', true);
  });

  it('next button is disabled on last page', () => {
    render(<Pagination page={5} pageSize={10} total={50} />);
    const nextBtn = screen.getByLabelText('Page suivante');
    expect(nextBtn).toHaveProperty('disabled', true);
  });
});

// ─── Property 10 ──────────────────────────────────────────────────────────────

// Feature: ui-professional-refactor, Property 10: Pagination button token usage
describe('Pagination — Property 10: Pagination button token usage', () => {
  /**
   * **Validates: Requirements 8.1, 8.2, 8.3, 8.4**
   *
   * For any current page and total:
   * - The active page button has `bg-primary-600` and `text-white` classes
   * - All page buttons have `rounded-md` class
   * - When page=1, the previous button is disabled (has `disabled` attribute +
   *   `disabled:opacity-40` class + `disabled:cursor-not-allowed` class)
   * - When page=totalPages, the next button is disabled similarly
   */
  it('active button has primary bg + white text; all buttons have rounded-md; disabled nav buttons have opacity-40 + cursor-not-allowed', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 10 }),
        fc.integer({ min: 1, max: 200 }),
        (page, total) => {
          // Clamp page to valid range for this total (pageSize=10)
          const pageSize = 10;
          const pages = totalPages(total, pageSize);
          const clampedPage = Math.min(page, pages);

          cleanup();
          const { container } = render(
            <Pagination page={clampedPage} pageSize={pageSize} total={total} />,
          );

          // Component returns null when total === 0
          if (total === 0) {
            cleanup();
            return container.firstChild === null;
          }

          // ── All page-number buttons must have rounded-md ──────────────────
          const allButtons = Array.from(container.querySelectorAll('button'));
          const pageNumberButtons = allButtons.filter((btn) => {
            const text = btn.textContent?.trim() ?? '';
            return /^\d+$/.test(text);
          });

          const allHaveRoundedMd = pageNumberButtons.every((btn) =>
            btn.className.includes('rounded-md'),
          );
          if (!allHaveRoundedMd) { cleanup(); return false; }

          // ── Active page button has bg-primary-600 and text-white ──────────
          const activeBtn = pageNumberButtons.find(
            (btn) => btn.getAttribute('aria-current') === 'page',
          );
          if (!activeBtn) { cleanup(); return false; }

          const activeBgOk = activeBtn.className.includes('bg-primary-600');
          const activeTextOk = activeBtn.className.includes('text-white');
          if (!activeBgOk || !activeTextOk) { cleanup(); return false; }

          // ── Nav buttons (prev/next) also have rounded-md ──────────────────
          const prevBtn = container.querySelector('[aria-label="Page précédente"]') as HTMLButtonElement | null;
          const nextBtn = container.querySelector('[aria-label="Page suivante"]') as HTMLButtonElement | null;

          if (!prevBtn || !nextBtn) { cleanup(); return false; }

          if (!prevBtn.className.includes('rounded-md')) { cleanup(); return false; }
          if (!nextBtn.className.includes('rounded-md')) { cleanup(); return false; }

          // ── Disabled state checks ─────────────────────────────────────────
          if (clampedPage === 1) {
            // Previous button must be disabled
            if (!prevBtn.disabled) { cleanup(); return false; }
            // Class string must contain disabled:opacity-40 and disabled:cursor-not-allowed
            if (!prevBtn.className.includes('disabled:opacity-40')) { cleanup(); return false; }
            if (!prevBtn.className.includes('disabled:cursor-not-allowed')) { cleanup(); return false; }
          }

          if (clampedPage === pages) {
            // Next button must be disabled
            if (!nextBtn.disabled) { cleanup(); return false; }
            if (!nextBtn.className.includes('disabled:opacity-40')) { cleanup(); return false; }
            if (!nextBtn.className.includes('disabled:cursor-not-allowed')) { cleanup(); return false; }
          }

          cleanup();
          return true;
        },
      ),
      { numRuns: 100 },
    );
  });
});
