// REQ-04: SourceCitation adapté React Native
import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import type { DocumentSource } from '@diagno-pilot/types';

export interface MobileSourceCitationProps {
  source: DocumentSource;
}

export function MobileSourceCitation({ source }: MobileSourceCitationProps) {
  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>{source.title}</Text>
        <Text style={styles.section}> — {source.section}</Text>
      </View>
      {source.excerpt ? (
        <Text style={styles.excerpt}>"{source.excerpt}"</Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    borderLeftWidth: 3, borderLeftColor: '#93c5fd',
    backgroundColor: '#eff6ff', borderRadius: 4,
    padding: 10, marginBottom: 6,
  },
  header: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'baseline' },
  title: { fontSize: 12, fontWeight: '700', color: '#1e40af' },
  section: { fontSize: 11, color: '#6b7280' },
  excerpt: { fontSize: 12, color: '#374151', fontStyle: 'italic', marginTop: 4 },
});
