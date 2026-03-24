import { useTranslations } from 'next-intl';

export default function DiagnosePage() {
  const t = useTranslations('nav');

  return (
    <main className="min-h-screen p-8">
      <h1 className="text-2xl font-bold mb-4">{t('diagnose')}</h1>
      <div className="max-w-2xl space-y-6">
        <section className="border rounded-lg p-6">
          <h2 className="text-lg font-semibold mb-3">Symptômes</h2>
          <textarea
            className="w-full border rounded px-3 py-2 h-24"
            placeholder="Décrivez les symptômes du patient..."
          />
          <button className="mt-3 bg-primary-600 text-white px-4 py-2 rounded hover:bg-primary-700">
            Analyser
          </button>
        </section>
        {/* Differential diagnoses and prescription steps will be added here */}
      </div>
    </main>
  );
}
