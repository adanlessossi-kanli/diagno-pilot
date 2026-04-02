// REQ-09: AlertBanner adapté React Native (StyleSheet vs CSS)
import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { colors, spacing, radius, typography } from '@diagno-pilot/ui/src/tokens';
import type { SafetyAlert } from '@diagno-pilot/types';

// eslint-disable-next-line @typescript-eslint/no-require-imports, @typescript-eslint/no-explicit-any
const { Ionicons } = require('@expo/vector-icons') as { Ionicons: any };

export interface MobileAlertBannerProps {
  alert: SafetyAlert;
  onDismiss?: () => void;
}

const levelTokens = {
  critical: { bg: colors.error.bg,   border: colors.error.border,   text: colors.error.text   },
  warning:  { bg: colors.warning.bg, border: colors.warning.border, text: colors.warning.text },
  info:     { bg: colors.info.bg,    border: colors.info.border,    text: colors.info.text    },
} as const;

const levelIcons: Record<string, string> = {
  critical: 'alert-circle',
  warning:  'warning',
  info:     'information-circle',
};

export function MobileAlertBanner({ alert, onDismiss }: MobileAlertBannerProps) {
  const tokens = levelTokens[alert.level] ?? levelTokens.info;
  const iconName = levelIcons[alert.level] ?? 'information-circle';

  return (
    <View
      style={[styles.container, { backgroundColor: tokens.bg, borderLeftColor: tokens.border }]}
      accessibilityRole="alert"
      accessibilityLiveRegion={alert.level === 'critical' ? 'assertive' : 'polite'}
    >
      <View style={styles.row}>
        <Ionicons
          name={iconName}
          size={typography.base}
          color={tokens.text}
          style={styles.icon}
          accessibilityLabel={alert.level}
        />
        <View style={styles.body}>
          <Text style={[styles.level, { color: tokens.text }]}>
            {alert.level.toUpperCase()}
            {alert.affected_drug ? `  ${alert.affected_drug}` : ''}
          </Text>
          <Text style={[styles.message, { color: tokens.text }]}>{alert.message}</Text>
        </View>
        {onDismiss && (
          <TouchableOpacity onPress={onDismiss} accessibilityLabel="Fermer l'alerte">
            <Text style={[styles.dismiss, { color: tokens.text }]}>×</Text>
          </TouchableOpacity>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    borderLeftWidth: 4,
    borderRadius: radius.sm,
    padding: spacing[3],
    marginBottom: spacing[2],
  },
  row: { flexDirection: 'row', alignItems: 'flex-start' },
  icon: { marginRight: spacing[2] },
  body: { flex: 1 },
  level: { fontSize: typography.xs, fontWeight: '700', letterSpacing: 0.5, textTransform: 'uppercase' },
  message: { fontSize: typography.sm, marginTop: 2 },
  dismiss: { fontSize: typography.lg, paddingLeft: spacing[2], opacity: 0.7 },
});
