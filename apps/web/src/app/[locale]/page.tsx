import { useTranslations } from 'next-intl';
import Image from 'next/image';
import { IMAGES } from '@/lib/images';

export default function HomePage() {
  const t = useTranslations('nav');

  return (
    <main className="min-h-screen p-8">
      {/* Hero image */}
      <div className="relative w-full h-64 mb-8 rounded-xl overflow-hidden bg-gray-100">
        <Image
          src={IMAGES.hero.src}
          alt={IMAGES.hero.alt}
          fill
          className="object-cover"
          priority
          sizes="(max-width: 768px) 100vw, 1200px"
        />
      </div>

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
