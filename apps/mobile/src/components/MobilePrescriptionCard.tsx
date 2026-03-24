// REQ-03: PrescriptionCard adapté React Native
import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
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
    backgroundColor: '#fff', borderRadius: 10, padding: 14,
    marginBottom: 10, borderWidth: 1, borderColor: '#e5e7eb',
  },
  header: {
    flexDirection: 'row', justifyContent: 'space-between',
    alignItems: 'center', marginBottom: 12,
  },
  antibiotic: { fontSize: 16, fontWeight: '700', color: '#111827', flex: 1 },
  cappedBadge: {
    backgroundColor: '#fef3c7', borderRadius: 12,
    paddingHorizontal: 8, paddingVertical: 3,
    borderWidth: 1, borderColor: '#fcd34d',
  },
  cappedText: { fontSize: 11, fontWeight: '600', color: '#92400e' },
  grid: {},
  row: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 4 },
  label: { fontSize: 12, color: '#6b7280', fontWeight: '500' },
  value: { fontSize: 13, color: '#111827' },
});
