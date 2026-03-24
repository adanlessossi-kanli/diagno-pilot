interface PatientDetailPageProps {
  params: Promise<{ locale: string; id: string }>;
}

export default async function PatientDetailPage({ params }: PatientDetailPageProps) {
  const { id } = await params;

  return (
    <main className="min-h-screen p-8">
      <h1 className="text-2xl font-bold mb-6">Dossier patient</h1>
      <p className="text-gray-500 text-sm mb-6">ID : {id}</p>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <section className="md:col-span-1 border rounded-lg p-4">
          <h2 className="font-semibold mb-3">Informations</h2>
          {/* Patient info will be rendered here */}
        </section>
        <section className="md:col-span-2 border rounded-lg p-4">
          <h2 className="font-semibold mb-3">Historique des consultations</h2>
          {/* Consultation history will be rendered here */}
        </section>
      </div>
    </main>
  );
}
