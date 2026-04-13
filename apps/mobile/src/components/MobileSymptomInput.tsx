// REQ-02: SymptomInput adapté React Native
import React, { useState } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  ScrollView,
  StyleSheet,
} from 'react-native';
import type { Symptom } from '@diagno-pilot/types';

export interface MobileSymptomInputProps {
  symptoms: Symptom[];
  onAdd: (symptom: Symptom) => void;
  onRemove: (index: number) => void;
}

const SEVERITIES = ['mild', 'moderate', 'severe'] as const;

export function MobileSymptomInput({ symptoms, onAdd, onRemove }: MobileSymptomInputProps) {
  const [name, setName] = useState('');
  const [severity, setSeverity] = useState<string>('moderate');
  const [durationDays, setDurationDays] = useState('');

  function handleAdd() {
    const trimmed = name.trim();
    if (!trimmed) return;
    onAdd({
      name: trimmed,
      severity,
      durationDays: durationDays ? parseInt(durationDays, 10) : 0,
    });
    setName('');
    setDurationDays('');
  }

  return (
    <View>
      <TextInput
        style={styles.input}
        value={name}
        onChangeText={setName}
        placeholder="Nom du symptôme"
        accessibilityLabel="Nom du symptôme"
        returnKeyType="done"
        onSubmitEditing={handleAdd}
      />

      {/* Severity picker */}
      <View style={styles.severityRow}>
        {SEVERITIES.map((s) => (
          <TouchableOpacity
            key={s}
            style={[styles.severityBtn, severity === s && styles.severityBtnActive]}
            onPress={() => setSeverity(s)}
            accessibilityRole="radio"
            accessibilityState={{ checked: severity === s }}
          >
            <Text style={[styles.severityText, severity === s && styles.severityTextActive]}>
              {s === 'mild' ? 'Léger' : s === 'moderate' ? 'Modéré' : 'Sévère'}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      <View style={styles.durationRow}>
        <TextInput
          style={[styles.input, styles.durationInput]}
          value={durationDays}
          onChangeText={setDurationDays}
          placeholder="Durée (jours)"
          keyboardType="numeric"
          accessibilityLabel="Durée en jours"
        />
        <TouchableOpacity
          style={[styles.addButton, !name.trim() && styles.addButtonDisabled]}
          onPress={handleAdd}
          disabled={!name.trim()}
          accessibilityRole="button"
          accessibilityLabel="Ajouter le symptôme"
        >
          <Text style={styles.addButtonText}>+ Ajouter</Text>
        </TouchableOpacity>
      </View>

      {symptoms.length > 0 && (
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.tagScroll}>
          {symptoms.map((s, i) => (
            <View key={`${s.name}-${i}`} style={styles.tag}>
              <Text style={styles.tagText}>
                {s.name}
                {s.severity ? ` · ${s.severity}` : ''}
                {(s.durationDays ?? 0) > 0 ? ` · ${s.durationDays}j` : ''}
              </Text>
              <TouchableOpacity
                onPress={() => onRemove(i)}
                accessibilityLabel={`Supprimer ${s.name}`}
              >
                <Text style={styles.tagRemove}>×</Text>
              </TouchableOpacity>
            </View>
          ))}
        </ScrollView>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  input: {
    borderWidth: 1, borderColor: '#d1d5db', borderRadius: 8,
    padding: 10, fontSize: 14, color: '#111827', marginBottom: 10,
  },
  severityRow: { flexDirection: 'row', gap: 8, marginBottom: 10 },
  severityBtn: {
    flex: 1, borderWidth: 1, borderColor: '#d1d5db',
    borderRadius: 6, padding: 8, alignItems: 'center',
  },
  severityBtnActive: { backgroundColor: '#2563eb', borderColor: '#2563eb' },
  severityText: { fontSize: 13, color: '#374151' },
  severityTextActive: { color: '#fff', fontWeight: '600' },
  durationRow: { flexDirection: 'row', gap: 8, marginBottom: 10 },
  durationInput: { flex: 1, marginBottom: 0 },
  addButton: {
    backgroundColor: '#2563eb', borderRadius: 8,
    paddingHorizontal: 16, justifyContent: 'center',
  },
  addButtonDisabled: { opacity: 0.5 },
  addButtonText: { color: '#fff', fontSize: 14, fontWeight: '600' },
  tagScroll: { marginBottom: 4 },
  tag: {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: '#f3f4f6', borderRadius: 16,
    paddingHorizontal: 12, paddingVertical: 6, marginRight: 8,
  },
  tagText: { fontSize: 13, color: '#374151' },
  tagRemove: { fontSize: 16, color: '#9ca3af', marginLeft: 6 },
});
