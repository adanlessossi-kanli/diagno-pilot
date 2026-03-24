import React from 'react';
import type { SafetyAlert } from '@diagno-pilot/types';

// REQ-09: AlertBanner must clearly distinguish critical vs warning alerts

const styles: Record<string, React.CSSProperties> = {
  critical: {
    backgroundColor: '#fee2e2',
    borderLeft: '4px solid #dc2626',
    color: '#7f1d1d',
  },
  warning: {
    backgroundColor: '#fef3c7',
    borderLeft: '4px solid #d97706',
    color: '#78350f',
  },
  info: {
    backgroundColor: '#dbeafe',
    borderLeft: '4px solid #2563eb',
    color: '#1e3a5f',
  },
};

const icons: Record<string, string> = {
  critical: '🚨',
  warning: '⚠️',
  info: 'ℹ️',
};

export interface AlertBannerProps {
  alert: SafetyAlert;
  onDismiss?: () => void;
}

export function AlertBanner({ alert, onDismiss }: AlertBannerProps) {
  const levelStyle = styles[alert.level] ?? styles.info;

  return (
    <div
      role="alert"
      aria-live={alert.level === 'critical' ? 'assertive' : 'polite'}
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        justifyContent: 'space-between',
        padding: '12px 16px',
        borderRadius: '4px',
        marginBottom: '8px',
        ...levelStyle,
      }}
    >
      <div style={{ display: 'flex', gap: '8px', flex: 1 }}>
        <span aria-hidden="true">{icons[alert.level]}</span>
        <div>
          <strong style={{ textTransform: 'uppercase', fontSize: '12px', letterSpacing: '0.05em' }}>
            {alert.level}
          </strong>
          {alert.affected_drug && (
            <span style={{ marginLeft: '8px', fontWeight: 600 }}>{alert.affected_drug}</span>
          )}
          <p style={{ margin: '4px 0 0', fontSize: '14px' }}>{alert.message}</p>
        </div>
      </div>
      {onDismiss && (
        <button
          onClick={onDismiss}
          aria-label="Dismiss alert"
          style={{
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            fontSize: '16px',
            lineHeight: 1,
            padding: '0 0 0 8px',
            color: 'inherit',
            opacity: 0.7,
          }}
        >
          ×
        </button>
      )}
    </div>
  );
}
