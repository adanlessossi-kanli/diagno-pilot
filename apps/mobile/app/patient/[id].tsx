// REQ-07: Dossier patient — historique des consultations
import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  ActivityIndicator,
  Alert,
  TouchableOpacity,
} from 'react-native';
import { useLocalSearchParams, router } from 'expo-router';
import { useAuth } from '../../src/contexts/AuthContext';
import { MobilePatientCard } from '../../src/components/MobilePatientCard';
import type { PatientProfile, Consultation } from '@diagno-pilot/types';

export default function PatientDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { apiClient } = useAuth();
  const [patient, setPatient] = useState<PatientProfile | null>(null);
  const [consultations, setConsultations] = useState<Consultation[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    if (!id) return;
    try {
      const [p, c] = await Promise.all([
        apiClient.patients.getPatient(id),
        apiClient.patients.listConsultations(id),
      ]);
      setPatient(p);
      setConsultations(c);
    } catch {
      Alert.alert('Erreur', 'Impossible de charger le dossier patient.');
    } finally {
      setLoading(false);
    }
  }, [id, apiClient]);

  useEffect(() => { fetchData(); }, [fetchData]);

  if (loading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color="#2563eb" />
      </View>
    );
  }

  if (!patient) {
    return (
      <View style={styles.centered}>
        <Text style={styles.errorText}>Patient introuvable.</Text>
        <TouchableOpacity onPress={() => router.back()}>
          <Text style={styles.backLink}>← Retour</Text>
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <TouchableOpacity onPress={() => router.back()} style={styles.backButton}>
        <Text style={styles.backLink}>← Patients</Text>
      </TouchableOpacity>

      <MobilePatientCard patient={patient} />

      <Text style={styles.sectionTitle}>
        Historique des consultations ({consultations.length})
      </Text>

      {consultations.length === 0 ? (
        <Text style={styles.emptyText}>Aucune consultation enregistrée.</Text>
      ) : (
        consultations.map((c) => (
          <View key={c.id} style={styles.consultationCard}>
            <Text style={styles.consultDate}>
              {new Date(c.createdAt).toLocaleDateString('fr-FR', {
                day: '2-digit', month: 'long', year: 'numeric',
              })}
            </Text>

            {c.symptoms.length > 0 && (
              <Text style={styles.consultDetail}>
                Symptômes : {c.symptoms.map((s) => s.name).join(', ')}
              </Text>
            )}

            {c.diagnoses.length > 0 && (
              <Text style={styles.consultDetail}>
                Diagnostic retenu : {c.diagnoses[0].condition}
                {c.diagnoses[0].icdCode ? ` (${c.diagnoses[0].icdCode})` : ''}
              </Text>
            )}

            {c.prescription && (
              <Text style={styles.consultDetail}>
                Prescription : {c.prescription.antibiotic} {c.prescription.doseMg}mg —{' '}
                {c.prescription.frequency} × {c.prescription.durationDays}j
              </Text>
            )}

            {c.alerts.filter((a) => a.level === 'critical').length > 0 && (
              <Text style={styles.criticalTag}>⚠ Alerte critique</Text>
            )}
          </View>
        ))
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f9fafb' },
  content: { padding: 16, paddingBottom: 40 },
  centered: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  backButton: { marginBottom: 12 },
  backLink: { color: '#2563eb', fontSize: 14, fontWeight: '600' },
  sectionTitle: { fontSize: 16, fontWeight: '700', color: '#111827', marginTop: 20, marginBottom: 12 },
  emptyText: { fontSize: 14, color: '#6b7280', textAlign: 'center', paddingVertical: 20 },
  errorText: { fontSize: 15, color: '#dc2626', marginBottom: 12 },
  consultationCard: {
    backgroundColor: '#fff', borderRadius: 10, padding: 14,
    marginBottom: 10, borderWidth: 1, borderColor: '#e5e7eb',
  },
  consultDate: { fontSize: 13, fontWeight: '700', color: '#2563eb', marginBottom: 6 },
  consultDetail: { fontSize: 13, color: '#374151', marginBottom: 3 },
  criticalTag: { fontSize: 12, color: '#dc2626', fontWeight: '600', marginTop: 4 },
});
