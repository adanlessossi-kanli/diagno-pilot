import React, { useState } from 'react';
import type { Symptom } from '@diagno-pilot/types';

// REQ-02: Symptom input for guided diagnosis mode

export interface SymptomInputProps {
  symptoms: Symptom[];
  onAdd: (symptom: Symptom) => void;
  onRemove: (index: number) => void;
}

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
          gap: '8px',
          flexWrap: 'wrap',
          marginBottom: '12px',
        }}
      >
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Symptom name"
          aria-label="Symptom name"
          style={inputStyle}
        />
        <select
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
        <input
          type="number"
          value={durationDays}
          onChange={(e) => setDurationDays(e.target.value)}
          placeholder="Days"
          aria-label="Duration in days"
          min={0}
          style={{ ...inputStyle, maxWidth: '80px' }}
        />
        <button
          onClick={handleAdd}
          disabled={!name.trim()}
          style={{
            padding: '8px 16px',
            backgroundColor: '#2563eb',
            color: '#fff',
            border: 'none',
            borderRadius: '4px',
            cursor: name.trim() ? 'pointer' : 'not-allowed',
            opacity: name.trim() ? 1 : 0.5,
            fontSize: '14px',
          }}
        >
          Add
        </button>
      </div>

      {symptoms.length > 0 && (
        <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
          {symptoms.map((s, i) => (
            <li
              key={i}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                backgroundColor: '#f3f4f6',
                borderRadius: '16px',
                padding: '4px 12px',
                fontSize: '13px',
                color: '#374151',
              }}
            >
              <span>{s.name}</span>
              {s.severity && <span style={{ color: '#6b7280' }}>· {s.severity}</span>}
              {s.durationDays != null && s.durationDays > 0 && (
                <span style={{ color: '#6b7280' }}>· {s.durationDays}d</span>
              )}
              <button
                onClick={() => onRemove(i)}
                aria-label={`Remove ${s.name}`}
                style={{
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  fontSize: '14px',
                  lineHeight: 1,
                  color: '#9ca3af',
                  padding: '0 0 0 4px',
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

const inputStyle: React.CSSProperties = {
  padding: '8px 12px',
  border: '1px solid #d1d5db',
  borderRadius: '4px',
  fontSize: '14px',
  outline: 'none',
  flex: 1,
  minWidth: '120px',
};
