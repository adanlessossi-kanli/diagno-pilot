/**
 * Unit tests for BackToTop component.
 *
 * Validates:
 * - Req 6.3: Back to top button appears after scrolling > 1 viewport height
 * - Req 6.4: Smooth scroll to top on click
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, act } from '@testing-library/react';
import React from 'react';

// ─── Import component under test ─────────────────────────────────────────────

import BackToTop from '../components/BackToTop';

// ─── Setup / Teardown ─────────────────────────────────────────────────────────

let scrollListeners: Array<EventListener> = [];

beforeEach(() => {
  scrollListeners = [];

  // Mock window.scrollY and window.innerHeight
  Object.defineProperty(window, 'scrollY', { writable: true, configurable: true, value: 0 });
  Object.defineProperty(window, 'innerHeight', { writable: true, configurable: true, value: 800 });

  // Mock window.scrollTo
  window.scrollTo = vi.fn();

  // Capture scroll event listeners so we can trigger them manually
  const originalAddEventListener = window.addEventListener.bind(window);
  const originalRemoveEventListener = window.removeEventListener.bind(window);

  vi.spyOn(window, 'addEventListener').mockImplementation((event: string, handler: any, options?: any) => {
    if (event === 'scroll') {
      scrollListeners.push(handler);
    }
    return originalAddEventListener(event, handler, options);
  });

  vi.spyOn(window, 'removeEventListener').mockImplementation((event: string, handler: any) => {
    if (event === 'scroll') {
      scrollListeners = scrollListeners.filter((h) => h !== handler);
    }
    return originalRemoveEventListener(event, handler);
  });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

// ─── Helpers ──────────────────────────────────────────────────────────────────

function simulateScroll(scrollY: number) {
  Object.defineProperty(window, 'scrollY', { writable: true, configurable: true, value: scrollY });
  act(() => {
    scrollListeners.forEach((listener) => listener(new Event('scroll')));
  });
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('BackToTop', () => {
  it('button is hidden initially (scrollY is 0)', () => {
    render(<BackToTop />);

    const button = screen.getByTestId('back-to-top');
    // The button should have pointer-events-none and opacity-0 when hidden
    expect(button.className).toContain('opacity-0');
    expect(button.className).toContain('pointer-events-none');
  });

  it('button becomes visible after scrolling past 1 viewport height', () => {
    render(<BackToTop />);

    const button = screen.getByTestId('back-to-top');

    // Initially hidden
    expect(button.className).toContain('opacity-0');

    // Scroll past 1 viewport height (innerHeight = 800, so scrollY > 800)
    simulateScroll(801);

    expect(button.className).toContain('opacity-100');
    expect(button.className).not.toContain('pointer-events-none');
  });

  it('calls window.scrollTo({ top: 0, behavior: "smooth" }) on click', () => {
    render(<BackToTop />);

    // Make button visible first
    simulateScroll(1000);

    const button = screen.getByTestId('back-to-top');
    fireEvent.click(button);

    expect(window.scrollTo).toHaveBeenCalledWith({ top: 0, behavior: 'smooth' });
  });

  it('has proper aria-label', () => {
    render(<BackToTop />);

    const button = screen.getByTestId('back-to-top');
    expect(button.getAttribute('aria-label')).toBe('Back to top');
  });
});
