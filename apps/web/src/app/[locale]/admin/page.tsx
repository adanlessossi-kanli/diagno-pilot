import { useTranslations } from 'next-intl';

export default function AdminPage() {
  const t = useTranslations('nav');

  return (
    <main className="min-h-screen p-8">
      <h1 className="text-2xl font-bold mb-6">{t('admin')}</h1>
      <div className="space-y-8">
        <section className="border rounded-lg p-6">
          <h2 className="text-lg font-semibold mb-4">Documents médicaux</h2>
          <button className="bg-primary-600 text-white px-4 py-2 rounded hover:bg-primary-700 mb-4">
            Importer un document
          </button>
          <div className="border rounded overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b">
                <tr>
                  <th className="text-left px-4 py-3 font-medium">Titre</th>
                  <th className="text-left px-4 py-3 font-medium">Source</th>
                  <th className="text-left px-4 py-3 font-medium">Statut</th>
                  <th className="text-left px-4 py-3 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {/* Document rows will be rendered here */}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </main>
  );
}
