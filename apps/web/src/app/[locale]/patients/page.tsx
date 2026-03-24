import { useTranslations } from 'next-intl';

export default function PatientsPage() {
  const t = useTranslations('nav');

  return (
    <main className="min-h-screen p-8">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">{t('patients')}</h1>
        <button className="bg-primary-600 text-white px-4 py-2 rounded hover:bg-primary-700">
          Nouveau patient
        </button>
      </div>
      <div className="border rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b">
            <tr>
              <th className="text-left px-4 py-3 font-medium">Nom</th>
              <th className="text-left px-4 py-3 font-medium">Date de naissance</th>
              <th className="text-left px-4 py-3 font-medium">Groupe d&apos;âge</th>
              <th className="text-left px-4 py-3 font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {/* Patient rows will be rendered here */}
          </tbody>
        </table>
      </div>
    </main>
  );
}
