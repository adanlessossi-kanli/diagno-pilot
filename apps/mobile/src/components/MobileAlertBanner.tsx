// REQ-09: AlertBanner adapté React Native (StyleSheet vs CSS)
import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import type { SafetyAlert } from '@diagno-pilot/types';

export interface MobileAlertBannerProps {
  alert: SafetyAlert;
  onDismiss?: () => void;
}

const levelColors = {
  critical: { bg: '#fee2e2', border: '#dc2626', text: '#7f1d1d' },
  warning:  { bg: '#fef3c7', border: '#d97706', text: '#78350f' },
  info:     { bg: '#dbeafe', border: '#2563eb', text: '#1e3a5f' },
};

const icons: Record<string, string> = {
  critical: '🚨',
  warning: '⚠️',
  info: 'ℹ️',
};

export function MobileAlertBanner({ alert, onDismiss }: MobileAlertBannerProps) {
  const colors = levelColors[alert.level] ?? levelColors.info;

  return (
    <View
      style={[styles.container, { backgroundColor: colors.bg, borderLeftColor: colors.border }]}
      accessibilityRole="alert"
      accessibilityLiveRegion={alert.level === 'critical' ? 'assertive' : 'polite'}
    >
      <View style={styles.row}>
        <Text style={styles.icon}>{icons[alert.level]}</Text>
        <View style={styles.body}>
          <Text style={[styles.level, { color: colors.text }]}>
            {alert.level.toUpperCase()}
            {alert.affected_drug ? `  ${alert.affected_drug}` : ''}
          </Text>
          <Text style={[styles.message, { color: colors.text }]}>{alert.message}</Text>
        </View>
        {onDismiss && (
          <TouchableOpacity onPress={onDismiss} accessibilityLabel="Fermer l'alerte">
            <Text style={[styles.dismiss, { color: colors.text }]}>×</Text>
          </TouchableOpacity>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    borderLeftWidth: 4, borderRadius: 4,
    padding: 12, marginBottom: 8,
  },
  row: { flexDirection: 'row', alignItems: 'flex-start' },
  icon: { fontSize: 16, marginRight: 8 },
  body: { flex: 1 },
  level: { fontSize: 11, fontWeight: '700', letterSpacing: 0.5, textTransform: 'uppercase' },
  message: { fontSize: 13, marginTop: 2 },
  dismiss: { fontSize: 18, paddingLeft: 8, opacity: 0.7 },
});
