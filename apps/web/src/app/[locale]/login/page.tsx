'use client';

import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import Image from 'next/image';
import { useLocale } from 'next-intl';
import { useAuth } from '../../../contexts/AuthContext';
import { IMAGES } from '@/lib/images';
import DiagnoPilotLogo from '../../../components/DiagnoPilotLogo';

export default function LoginPage() {
  const t = useTranslations('auth');
  const tErrors = useTranslations('errors');
  const { login, user, isLoading } = useAuth();
  const router = useRouter();
  const locale = useLocale();

  const [showPassword, setShowPassword] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const loginSchema = z.object({
    email: z
      .string()
      .min(1, t('emailRequired'))
      .email(t('emailInvalid')),
    password: z.string().min(1, t('passwordRequired')),
  });

  type LoginFormValues = z.infer<typeof loginSchema>;

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: '', password: '' },
  });

  // Redirect if already authenticated
  useEffect(() => {
    if (!isLoading && user) {
      router.replace('..');
    }
  }, [user, isLoading, router]);

  async function onSubmit(data: LoginFormValues) {
    setServerError(null);
    setSubmitting(true);
    try {
      await login(data.email, data.password);
    } catch (err) {
      const msg = (err as { message?: string })?.message;
      setServerError(msg && msg !== 'undefined' ? msg : tErrors('unauthorized'));
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

        {serverError && (
          <div role="alert" aria-live="assertive" className="mb-4 border-l-4 border-error-border bg-error-bg px-4 py-3 text-sm text-error-text">
            {serverError}
          </div>
        )}

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
          <div>
            <label htmlFor="email" className="block text-sm font-medium text-gray-700">
              {t('email')}
            </label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              aria-required="true"
              autoFocus
              aria-invalid={!!errors.email}
              aria-describedby={errors.email ? 'email-error' : undefined}
              {...register('email')}
              className="mt-1 block w-full rounded border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="medecin@hopital.tg"
            />
            {errors.email && (
              <p id="email-error" role="alert" className="mt-1 text-sm text-error-text">
                {errors.email.message}
              </p>
            )}
          </div>

          <div>
            <label htmlFor="password" className="block text-sm font-medium text-gray-700">
              {t('password')}
            </label>
            <div className="relative">
              <input
                id="password"
                type={showPassword ? 'text' : 'password'}
                autoComplete="current-password"
                aria-required="true"
                aria-invalid={!!errors.password}
                aria-describedby={errors.password ? 'password-error' : undefined}
                {...register('password')}
                className="mt-1 block w-full rounded border border-gray-300 px-3 py-2 pr-10 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <button
                type="button"
                onClick={() => setShowPassword((prev) => !prev)}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-700 p-1"
                aria-label={showPassword ? 'Hide password' : 'Show password'}
              >
                {showPassword ? (
                  /* Eye-off icon */
                  <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94" />
                    <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19" />
                    <line x1="1" y1="1" x2="23" y2="23" />
                    <path d="M14.12 14.12a3 3 0 1 1-4.24-4.24" />
                  </svg>
                ) : (
                  /* Eye icon */
                  <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                    <circle cx="12" cy="12" r="3" />
                  </svg>
                )}
              </button>
            </div>
            {errors.password && (
              <p id="password-error" role="alert" className="mt-1 text-sm text-error-text">
                {errors.password.message}
              </p>
            )}
          </div>

          <button
            type="submit"
            disabled={submitting}
            aria-busy={submitting}
            className="w-full bg-primary-600 text-white hover:bg-primary-700 rounded-md px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {submitting ? t('signingIn') : t('submit')}
          </button>
        </form>

        <div className="mt-3 text-center">
          <Link
            href={`/${locale}/forgot-password`}
            className="text-sm text-primary-600 hover:underline"
          >
            {t('forgotPassword')}
          </Link>
        </div>

        <p className="mt-4 text-center text-sm text-gray-600">
          {t('noAccount')}{' '}
          <Link href={`/${locale}/signup`} className="text-primary-600 hover:underline font-medium">
            {t('signupLink')}
          </Link>
        </p>
      </div>
    </main>
  );
}
