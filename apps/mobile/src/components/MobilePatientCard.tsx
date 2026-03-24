// REQ-06: PatientCard adapté React Native
import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import type { PatientProfile } from '@diagno-pilot/types';

export interface MobilePatientCardProps {
  patient: PatientProfile;
}

const ageGroupLabel: Record<string, string> = {
  neonatal: 'Néonatal (0–28j)',
  infant: 'Nourrisson (1–23 mois)',
  child: 'Enfant (2–17 ans)',
  adult: 'Adulte (18+)',
};

export function MobilePatientCard({ patient }: MobilePatientCardProps) {
  return (
    <View style={styles.card}>
      <View style={styles.header}>
        <View style={styles.avatar}>
          <Text style={styles.avatarIcon}>👤</Text>
        </View>
        <View style={styles.headerText}>
          <Text style={styles.name}>{patient.fullName ?? 'Patient inconnu'}</Text>
          {patient.ageGroup && (
            <Text style={styles.ageGroup}>
              {ageGroupLabel[patient.ageGroup] ?? patient.ageGroup}
            </Text>
          )}
        </View>
      </View>

      <View style={styles.grid}>
        {patient.weightKg !== undefined && (
          <View style={styles.row}>
            <Text style={styles.label}>Poids</Text>
            <Text style={styles.value}>{patient.weightKg} kg</Text>
          </View>
        )}
        {patient.dateOfBirth && (
          <View style={styles.row}>
            <Text style={styles.label}>Naissance</Text>
            <Text style={styles.value}>{patient.dateOfBirth}</Text>
          </View>
        )}
        <View style={styles.row}>
          <Text style={styles.label}>Allergies</Text>
          <Text style={styles.value}>
            {patient.allergies.length > 0 ? `${patient.allergies.length} connue(s)` : 'Aucune'}
          </Text>
        </View>
        {(patient.renalFailure || patient.hepaticFailure) && (
          <View style={styles.row}>
            <Text style={styles.label}>Comorbidités</Text>
            <Text style={styles.value}>
              {[
                patient.renalFailure && 'Insuff. rénale',
                patient.hepaticFailure && 'Insuff. hépatique',
              ].filter(Boolean).join(', ')}
            </Text>
          </View>
        )}
        {patient.currentMedications.length > 0 && (
          <View style={styles.row}>
            <Text style={styles.label}>Médicaments</Text>
            <Text style={styles.value}>{patient.currentMedications.length} en cours</Text>
          </View>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: '#fff', borderRadius: 10, padding: 14,
    marginBottom: 10, borderWidth: 1, borderColor: '#e5e7eb',
  },
  header: { flexDirection: 'row', alignItems: 'center', marginBottom: 12 },
  avatar: {
    width: 40, height: 40, borderRadius: 20,
    backgroundColor: '#dbeafe', justifyContent: 'center', alignItems: 'center',
    marginRight: 12,
  },
  avatarIcon: { fontSize: 20 },
  headerText: { flex: 1 },
  name: { fontSize: 15, fontWeight: '700', color: '#111827' },
  ageGroup: { fontSize: 12, color: '#6b7280', marginTop: 2 },
  grid: {},
  row: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 3 },
  label: { fontSize: 12, color: '#6b7280', fontWeight: '500' },
  value: { fontSize: 13, color: '#111827' },
});
