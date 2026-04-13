'use client';

import { useState, useCallback } from 'react';
import { useTranslations } from 'next-intl';

export default function CopyButton({ text }: { text: string }) {
  const t = useTranslations('chat');
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Silently fail if clipboard API is unavailable
    }
  }, [text]);

  return (
    <button
      type="button"
      data-testid="copy-button"
      onClick={() => void handleCopy()}
      className="inline-flex items-center gap-1 rounded px-1.5 py-1 text-xs text-gray-500 hover:text-gray-700 hover:bg-gray-100 transition-colors"
      aria-label={copied ? t('copied') : 'Copy'}
    >
      {copied ? (
        <span className="text-green-600 font-medium">{t('copied')}</span>
      ) : (
        <svg
          xmlns="http://www.w3.org/2000/svg"
          className="h-4 w-4"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
          aria-hidden="true"
        >
          <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
        </svg>
      )}
    </button>
  );
}
