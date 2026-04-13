'use client';

import { useState, useEffect } from 'react';
import { useTranslations, useLocale } from 'next-intl';
import { useRouter } from 'next/navigation';
import { useAuth } from '../../../contexts/AuthContext';

// ─── Create Nurse Form ────────────────────────────────────────────────────────

function CreateNurseForm() {
  const t = useTranslations('createNurse');
  const tCommon = useTranslations('common');
  const locale = useLocale();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fullName, setFullName] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setSuccess('');
    setSubmitting(true);
    try {
      const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? '';
      const res = await fetch(`${baseUrl}/api/v1/medecin/users`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password, fullName, role: 'infirmière' }),
      });
      if (!res.ok) {
        const data = (await res.json().catch(() => ({}))) as { detail?: string };
        setError(data.detail ?? t('errorCreate'));
      } else {
        setSuccess(t('successCreate'));
        setEmail('');
        setPassword('');
        setFullName('');
      }
    } catch {
      setError(t('errorCreate'));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="border rounded-xl shadow-sm p-6 bg-white max-w-md w-full">
      <h2 className="text-lg font-semibold mb-4">{t('formTitle')}</h2>

      <form onSubmit={(e) => void handleSubmit(e)} className="space-y-4">
        {/* Full name */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            {t('fullName')} <span className="text-red-500">*</span>
          </label>
          <input
            type="text"
            required
            autoFocus
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            className="w-full border rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        {/* Email */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            {t('email')} <span className="text-red-500">*</span>
          </label>
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full border rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        {/* Password */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            {t('password')} <span className="text-red-500">*</span>
          </label>
          <input
            type="password"
            autoComplete="new-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full border rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        {/* Feedback */}
        {error && (
          <p role="alert" className="text-sm text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2">
            {error}
          </p>
        )}
        {success && (
          <p role="status" className="text-sm text-green-700 bg-green-50 border border-green-200 rounded px-3 py-2">
            {success}
          </p>
        )}

        {/* Actions */}
        <div className="flex justify-end gap-3 pt-2">
          <a
            href={`/${locale}/patients`}
            className="px-4 py-2 text-sm font-medium text-gray-700 border border-gray-300 rounded hover:bg-gray-50 transition-colors"
          >
            {tCommon('cancel')}
          </a>
          <button
            type="submit"
            disabled={submitting}
            className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
          >
            {submitting && (
              <svg className="animate-spin h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
              </svg>
            )}
            {submitting ? tCommon('loading') : t('submit')}
          </button>
        </div>
      </form>
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function CreateNursePage() {
  const t = useTranslations('createNurse');
  const tCommon = useTranslations('common');
  const { user, isLoading: authLoading } = useAuth();
  const router = useRouter();
  const locale = useLocale();

  // Role guard: only medecin can access; others are redirected to home
  useEffect(() => {
    if (!authLoading && (!user || user.role !== 'medecin')) {
      router.push(`/${locale}`);
    }
  }, [authLoading, user, router, locale]);

  if (authLoading) {
    return (
      <main className="min-h-screen p-8 flex items-center justify-center">
        <p className="text-gray-500">{tCommon('loading')}</p>
      </main>
    );
  }

  if (!user || user.role !== 'medecin') {
    return null;
  }

  return (
    <main className="min-h-screen p-8 max-w-3xl mx-auto">
      <div className="mb-6">
        <a
          href={`/${locale}/patients`}
          className="text-sm text-blue-600 hover:underline"
        >
          ← Retour aux patients
        </a>
      </div>

      <h1 className="text-2xl font-bold mb-6">{t('pageTitle')}</h1>

      <CreateNurseForm />
    </main>
  );
}
