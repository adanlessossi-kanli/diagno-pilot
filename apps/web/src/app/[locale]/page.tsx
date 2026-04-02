'use client';

import { useTranslations } from 'next-intl';
import { useParams } from 'next/navigation';
import Image from 'next/image';
import Link from 'next/link';
import { IMAGES } from '@/lib/images';

export default function HomePage() {
  const params = useParams();
  const locale = (params?.locale as string) ?? 'fr-TG';
  const t = useTranslations('home');

  return (
    <section className="relative min-h-screen flex flex-col items-center justify-center overflow-hidden">
      {/* Hero background image */}
      <Image
        src={IMAGES.hero.src}
        alt={IMAGES.hero.alt}
        fill
        className="object-cover"
        priority
      />

      {/* Dark overlay */}
      <div className="absolute inset-0 bg-black/40" aria-hidden="true" />

      {/* Content */}
      <div className="relative z-10 flex flex-col items-center text-center px-4">
        <h1 className="text-5xl font-bold text-white mb-4">Diagno-Pilot</h1>
        <p className="text-xl text-white/90 mb-8 max-w-xl">{t('tagline')}</p>
        <Link
          href={`/${locale}/chat`}
          className="px-8 py-3 bg-primary-600 hover:bg-primary-700 text-white font-semibold rounded-lg transition-colors"
        >
          {t('cta')}
        </Link>
      </div>
    </section>
  );
}
