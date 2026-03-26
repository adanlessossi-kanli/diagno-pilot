import type { Metadata } from 'next';
import { NextIntlClientProvider } from 'next-intl';
import { getMessages } from 'next-intl/server';
import { notFound } from 'next/navigation';
import { routing } from '../../i18n/routing';
import { AuthProvider } from '../../contexts/AuthContext';
import NavBar from '../../components/NavBar';
import Footer from '../../components/Footer';
import '../globals.css';

export const metadata: Metadata = {
  title: 'Diagno-Pilot',
  description: "Application d'aide au diagnostic des maladies infectieuses",
};

interface LocaleLayoutProps {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
}

export default async function LocaleLayout({ children, params }: LocaleLayoutProps) {
  const { locale } = await params;

  // Validate locale
  if (!routing.locales.includes(locale as 'fr' | 'en')) {
    notFound();
  }

  const messages = await getMessages();

  return (
    <html lang={locale}>
      <body className="font-sans bg-gray-50">
        <NextIntlClientProvider messages={messages}>
          <AuthProvider locale={locale}>
            <NavBar locale={locale} />
            <div className="max-w-[1280px] mx-auto px-4 pt-6">
              <main>{children}</main>
            </div>
            <Footer />
          </AuthProvider>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
