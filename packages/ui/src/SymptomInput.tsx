import React, { useState } from 'react';
import type { Symptom } from '@diagno-pilot/types';
import { colors, spacing, radius, typography } from './tokens';

// REQ-02: Symptom input for guided diagnosis mode

export interface SymptomInputProps {
  symptoms: Symptom[];
  onAdd: (symptom: Symptom) => void;
  onRemove: (index: number) => void;
}

const inputStyle: React.CSSProperties = {
  padding: `${spacing[2]}px ${spacing[3]}px`,
  border: `1px solid ${colors.neutral[200]}`,
  borderRadius: `${radius.sm}px`,
  fontSize: `${typography.sm}px`,
  outline: 'none',
  flex: 1,
  minWidth: '120px',
};

const labelStyle: React.CSSProperties = {
  fontSize: `${typography.xs}px`,
  fontWeight: 500,
  color: colors.neutral[500],
  marginBottom: `${spacing[1]}px`,
  display: 'block',
};

export function SymptomInput({ symptoms, onAdd, onRemove }: SymptomInputProps) {
  const [name, setName] = useState('');
  const [severity, setSeverity] = useState('');
  const [durationDays, setDurationDays] = useState('');

  function handleAdd() {
    const trimmed = name.trim();
    if (!trimmed) return;
    onAdd({
      name: trimmed,
      severity: severity.trim() || 'moderate',
      durationDays: durationDays ? parseInt(durationDays, 10) : 0,
    });
    setName('');
    setSeverity('');
    setDurationDays('');
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter') handleAdd();
  }

  return (
    <div style={{ fontFamily: 'inherit' }}>
      <div
        style={{
          display: 'flex',
          gap: `${spacing[2]}px`,
          flexWrap: 'wrap',
          marginBottom: `${spacing[3]}px`,
          alignItems: 'flex-end',
        }}
      >
        <div style={{ flex: 1, minWidth: '120px' }}>
          <label htmlFor="symptom-name" style={labelStyle}>Symptom name</label>
          <input
            id="symptom-name"
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Symptom name"
            aria-label="Symptom name"
            style={inputStyle}
          />
        </div>
        <div style={{ minWidth: '120px', maxWidth: '140px' }}>
          <label htmlFor="symptom-severity" style={labelStyle}>Severity</label>
          <select
            id="symptom-severity"
            value={severity}
            onChange={(e) => setSeverity(e.target.value)}
            aria-label="Severity"
            style={{ ...inputStyle, maxWidth: '140px' }}
          >
            <option value="">Severity…</option>
            <option value="mild">Mild</option>
            <option value="moderate">Moderate</option>
            <option value="severe">Severe</option>
          </select>
        </div>
        <div style={{ minWidth: '80px', maxWidth: '80px' }}>
          <label htmlFor="symptom-duration" style={labelStyle}>Duration (days)</label>
          <input
            id="symptom-duration"
            type="number"
            value={durationDays}
            onChange={(e) => setDurationDays(e.target.value)}
            placeholder="Days"
            aria-label="Duration in days"
            min={0}
            style={{ ...inputStyle, maxWidth: '80px' }}
          />
        </div>
        <button
          onClick={handleAdd}
          disabled={!name.trim()}
          style={{
            padding: `${spacing[2]}px ${spacing[4]}px`,
            backgroundColor: colors.primary[600],
            color: '#fff',
            border: 'none',
            borderRadius: `${radius.sm}px`,
            cursor: name.trim() ? 'pointer' : 'not-allowed',
            opacity: name.trim() ? 1 : 0.5,
            fontSize: `${typography.sm}px`,
          }}
        >
          Add
        </button>
      </div>

      {symptoms.length > 0 && (
        <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexWrap: 'wrap', gap: `${spacing[2]}px` }}>
          {symptoms.map((s, i) => (
            <li
              key={i}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: `${spacing[1] + 2}px`,
                backgroundColor: colors.neutral[100],
                borderRadius: `${radius.xl}px`,
                padding: `${spacing[1]}px ${spacing[3]}px`,
                fontSize: `${typography.xs + 1}px`,
                color: colors.neutral[700],
              }}
            >
              <span>{s.name}</span>
              {s.severity && <span style={{ color: colors.neutral[500] }}>· {s.severity}</span>}
              {s.durationDays != null && s.durationDays > 0 && (
                <span style={{ color: colors.neutral[500] }}>· {s.durationDays}d</span>
              )}
              <button
                onClick={() => onRemove(i)}
                aria-label={`Remove ${s.name}`}
                style={{
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  fontSize: `${typography.sm}px`,
                  lineHeight: 1,
                  color: colors.neutral[400],
                  padding: `0 0 0 ${spacing[1]}px`,
                }}
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
