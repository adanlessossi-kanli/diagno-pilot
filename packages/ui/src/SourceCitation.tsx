import React from 'react';
import type { DocumentSource } from '@diagno-pilot/types';

// REQ-04: Source citation for RAG responses

export interface SourceCitationProps {
  source: DocumentSource;
}

export function SourceCitation({ source }: SourceCitationProps) {
  return (
    <blockquote
      style={{
        margin: '0 0 8px',
        padding: '10px 14px',
        borderLeft: '3px solid #93c5fd',
        backgroundColor: '#eff6ff',
        borderRadius: '0 4px 4px 0',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'baseline', gap: '6px', marginBottom: source.excerpt ? '6px' : 0 }}>
        <span style={{ fontSize: '13px', fontWeight: 600, color: '#1e40af' }}>{source.title}</span>
        <span style={{ fontSize: '12px', color: '#6b7280' }}>— {source.section}</span>
      </div>
      {source.excerpt && (
        <p style={{ margin: 0, fontSize: '13px', color: '#374151', fontStyle: 'italic' }}>
          "{source.excerpt}"
        </p>
      )}
    </blockquote>
  );
}
