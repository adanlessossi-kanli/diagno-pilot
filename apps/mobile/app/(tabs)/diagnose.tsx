// REQ-02, REQ-03, REQ-09: Mode guidé — diagnostic différentiel + prescription
import React, { useState } from 'react';
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  TouchableOpacity,
  Alert,
  ActivityIndicator,
} from 'react-native';
import { useAuth } from '../../src/contexts/AuthContext';
import { MobileSymptomInput } from '../../src/components/MobileSymptomInput';
import { MobilePrescriptionCard } from '../../src/components/MobilePrescriptionCard';
import { MobileAlertBanner } from '../../src/components/MobileAlertBanner';
import type { Symptom, Prescription, SafetyAlert } from '@diagno-pilot/types';
import type { DiagnosisResponse } from '@diagno-pilot/api-client';
import { getProbabilityColor } from '../../src/utils/probabilityColor';

type Step = 'symptoms' | 'differential' | 'prescription';
type DiagnosisEntry = DiagnosisResponse['diagnoses'][number];

export default function DiagnoseScreen() {
  const { apiClient } = useAuth();
  const [step, setStep] = useState<Step>('symptoms');
  const [symptoms, setSymptoms] = useState<Symptom[]>([]);
  const [diagnoses, setDiagnoses] = useState<DiagnosisEntry[]>([]);
  const [selectedDiagnosis, setSelectedDiagnosis] = useState<DiagnosisEntry | null>(null);
  const [prescription, setPrescription] = useState<Prescription | null>(null);
  const [alerts, setAlerts] = useState<SafetyAlert[]>([]);
  const [loading, setLoading] = useState(false);

  async function handleGetDiagnoses() {
    if (symptoms.length === 0) return;
    setLoading(true);
    try {
      const res = await apiClient.diagnose.getSymptomsDiagnosis(symptoms);
      setDiagnoses(res.diagnoses);
      setStep('differential');
    } catch {
      Alert.alert('Erreur', 'Impossible d\'obtenir les diagnostics. Vérifiez votre connexion.');
    } finally {
      setLoading(false);
    }
  }

  async function handleGetPrescription(diagnosis: DiagnosisEntry) {
    setSelectedDiagnosis(diagnosis);
    setLoading(true);
    try {
      const res = await apiClient.diagnose.getPrescription(diagnosis.condition, {
        allergies: [],
        renalFailure: false,
        hepaticFailure: false,
        currentMedications: [],
      });
      setPrescription(res.prescription);
      setAlerts(res.alerts);
      setStep('prescription');
    } catch {
      Alert.alert('Erreur', 'Impossible d\'obtenir la prescription.');
    } finally {
      setLoading(false);
    }
  }

  function handleReset() {
    setStep('symptoms');
    setSymptoms([]);
    setDiagnoses([]);
    setSelectedDiagnosis(null);
    setPrescription(null);
    setAlerts([]);
  }

  const criticalAlerts = alerts.filter((a) => a.level === 'critical');

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      {/* Step indicator */}
      <View style={styles.stepRow}>
        {(['symptoms', 'differential', 'prescription'] as Step[]).map((s, i) => (
          <View key={s} style={styles.stepItem}>
            <View style={[styles.stepDot, step === s && styles.stepDotActive]}>
              <Text style={[styles.stepNum, step === s && styles.stepNumActive]}>{i + 1}</Text>
            </View>
            <Text style={[styles.stepLabel, step === s && styles.stepLabelActive]}>
              {s === 'symptoms' ? 'Symptômes' : s === 'differential' ? 'Diagnostic' : 'Prescription'}
            </Text>
          </View>
        ))}
      </View>

      {/* Step 1: Symptoms */}
      {step === 'symptoms' && (
        <View>
          <Text style={styles.sectionTitle}>Saisir les symptômes</Text>
          <MobileSymptomInput
            symptoms={symptoms}
            onAdd={(s) => setSymptoms((prev) => [...prev, s])}
            onRemove={(i) => setSymptoms((prev) => prev.filter((_, idx) => idx !== i))}
          />
          <TouchableOpacity
            style={[styles.primaryButton, symptoms.length === 0 && styles.buttonDisabled]}
            onPress={handleGetDiagnoses}
            disabled={loading || symptoms.length === 0}
            accessibilityRole="button"
          >
            {loading ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <Text style={styles.primaryButtonText}>Obtenir les diagnostics →</Text>
            )}
          </TouchableOpacity>
        </View>
      )}

      {/* Step 2: Differential diagnoses */}
      {step === 'differential' && (
        <View>
          <Text style={styles.sectionTitle}>Diagnostics différentiels</Text>
          {diagnoses.map((d, i) => (
            <TouchableOpacity
              key={`${d.condition}-${i}`}
              style={styles.diagnosisCard}
              onPress={() => handleGetPrescription(d)}
              accessibilityRole="button"
              accessibilityLabel={`Sélectionner ${d.condition}`}
            >
              <View style={styles.diagnosisHeader}>
                <Text style={styles.diagnosisName}>{d.condition}</Text>
                <View style={[styles.probBadge, { backgroundColor: getProbabilityColor(d.probability) }]}>
                  <Text style={styles.probText}>{Math.round(d.probability * 100)}%</Text>
                </View>
              </View>
              {d.icdCode && (
                <Text style={styles.icdCode}>CIM-10 : {d.icdCode}</Text>
              )}
              {d.concordantSymptoms.length > 0 && (
                <Text style={styles.concordant}>
                  Symptômes concordants : {d.concordantSymptoms.join(', ')}
                </Text>
              )}
            </TouchableOpacity>
          ))}
          <TouchableOpacity style={styles.secondaryButton} onPress={handleReset}>
            <Text style={styles.secondaryButtonText}>← Recommencer</Text>
          </TouchableOpacity>
        </View>
      )}

      {/* Step 3: Prescription + alerts */}
      {step === 'prescription' && prescription && (
        <View>
          <Text style={styles.sectionTitle}>
            Prescription — {selectedDiagnosis?.condition}
          </Text>

          {/* Critical alerts block prescription */}
          {criticalAlerts.length > 0 && (
            <View style={styles.criticalBlock} testID="alert-critical">
              <Text style={styles.criticalBlockTitle}>⛔ Alertes critiques</Text>
              {criticalAlerts.map((a, i) => (
                <MobileAlertBanner key={`critical-${a.type}-${i}`} alert={a} />
              ))}
            </View>
          )}

          {/* Non-critical alerts */}
          {alerts.filter((a) => a.level !== 'critical').map((a, i) => (
            <MobileAlertBanner key={`alert-${a.type}-${i}`} alert={a} />
          ))}

          <MobilePrescriptionCard prescription={prescription} />

          <TouchableOpacity style={styles.secondaryButton} onPress={() => setStep('differential')}>
            <Text style={styles.secondaryButtonText}>← Changer de diagnostic</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.secondaryButton} onPress={handleReset}>
            <Text style={styles.secondaryButtonText}>Nouvelle consultation</Text>
          </TouchableOpacity>
        </View>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f9fafb' },
  content: { padding: 16, paddingBottom: 40 },
  stepRow: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 24 },
  stepItem: { alignItems: 'center', flex: 1 },
  stepDot: {
    width: 28, height: 28, borderRadius: 14,
    backgroundColor: '#e5e7eb', justifyContent: 'center', alignItems: 'center',
  },
  stepDotActive: { backgroundColor: '#2563eb' },
  stepNum: { fontSize: 13, fontWeight: '600', color: '#6b7280' },
  stepNumActive: { color: '#fff' },
  stepLabel: { fontSize: 11, color: '#9ca3af', marginTop: 4, textAlign: 'center' },
  stepLabelActive: { color: '#2563eb', fontWeight: '600' },
  sectionTitle: { fontSize: 18, fontWeight: '700', color: '#111827', marginBottom: 16 },
  diagnosisCard: {
    backgroundColor: '#fff', borderRadius: 10, padding: 14,
    marginBottom: 10, borderWidth: 1, borderColor: '#e5e7eb',
  },
  diagnosisHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  diagnosisName: { fontSize: 15, fontWeight: '600', color: '#111827', flex: 1 },
  probBadge: { borderRadius: 12, paddingHorizontal: 10, paddingVertical: 3 },
  probText: { fontSize: 13, fontWeight: '700', color: '#374151' },
  icdCode: { fontSize: 12, color: '#6b7280', marginTop: 4 },
  concordant: { fontSize: 12, color: '#6b7280', marginTop: 2 },
  primaryButton: {
    backgroundColor: '#2563eb', borderRadius: 8, padding: 14,
    alignItems: 'center', marginTop: 16,
  },
  buttonDisabled: { opacity: 0.5 },
  primaryButtonText: { color: '#fff', fontSize: 16, fontWeight: '600' },
  secondaryButton: {
    borderWidth: 1, borderColor: '#d1d5db', borderRadius: 8,
    padding: 12, alignItems: 'center', marginTop: 10,
  },
  secondaryButtonText: { color: '#374151', fontSize: 14 },
  criticalBlock: {
    backgroundColor: '#fef2f2', borderRadius: 8, padding: 12,
    marginBottom: 12, borderWidth: 1, borderColor: '#fca5a5',
  },
  criticalBlockTitle: { fontSize: 14, fontWeight: '700', color: '#dc2626', marginBottom: 8 },
});
