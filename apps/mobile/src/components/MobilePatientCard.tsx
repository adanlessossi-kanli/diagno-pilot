// REQ-06: PatientCard adapté React Native
import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { colors, spacing, radius, typography, shadow } from '@diagno-pilot/ui/src/tokens';
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

/** Derive up-to-2-character initials from a full name */
function getInitials(fullName: string): string {
  const parts = fullName.trim().split(/\s+/);
  if (parts.length === 1) return parts[0].charAt(0).toUpperCase();
  return (parts[0].charAt(0) + parts[parts.length - 1].charAt(0)).toUpperCase();
}

export function MobilePatientCard({ patient }: MobilePatientCardProps) {
  const initials = patient.fullName ? getInitials(patient.fullName) : '?';

  return (
    <View style={styles.card}>
      <View style={styles.header}>
        <View style={styles.avatar} accessibilityLabel={`Avatar de ${patient.fullName ?? 'patient'}`}>
          <Text style={styles.avatarInitials}>{initials}</Text>
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
    backgroundColor: '#fff',
    borderRadius: radius.lg,
    padding: spacing[4],
    marginBottom: spacing[2],
    borderWidth: 1,
    borderColor: colors.neutral[200],
    elevation: shadow.mobile.sm,
  },
  header: { flexDirection: 'row', alignItems: 'center', marginBottom: spacing[3] },
  avatar: {
    width: 40,
    height: 40,
    borderRadius: radius.full,
    backgroundColor: colors.primary[600],
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: spacing[3],
  },
  avatarInitials: { fontSize: typography.sm, fontWeight: '700', color: '#fff' },
  headerText: { flex: 1 },
  name: { fontSize: typography.base, fontWeight: '700', color: colors.neutral[900] },
  ageGroup: { fontSize: typography.xs, color: colors.neutral[500], marginTop: 2 },
  grid: {},
  row: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 3 },
  label: { fontSize: typography.xs, color: colors.neutral[500], fontWeight: '500' },
  value: { fontSize: typography.sm, color: colors.neutral[900] },
});
