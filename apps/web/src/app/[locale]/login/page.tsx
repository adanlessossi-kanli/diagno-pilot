'use client';

import { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import Image from 'next/image';
import { useAuth } from '../../../contexts/AuthContext';
import { IMAGES } from '@/lib/images';
import DiagnoPilotLogo from '../../../components/DiagnoPilotLogo';

export default function LoginPage() {
  const t = useTranslations('auth');
  const tErrors = useTranslations('errors');
  const { login, user, isLoading } = useAuth();
  const router = useRouter();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Redirect if already authenticated
  useEffect(() => {
    if (!isLoading && user) {
      router.replace('..');
    }
  }, [user, isLoading, router]);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
    } catch (err) {
      const msg = (err as { message?: string })?.message;
      setError(msg && msg !== 'undefined' ? msg : tErrors('unauthorized'));
    } finally {
      setSubmitting(false);
    }
  }

  if (isLoading) {
    return null;
  }

  return (
    <main className="min-h-screen flex items-center justify-center bg-gray-50">
      {/* Side image — hidden on small screens */}
      <div className="hidden lg:block relative w-96 h-screen bg-gray-100 shrink-0">
        <Image
          src={IMAGES.loginSide.src}
          alt={IMAGES.loginSide.alt}
          fill
          className="object-cover"
          priority
          sizes="384px"
        />
      </div>

      <div className="w-full max-w-md p-8 bg-white rounded-xl shadow-md">
        <DiagnoPilotLogo size={40} className="mb-2" />
        <span className="text-primary-600 font-bold text-2xl">Diagno-Pilot</span>
        <h1 className="text-2xl font-bold mb-6">{t('login')}</h1>

        {error && (
          <div role="alert" aria-live="assertive" className="mb-4 border-l-4 border-error-border bg-error-bg px-4 py-3 text-sm text-error-text">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4" noValidate>
          <div>
            <label htmlFor="email" className="block text-sm font-medium text-gray-700">
              {t('email')}
            </label>
            <input
              id="email"
              name="email"
              type="email"
              autoComplete="email"
              required
              aria-required="true"
              value={email}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setEmail(e.target.value)}
              className="mt-1 block w-full rounded border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="medecin@hopital.tg"
            />
          </div>

          <div>
            <label htmlFor="password" className="block text-sm font-medium text-gray-700">
              {t('password')}
            </label>
            <input
              id="password"
              name="password"
              type="password"
              autoComplete="current-password"
              required
              aria-required="true"
              value={password}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setPassword(e.target.value)}
              className="mt-1 block w-full rounded border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <button
            type="submit"
            disabled={submitting}
            aria-busy={submitting}
            className={`w-full bg-primary-600 text-white hover:bg-primary-700 rounded-md px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed`}
          >
            {submitting ? '…' : t('submit')}
          </button>
        </form>
      </div>
    </main>
  );
}
