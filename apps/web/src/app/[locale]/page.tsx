import { useTranslations } from 'next-intl';

export default function HomePage() {
  const t = useTranslations('nav');

  return (
    <main className="min-h-screen p-8">
      <h1 className="text-3xl font-bold text-primary-700">Diagno-Pilot</h1>
      <nav className="mt-6 flex gap-4">
        <a href="chat" className="text-primary-600 hover:underline">{t('chat')}</a>
        <a href="diagnose" className="text-primary-600 hover:underline">{t('diagnose')}</a>
        <a href="patients" className="text-primary-600 hover:underline">{t('patients')}</a>
        <a href="admin" className="text-primary-600 hover:underline">{t('admin')}</a>
      </nav>
    </main>
  );
}
