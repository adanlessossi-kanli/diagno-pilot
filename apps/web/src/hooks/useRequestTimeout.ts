import { useState, useRef, useCallback, useEffect } from 'react';

export interface UseRequestTimeoutOptions {
  warningMs?: number;
  abortMs?: number;
  onWarning?: () => void;
  onAbort?: () => void;
}

export function useRequestTimeout(options?: UseRequestTimeoutOptions) {
  const {
    warningMs = 15000,
    abortMs = 30000,
    onWarning,
    onAbort,
  } = options ?? {};

  const [isWarning, setIsWarning] = useState(false);
  const [isAborted, setIsAborted] = useState(false);

  const warningTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abortTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearTimer = useCallback(() => {
    if (warningTimerRef.current !== null) {
      clearTimeout(warningTimerRef.current);
      warningTimerRef.current = null;
    }
    if (abortTimerRef.current !== null) {
      clearTimeout(abortTimerRef.current);
      abortTimerRef.current = null;
    }
    setIsWarning(false);
    setIsAborted(false);
  }, []);

  const startTimer = useCallback(
    (controller: AbortController) => {
      clearTimer();

      warningTimerRef.current = setTimeout(() => {
        setIsWarning(true);
        onWarning?.();
      }, warningMs);

      abortTimerRef.current = setTimeout(() => {
        setIsAborted(true);
        controller.abort();
        onAbort?.();
      }, abortMs);
    },
    [clearTimer, warningMs, abortMs, onWarning, onAbort],
  );

  useEffect(() => {
    return () => {
      if (warningTimerRef.current !== null) {
        clearTimeout(warningTimerRef.current);
      }
      if (abortTimerRef.current !== null) {
        clearTimeout(abortTimerRef.current);
      }
    };
  }, []);

  return { startTimer, clearTimer, isWarning, isAborted };
}
