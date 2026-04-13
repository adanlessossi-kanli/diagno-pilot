import React from 'react';
import { colors, spacing, typography } from './tokens';

export type StepState = 'completed' | 'current' | 'upcoming';

export function getStepState(stepIndex: number, currentIndex: number): StepState {
  if (stepIndex < currentIndex) return 'completed';
  if (stepIndex === currentIndex) return 'current';
  return 'upcoming';
}

export interface StepProgressProps {
  steps: string[];
  currentIndex: number;
}

const containerStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: spacing[4],
};

const stepStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: spacing[2],
  fontSize: typography.sm,
};

const stateStyles: Record<StepState, { circle: React.CSSProperties; label: React.CSSProperties }> = {
  completed: {
    circle: {
      width: 24,
      height: 24,
      borderRadius: '50%',
      backgroundColor: colors.primary[600],
      color: '#FFFFFF',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      fontSize: typography.xs,
      flexShrink: 0,
    },
    label: {
      color: colors.primary[700],
      fontWeight: 600,
    },
  },
  current: {
    circle: {
      width: 24,
      height: 24,
      borderRadius: '50%',
      backgroundColor: colors.primary[600],
      color: '#FFFFFF',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      fontSize: typography.xs,
      fontWeight: 700,
      flexShrink: 0,
    },
    label: {
      color: colors.primary[700],
      fontWeight: 700,
    },
  },
  upcoming: {
    circle: {
      width: 24,
      height: 24,
      borderRadius: '50%',
      backgroundColor: colors.neutral[200],
      color: colors.neutral[500],
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      fontSize: typography.xs,
      flexShrink: 0,
    },
    label: {
      color: colors.neutral[400],
      fontWeight: 400,
    },
  },
};

const connectorBase: React.CSSProperties = {
  height: 2,
  flex: 1,
  minWidth: spacing[4],
};

function Checkmark() {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
      <path d="M2 6l3 3 5-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function StepProgress({ steps, currentIndex }: StepProgressProps) {
  return (
    <div style={containerStyle} role="group" aria-label="Progress">
      {steps.map((label, i) => {
        const state = getStepState(i, currentIndex);
        const styles = stateStyles[state];

        return (
          <React.Fragment key={i}>
            <div style={stepStyle}>
              <div style={styles.circle} aria-hidden="true">
                {state === 'completed' ? <Checkmark /> : i + 1}
              </div>
              <span style={styles.label}>{label}</span>
            </div>
            {i < steps.length - 1 && (
              <div
                style={{
                  ...connectorBase,
                  backgroundColor: i < currentIndex ? colors.primary[600] : colors.neutral[200],
                }}
                aria-hidden="true"
              />
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
}
