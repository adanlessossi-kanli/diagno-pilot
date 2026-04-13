import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, act, cleanup } from '@testing-library/react';
import React from 'react';

// ─── Mocks ────────────────────────────────────────────────────────────────────

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

import CopyButton from '../CopyButton';

// ─── Setup ────────────────────────────────────────────────────────────────────

beforeEach(() => {
  vi.useFakeTimers();
  Object.assign(navigator, {
    clipboard: {
      writeText: vi.fn().mockResolvedValue(undefined),
    },
  });
});

afterEach(() => {
  vi.useRealTimers();
  cleanup();
});

// ─── Unit tests ───────────────────────────────────────────────────────────────

describe('CopyButton', () => {
  it('renders with a copy icon by default', () => {
    render(<CopyButton text="hello" />);
    const button = screen.getByTestId('copy-button');
    expect(button).toBeDefined();
    expect(button.querySelector('svg')).not.toBeNull();
  });

  it('copies text to clipboard on click', async () => {
    render(<CopyButton text="some text to copy" />);
    const button = screen.getByTestId('copy-button');

    await act(async () => {
      fireEvent.click(button);
    });

    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('some text to copy');
  });

  it('shows "copied" feedback after clicking', async () => {
    render(<CopyButton text="test" />);
    const button = screen.getByTestId('copy-button');

    await act(async () => {
      fireEvent.click(button);
    });

    // The translated key 'copied' should appear as text
    expect(button.textContent).toContain('copied');
    // SVG icon should be gone
    expect(button.querySelector('svg')).toBeNull();
  });

  it('reverts to copy icon after ~2 seconds', async () => {
    render(<CopyButton text="test" />);
    const button = screen.getByTestId('copy-button');

    await act(async () => {
      fireEvent.click(button);
    });

    expect(button.textContent).toContain('copied');

    act(() => {
      vi.advanceTimersByTime(2000);
    });

    // Should revert back to the SVG icon
    expect(button.querySelector('svg')).not.toBeNull();
    expect(button.textContent).not.toContain('copied');
  });

  it('has data-testid="copy-button"', () => {
    render(<CopyButton text="test" />);
    expect(screen.getByTestId('copy-button')).toBeDefined();
  });

  it('handles clipboard API failure gracefully', async () => {
    (navigator.clipboard.writeText as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error('Clipboard unavailable'),
    );

    render(<CopyButton text="test" />);
    const button = screen.getByTestId('copy-button');

    // Should not throw
    await act(async () => {
      fireEvent.click(button);
    });

    // Should still show the copy icon (no "copied" feedback on failure)
    expect(button.querySelector('svg')).not.toBeNull();
  });
});
