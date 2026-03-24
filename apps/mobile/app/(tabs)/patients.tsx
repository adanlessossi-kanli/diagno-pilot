// REQ-06, REQ-07: Liste des patients et dossier patient
import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  FlatList,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  RefreshControl,
  Alert,
} from 'react-native';
import { router } from 'expo-router';
import { useAuth } from '../../src/contexts/AuthContext';
import { MobilePatientCard } from '../../src/components/MobilePatientCard';
import type { PatientProfile } from '@diagno-pilot/types';

export default function PatientsScreen() {
  const { apiClient } = useAuth();
  const [patients, setPatients] = useState<PatientProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const fetchPatients = useCallback(async () => {
    try {
      const data = await apiClient.patients.listPatients();
      setPatients(data);
    } catch {
      Alert.alert('Erreur', 'Impossible de charger les patients.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [apiClient]);

  useEffect(() => { fetchPatients(); }, [fetchPatients]);

  function onRefresh() {
    setRefreshing(true);
    fetchPatients();
  }

  if (loading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color="#2563eb" />
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <FlatList
        data={patients}
        keyExtractor={(p) => p.id ?? p.fullName ?? Math.random().toString()}
        renderItem={({ item }) => (
          <TouchableOpacity
            onPress={() => router.push(`/patient/${item.id}`)}
            accessibilityRole="button"
            accessibilityLabel={`Ouvrir le dossier de ${item.fullName}`}
          >
            <MobilePatientCard patient={item} />
          </TouchableOpacity>
        )}
        contentContainerStyle={styles.list}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Text style={styles.emptyIcon}>👥</Text>
            <Text style={styles.emptyText}>Aucun patient enregistré.</Text>
          </View>
        }
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f9fafb' },
  centered: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  list: { padding: 12, paddingBottom: 40 },
  empty: { alignItems: 'center', paddingTop: 80 },
  emptyIcon: { fontSize: 48, marginBottom: 12 },
  emptyText: { fontSize: 14, color: '#6b7280' },
});
