'use client';

import { useEffect, useCallback, useSyncExternalStore } from 'react';
import { useTranslations } from 'next-intl';

const HEALTH_CHECK_INTERVAL_MS = 30_000;
const MAX_CONSECUTIVE_FAILURES = 3;

// ── External store for navigator.onLine ───────────────────────────────────────

function subscribeOnlineStatus(callback: () => void) {
  window.addEventListener('online', callback);
  window.addEventListener('offline', callback);
  return () => {
    window.removeEventListener('online', callback);
    window.removeEventListener('offline', callback);
  };
}

function getOnlineSnapshot() {
  return navigator.onLine;
}

function getServerSnapshot() {
  return true;
}

// ── External store for health-check status ────────────────────────────────────

let _healthListeners: Array<() => void> = [];
let _healthFailed = false;
let _consecutiveFailures = 0;

function _notifyHealth() {
  for (const fn of _healthListeners) fn();
}

function subscribeHealthCheck(callback: () => void) {
  _healthListeners = [..._healthListeners, callback];
  return () => {
    _healthListeners = _healthListeners.filter((fn) => fn !== callback);
  };
}

function getHealthCheckSnapshot() {
  return _healthFailed;
}

function getHealthCheckServerSnapshot() {
  return false;
}

function resetHealthCheck() {
  _consecutiveFailures = 0;
  if (_healthFailed) {
    _healthFailed = false;
    _notifyHealth();
  }
}

function recordHealthSuccess() {
  _consecutiveFailures = 0;
  if (_healthFailed) {
    _healthFailed = false;
    _notifyHealth();
  }
}

function recordHealthFailure() {
  _consecutiveFailures += 1;
  if (_consecutiveFailures >= MAX_CONSECUTIVE_FAILURES && !_healthFailed) {
    _healthFailed = true;
    _notifyHealth();
  }
}

/** @internal — exposed for test cleanup */
export function _resetHealthCheckState() {
  _healthListeners = [];
  _healthFailed = false;
  _consecutiveFailures = 0;
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function OfflineBanner() {
  const t = useTranslations('errors');

  const isOnline = useSyncExternalStore(subscribeOnlineStatus, getOnlineSnapshot, getServerSnapshot);
  const isHealthFailed = useSyncExternalStore(subscribeHealthCheck, getHealthCheckSnapshot, getHealthCheckServerSnapshot);

  const checkHealth = useCallback(async () => {
    try {
      await fetch('/api/health', { method: 'HEAD', cache: 'no-store' });
      // Any response means the server is reachable
      recordHealthSuccess();
    } catch {
      // Network error — server truly unreachable
      recordHealthFailure();
    }
  }, []);

  // Reset health-check failures when browser comes back online
  useEffect(() => {
    const handleOnline = () => resetHealthCheck();
    window.addEventListener('online', handleOnline);
    return () => window.removeEventListener('online', handleOnline);
  }, []);

  // Periodic health check
  useEffect(() => {
    const timeout = setTimeout(checkHealth, 0);
    const interval = setInterval(checkHealth, HEALTH_CHECK_INTERVAL_MS);
    return () => {
      clearTimeout(timeout);
      clearInterval(interval);
    };
  }, [checkHealth]);

  if (!(!isOnline || isHealthFailed)) return null;

  return (
    <div
      role="alert"
      className="fixed top-0 left-0 right-0 z-50 bg-error-border text-white text-center text-sm font-medium py-2 px-4"
    >
      {t('offline')}
    </div>
  );
}
