import React from 'react';
import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import * as fc from 'fast-check';
import { AlertBanner } from '../AlertBanner';
import type { SafetyAlert } from '@diagno-pilot/types';

// Feature: ui-professional-refactor, Property 7: Alert banner semantic token usage (web)
// For each level in {critical, warning, info}, the rendered element contains the
// correct semantic token class strings.

const levelTokenMap = {
  critical: { bg: 'bg-error-bg', border: 'border-error-border', text: 'text-error-text' },
  warning:  { bg: 'bg-warning-bg', border: 'border-warning-border', text: 'text-warning-text' },
  info:     { bg: 'bg-info-bg', border: 'border-info-border', text: 'text-info-text' },
} as const;

function makeAlert(level: 'critical' | 'warning' | 'info'): SafetyAlert {
  return {
    level,
    message: `Test ${level} alert`,
    affectedDrug: undefined,
  } as unknown as SafetyAlert;
}

describe('P7: Alert banner semantic token usage (web)', () => {
  it('renders correct semantic token classes for each alert level', () => {
    // Feature: ui-professional-refactor, Property 7: Alert banner semantic token usage (web)
    fc.assert(
      fc.property(
        fc.constantFrom('critical' as const, 'warning' as const, 'info' as const),
        (level) => {
          const { container } = render(<AlertBanner alert={makeAlert(level)} />);
          const root = container.firstElementChild as HTMLElement;
          const classes = root.className;

          const tokens = levelTokenMap[level];
          expect(classes).toContain(tokens.bg);
          expect(classes).toContain(tokens.border);
          expect(classes).toContain(tokens.text);
        },
      ),
      { numRuns: 100 },
    );
  });

  it('critical level uses error.* token classes', () => {
    const { container } = render(<AlertBanner alert={makeAlert('critical')} />);
    const root = container.firstElementChild as HTMLElement;
    expect(root.className).toContain('bg-error-bg');
    expect(root.className).toContain('border-error-border');
    expect(root.className).toContain('text-error-text');
  });

  it('warning level uses warning.* token classes', () => {
    const { container } = render(<AlertBanner alert={makeAlert('warning')} />);
    const root = container.firstElementChild as HTMLElement;
    expect(root.className).toContain('bg-warning-bg');
    expect(root.className).toContain('border-warning-border');
    expect(root.className).toContain('text-warning-text');
  });

  it('info level uses info.* token classes', () => {
    const { container } = render(<AlertBanner alert={makeAlert('info')} />);
    const root = container.firstElementChild as HTMLElement;
    expect(root.className).toContain('bg-info-bg');
    expect(root.className).toContain('border-info-border');
    expect(root.className).toContain('text-info-text');
  });

  it('renders no emoji characters', () => {
    fc.assert(
      fc.property(
        fc.constantFrom('critical' as const, 'warning' as const, 'info' as const),
        (level) => {
          const { container } = render(<AlertBanner alert={makeAlert(level)} />);
          // No emoji in the rendered text content (SVG icons used instead)
          const emojiRegex = /[\u{1F300}-\u{1FFFF}]/u;
          expect(emojiRegex.test(container.textContent ?? '')).toBe(false);
        },
      ),
      { numRuns: 100 },
    );
  });
});
