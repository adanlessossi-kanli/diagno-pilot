'use client';

import { useState, useEffect, useMemo } from 'react';
import { useLocale } from 'next-intl';
import { useRouter } from 'next/navigation';
import { createApiClient } from '@diagno-pilot/api-client';
import { useAuth } from '../../../contexts/AuthContext';
import { DocumentChat } from '../../../components/DocumentChat';
import { DocumentSidebar } from '../../../components/DocumentSidebar';

// ─── Constants ────────────────────────────────────────────────────────────────

const ALLOWED_ROLES = ['admin', 'medecin', 'infirmière'];

// ─── Main page ────────────────────────────────────────────────────────────────

export default function DocumentsPage() {
  const { user, isLoading: authLoading } = useAuth();
  const router = useRouter();
  const locale = useLocale();

  const apiClient = useMemo(() => {
    const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? '';
    return createApiClient(baseUrl, undefined, () => locale);
  }, [locale]);

  // Mobile sidebar toggle
  const [sidebarOpen, setSidebarOpen] = useState(false);
  // Desktop sidebar collapsed state
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  // Access control — redirect unauthorized roles
  useEffect(() => {
    if (!authLoading && (!user || !ALLOWED_ROLES.includes(user.role))) {
      router.push(`/${locale}`);
    }
  }, [authLoading, user, router, locale]);

  // Loading auth
  if (authLoading) {
    return (
      <main className="min-h-screen flex items-center justify-center">
        <p className="text-gray-500">Loading…</p>
      </main>
    );
  }

  // Not authenticated or unauthorized — render nothing while redirect fires
  if (!user || !ALLOWED_ROLES.includes(user.role)) {
    return null;
  }

  return (
    <div className="flex h-screen">
      {/* Document Chat (center, includes SessionHistoryPanel internally) */}
      <DocumentChat apiClient={apiClient} isAuthenticated={!!user} />

      {/* Desktop sidebar toggle button */}
      <button
        className="hidden md:flex items-center justify-center w-6 shrink-0 border-l border-gray-200 bg-gray-50 hover:bg-gray-100 transition-colors cursor-pointer"
        onClick={() => setSidebarCollapsed((prev) => !prev)}
        aria-label={sidebarCollapsed ? 'Expand document sidebar' : 'Collapse document sidebar'}
        aria-expanded={!sidebarCollapsed}
      >
        <svg
          className={`w-4 h-4 text-gray-500 transition-transform duration-200 ${sidebarCollapsed ? 'rotate-180' : ''}`}
          fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
        </svg>
      </button>

      {/* Document Sidebar (right, desktop only, collapsible) */}
      {!sidebarCollapsed && (
        <aside className="hidden md:flex flex-col w-[320px] shrink-0 border-l overflow-y-auto overflow-x-hidden">
          <DocumentSidebar apiClient={apiClient} userRole={user.role} />
        </aside>
      )}

      {/* Mobile sidebar toggle button */}
      <button
        className="md:hidden fixed bottom-4 right-4 z-40 bg-blue-600 text-white p-3 rounded-full shadow-lg"
        onClick={() => setSidebarOpen(true)}
        aria-label="Toggle document sidebar"
      >
        ☰
      </button>

      {/* Mobile sidebar overlay */}
      {sidebarOpen && (
        <div className="fixed inset-0 z-50 md:hidden" onClick={() => setSidebarOpen(false)}>
          <div className="absolute inset-0 bg-black/30" />
          <aside
            className="absolute right-0 top-0 h-full w-[300px] bg-white shadow-lg overflow-y-auto overflow-x-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            <DocumentSidebar apiClient={apiClient} userRole={user.role} />
          </aside>
        </div>
      )}
    </div>
  );
}
