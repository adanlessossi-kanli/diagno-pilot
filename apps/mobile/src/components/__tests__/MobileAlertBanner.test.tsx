/**
 * Property-based tests for MobileAlertBanner (P11)
 *
 * Feature: ui-professional-refactor, Property 11: Mobile alert banner semantic token and border usage
 *
 * For each level in {critical, warning, info}, assert:
 *  - borderLeftWidth === 4
 *  - borderLeftColor equals the semantic border token
 *  - backgroundColor equals the semantic bg token
 *  - An Ionicons component is rendered (not a Text emoji)
 *
 * Validates: Requirements 13.1, 13.2, 13.3, 13.4, 13.5
 */
import React from 'react';
import { render, screen } from '@testing-library/react-native';
import * as fc from 'fast-check';
import { MobileAlertBanner } from '../MobileAlertBanner';
import { colors } from '@diagno-pilot/ui/src/tokens';
import type { SafetyAlert } from '@diagno-pilot/types';

// Mock @expo/vector-icons so Ionicons renders as a testable component
jest.mock('@expo/vector-icons', () => {
  const React = require('react');
  const { View } = require('react-native');
  return {
    Ionicons: ({ name, accessibilityLabel, ...rest }: { name: string; accessibilityLabel?: string; [key: string]: unknown }) =>
      React.createElement(View, {
        testID: `ionicons-${name}`,
        accessibilityLabel: accessibilityLabel ?? name,
        ...rest,
      }),
  };
});

const levelTokens = {
  critical: { bg: colors.error.bg,   border: colors.error.border   },
  warning:  { bg: colors.warning.bg, border: colors.warning.border },
  info:     { bg: colors.info.bg,    border: colors.info.border    },
} as const;

const makeAlert = (level: 'critical' | 'warning' | 'info'): SafetyAlert => ({
  level,
  type: 'allergy',
  message: `Test message for ${level}`,
  affectedDrug: undefined,
});

describe('MobileAlertBanner — P11: semantic token and border usage', () => {
  // Feature: ui-professional-refactor, Property 11: Mobile alert banner semantic token and border usage
  it('P11: for any alert level, applies correct semantic tokens and renders Ionicons', () => {
    fc.assert(
      fc.property(
        fc.constantFrom('critical' as const, 'warning' as const, 'info' as const),
        (level) => {
          const { unmount } = render(<MobileAlertBanner alert={makeAlert(level)} />);

          // Find the container View (accessibilityRole="alert") using props query
          const container = screen.UNSAFE_getByProps({ accessibilityRole: 'alert' });
          const containerStyle = container.props.style;

          // Flatten style array to a single object
          const flatStyle: Record<string, unknown> = {};
          (Array.isArray(containerStyle) ? containerStyle : [containerStyle]).forEach((s) => {
            if (s && typeof s === 'object') Object.assign(flatStyle, s);
          });

          const expected = levelTokens[level];

          // Assert borderLeftWidth === 4
          expect(flatStyle.borderLeftWidth).toBe(4);

          // Assert borderLeftColor equals semantic border token
          expect(flatStyle.borderLeftColor).toBe(expected.border);

          // Assert backgroundColor equals semantic bg token
          expect(flatStyle.backgroundColor).toBe(expected.bg);

          // Assert Ionicons is rendered (not a Text emoji)
          const iconNames: Record<string, string> = {
            critical: 'alert-circle',
            warning: 'warning',
            info: 'information-circle',
          };
          expect(screen.getByTestId(`ionicons-${iconNames[level]}`)).toBeTruthy();

          unmount();
        }
      ),
      { numRuns: 100 }
    );
  });

  it('renders dismiss button when onDismiss is provided', () => {
    const onDismiss = jest.fn();
    render(<MobileAlertBanner alert={makeAlert('info')} onDismiss={onDismiss} />);
    expect(screen.getByLabelText("Fermer l'alerte")).toBeTruthy();
  });

  it('does not render dismiss button when onDismiss is absent', () => {
    render(<MobileAlertBanner alert={makeAlert('warning')} />);
    expect(screen.queryByLabelText("Fermer l'alerte")).toBeNull();
  });
});
