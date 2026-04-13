import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, cleanup, act } from '@testing-library/react';
import React from 'react';

// Mock next-intl before importing the component
vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

import OfflineBanner, { _resetHealthCheckState } from '../OfflineBanner';

// ─── Helpers ──────────────────────────────────────────────────────────────────

function setNavigatorOnLine(value: boolean) {
  Object.defineProperty(navigator, 'onLine', {
    value,
    writable: true,
    configurable: true,
  });
}

function fireWindowEvent(event: string) {
  window.dispatchEvent(new Event(event));
}

// ─── Setup ────────────────────────────────────────────────────────────────────

beforeEach(() => {
  vi.useFakeTimers();
  setNavigatorOnLine(true);
  _resetHealthCheckState();
  // Default: health check succeeds
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(null, { status: 200 }),
  );
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  cleanup();
});

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('OfflineBanner', () => {
  it('renders nothing when navigator.onLine is true and health checks pass', async () => {
    const { container } = render(<OfflineBanner />);

    // Let the initial health check resolve
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(container.querySelector('[role="alert"]')).toBeNull();
  });

  it('shows banner when navigator.onLine is false', async () => {
    setNavigatorOnLine(false);

    const { container } = render(<OfflineBanner />);

    // Let the initial health check resolve
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    const alert = container.querySelector('[role="alert"]');
    expect(alert).not.toBeNull();
    expect(alert!.textContent).toBe('offline');
  });

  it('auto-hides when connectivity is restored (online event fires)', async () => {
    setNavigatorOnLine(false);

    const { container } = render(<OfflineBanner />);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    // Banner should be visible
    expect(container.querySelector('[role="alert"]')).not.toBeNull();

    // Simulate connectivity restored
    await act(async () => {
      setNavigatorOnLine(true);
      fireWindowEvent('online');
    });

    expect(container.querySelector('[role="alert"]')).toBeNull();
  });

  it('shows banner after 3 consecutive health check failures even when navigator.onLine is true', async () => {
    setNavigatorOnLine(true);

    // Health check throws network error (server unreachable)
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('Failed to fetch'));

    const { container } = render(<OfflineBanner />);

    // Initial health check (failure 1)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(container.querySelector('[role="alert"]')).toBeNull();

    // Advance 30s — failure 2
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });

    expect(container.querySelector('[role="alert"]')).toBeNull();

    // Advance 30s — failure 3 → banner should appear
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });

    expect(container.querySelector('[role="alert"]')).not.toBeNull();
  });

  it('resets health check failure count when a health check succeeds', async () => {
    setNavigatorOnLine(true);

    const fetchMock = vi.spyOn(globalThis, 'fetch');

    // First 2 calls throw network error, then succeed, then 2 more throw
    fetchMock
      .mockRejectedValueOnce(new TypeError('Failed to fetch')) // fail 1
      .mockRejectedValueOnce(new TypeError('Failed to fetch')) // fail 2
      .mockResolvedValueOnce(new Response(null, { status: 200 })) // success → reset
      .mockRejectedValueOnce(new TypeError('Failed to fetch')) // fail 1 (after reset)
      .mockRejectedValueOnce(new TypeError('Failed to fetch')); // fail 2 (after reset)

    const { container } = render(<OfflineBanner />);

    // Initial health check — fail 1
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    // 30s — fail 2
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });

    // 30s — success (resets counter)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });

    expect(container.querySelector('[role="alert"]')).toBeNull();

    // 30s — fail 1 after reset
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });

    // 30s — fail 2 after reset (still only 2, not 3)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });

    // Should still be hidden — only 2 consecutive failures after reset
    expect(container.querySelector('[role="alert"]')).toBeNull();
  });

  it('hides banner when online event fires (resets health check failures too)', async () => {
    setNavigatorOnLine(true);

    // All health checks throw network error (server unreachable)
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('Failed to fetch'));

    const { container } = render(<OfflineBanner />);

    // Trigger 3 consecutive failures
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });

    // Banner should be visible
    expect(container.querySelector('[role="alert"]')).not.toBeNull();

    // Now switch fetch to succeed and fire online event
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(null, { status: 200 }),
    );

    await act(async () => {
      fireWindowEvent('online');
    });

    // Banner should be hidden — online event resets health check failures
    expect(container.querySelector('[role="alert"]')).toBeNull();
  });
});
