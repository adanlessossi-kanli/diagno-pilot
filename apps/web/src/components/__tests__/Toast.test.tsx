import fc from 'fast-check';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, cleanup, act } from '@testing-library/react';
import React from 'react';
import { Toast } from '../Toast';

// ─── Setup ────────────────────────────────────────────────────────────────────

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  cleanup();
});

// ─── Unit tests ───────────────────────────────────────────────────────────────

describe('Toast — unit tests', () => {
  it('renders the message', () => {
    const { container } = render(<Toast message="Hello world" />);
    expect(container.textContent).toContain('Hello world');
  });

  it('auto-dismisses after the default duration (3000ms)', () => {
    const onClose = vi.fn();
    const { container } = render(<Toast message="Bye" onClose={onClose} />);

    expect(container.querySelector('[role="status"]')).not.toBeNull();

    act(() => {
      vi.advanceTimersByTime(3000);
    });

    expect(container.querySelector('[role="status"]')).toBeNull();
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('auto-dismisses after a custom duration', () => {
    const onClose = vi.fn();
    const { container } = render(<Toast message="Custom" duration={1500} onClose={onClose} />);

    act(() => {
      vi.advanceTimersByTime(1499);
    });
    expect(container.querySelector('[role="status"]')).not.toBeNull();

    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(container.querySelector('[role="status"]')).toBeNull();
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('calls onClose when dismissed', () => {
    const onClose = vi.fn();
    render(<Toast message="Test" onClose={onClose} />);

    act(() => {
      vi.advanceTimersByTime(3000);
    });

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('does not call onClose before duration elapses', () => {
    const onClose = vi.fn();
    render(<Toast message="Test" onClose={onClose} />);

    act(() => {
      vi.advanceTimersByTime(2999);
    });

    expect(onClose).not.toHaveBeenCalled();
  });
});

// ─── Property 8 ───────────────────────────────────────────────────────────────

// Feature: ui-professional-refactor, Property 8: Toast semantic token usage
describe('Toast — Property 8: Toast semantic token usage', () => {
  /**
   * **Validates: Requirements 6.4**
   * Property 8: For any toast type in {success, error, info}, the rendered Toast
   * component must apply the corresponding semantic color token classes.
   *
   * Expected classes:
   *   success → bg-success-border text-white
   *   error   → bg-error-border text-white
   *   info    → bg-info-border text-white
   *
   * All variants also include animate-slide-in-top.
   */
  it('applies the correct semantic token class for each toast type', () => {
    const expectedClasses: Record<'success' | 'error' | 'info', string> = {
      success: 'bg-success-border',
      error: 'bg-error-border',
      info: 'bg-info-border',
    };

    fc.assert(
      fc.property(
        fc.constantFrom('success' as const, 'error' as const, 'info' as const),
        (type) => {
          cleanup();
          const { container } = render(<Toast message="Test" type={type} />);

          const el = container.querySelector('[role="status"]');
          if (!el) { cleanup(); return false; }

          const classes = el.className;

          // Must have the correct semantic background token class
          const hasBgClass = classes.includes(expectedClasses[type]);

          // Must have white text
          const hasTextWhite = classes.includes('text-white');

          // Must have the slide-in animation
          const hasAnimation = classes.includes('animate-slide-in-top');

          // Must NOT have the other types' bg classes
          const otherTypes = (['success', 'error', 'info'] as const).filter((t) => t !== type);
          const hasNoOtherBgClass = otherTypes.every(
            (t) => !classes.includes(expectedClasses[t]),
          );

          cleanup();
          return hasBgClass && hasTextWhite && hasAnimation && hasNoOtherBgClass;
        },
      ),
      { numRuns: 100 },
    );
  });
});
