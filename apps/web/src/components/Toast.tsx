'use client';

import { useEffect, useState, useCallback } from 'react';

interface ToastProps {
  message: string;
  type?: 'success' | 'error' | 'info';
  duration?: number; // ms, default 3000
  onClose?: () => void;
}

export function Toast({ message, type = 'success', duration = 3000, onClose }: ToastProps) {
  const [visible, setVisible] = useState(true);

  const dismiss = useCallback(() => {
    setVisible(false);
    onClose?.();
  }, [onClose]);

  useEffect(() => {
    const timer = setTimeout(dismiss, duration);
    return () => clearTimeout(timer);
  }, [duration, dismiss]);

  if (!visible) return null;

  const colorClass =
    type === 'success'
      ? 'bg-success-border text-white'
      : type === 'error'
        ? 'bg-error-border text-white'
        : 'bg-info-border text-white';

  return (
    <div
      role="status"
      aria-live="polite"
      className={`fixed top-4 right-4 z-50 px-4 py-3 rounded-lg shadow-lg text-sm font-medium transition-opacity animate-slide-in-top flex items-center gap-2 ${colorClass}`}
    >
      <span>{message}</span>
      <button
        onClick={dismiss}
        aria-label="Dismiss"
        className="bg-transparent border-0 cursor-pointer text-white text-base leading-none p-0 ml-2 opacity-80 hover:opacity-100"
      >
        ×
      </button>
    </div>
  );
}
