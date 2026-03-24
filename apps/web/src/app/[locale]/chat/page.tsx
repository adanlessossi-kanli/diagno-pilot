import { useTranslations } from 'next-intl';

export default function ChatPage() {
  const t = useTranslations('nav');

  return (
    <main className="min-h-screen p-8">
      <h1 className="text-2xl font-bold mb-4">{t('chat')}</h1>
      <div className="flex flex-col h-[70vh] border rounded-lg overflow-hidden">
        <div className="flex-1 p-4 overflow-y-auto bg-gray-50">
          {/* Messages will be rendered here */}
        </div>
        <div className="border-t p-4 bg-white flex gap-2">
          <input
            type="text"
            className="flex-1 border rounded px-3 py-2"
            placeholder="Posez votre question..."
          />
          <button className="bg-primary-600 text-white px-4 py-2 rounded hover:bg-primary-700">
            Envoyer
          </button>
        </div>
      </div>
    </main>
  );
}
