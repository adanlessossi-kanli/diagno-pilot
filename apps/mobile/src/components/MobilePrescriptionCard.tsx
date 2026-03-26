// REQ-03: PrescriptionCard adapté React Native
import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { colors, spacing, radius, typography, shadow } from '@diagno-pilot/ui/src/tokens';
import type { Prescription } from '@diagno-pilot/types';

export interface MobilePrescriptionCardProps {
  prescription: Prescription;
}

export function MobilePrescriptionCard({ prescription: rx }: MobilePrescriptionCardProps) {
  return (
    <View style={styles.card}>
      <View style={styles.header}>
        <Text style={styles.antibiotic}>{rx.antibiotic}</Text>
        {rx.is_capped_to_adult_dose && (
          <View style={styles.cappedBadge}>
            <Text style={styles.cappedText}>⚠ Dose adulte max</Text>
          </View>
        )}
      </View>

      <View style={styles.grid}>
        <View style={styles.row}>
          <Text style={styles.label}>Dose</Text>
          <Text style={styles.value}>
            {rx.dose_mg} mg
            {rx.dose_per_kg !== undefined ? ` (${rx.dose_per_kg} mg/kg)` : ''}
          </Text>
        </View>
        <View style={styles.row}>
          <Text style={styles.label}>Fréquence</Text>
          <Text style={styles.value}>{rx.frequency}</Text>
        </View>
        <View style={styles.row}>
          <Text style={styles.label}>Durée</Text>
          <Text style={styles.value}>
            {rx.duration_days} jour{rx.duration_days !== 1 ? 's' : ''}
          </Text>
        </View>
        <View style={styles.row}>
          <Text style={styles.label}>Voie</Text>
          <Text style={styles.value}>{rx.route}</Text>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: '#fff',
    borderRadius: radius.lg,
    padding: spacing[4],
    marginBottom: spacing[2],
    borderWidth: 1,
    borderColor: colors.neutral[200],
    elevation: shadow.mobile.sm,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing[3],
  },
  antibiotic: { fontSize: typography.base, fontWeight: '700', color: colors.neutral[900], flex: 1 },
  cappedBadge: {
    backgroundColor: colors.warning.bg,
    borderRadius: radius.full,
    paddingHorizontal: spacing[2],
    paddingVertical: 3,
    borderWidth: 1,
    borderColor: colors.warning.border,
  },
  cappedText: { fontSize: typography.xs, fontWeight: '600', color: colors.warning.text },
  grid: {},
  row: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: spacing[1] },
  label: { fontSize: typography.xs, color: colors.neutral[500], fontWeight: '500' },
  value: { fontSize: typography.sm, color: colors.neutral[900] },
});
