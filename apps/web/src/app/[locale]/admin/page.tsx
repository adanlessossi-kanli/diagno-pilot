'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import { useTranslations, useLocale } from 'next-intl';
import { useRouter } from 'next/navigation';
import { createApiClient } from '@diagno-pilot/api-client';
import { useAuth } from '../../../contexts/AuthContext';

// ─── Types ────────────────────────────────────────────────────────────────────

interface AdminUser {
  id: string;
  fullName: string;
  email: string;
  role: string;
  isActive: boolean;
}

interface AdminStats {
  total_patients: number;
  total_consultations: number;
  total_documents: number;
  active_users: number;
}

interface AuditEntry {
  id: string;
  timestamp: string;
  actorEmail: string;
  action: string;
  resource: string;
  resourceId?: string | null;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleString('fr-FR');
}

// ─── Section 1: User Management ───────────────────────────────────────────────

const ROLES = ['admin', 'medecin', 'infirmière', 'guest'] as const;

function UserManagementSection({
  apiBase,
  currentUserId,
}: {
  apiBase: string;
  currentUserId: string;
}) {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [actionError, setActionError] = useState('');

  const fetchUsers = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await fetch(`${apiBase}/api/v1/admin/users`, {
        credentials: 'include',
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = (await res.json()) as AdminUser[];
      setUsers(data);
    } catch {
      setError('Erreur lors du chargement des utilisateurs.');
    } finally {
      setLoading(false);
    }
  }, [apiBase]);

  useEffect(() => { void fetchUsers(); }, [fetchUsers]);

  async function handleRoleChange(userId: string, role: string) {
    setActionError('');
    try {
      const res = await fetch(`${apiBase}/api/v1/admin/users/${userId}/role`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ role }),
      });
      if (!res.ok) {
        const body = (await res.json()) as { detail?: string };
        throw new Error(body.detail ?? `HTTP ${res.status}`);
      }
      const updated = (await res.json()) as AdminUser;
      setUsers((prev) => prev.map((u) => (u.id === userId ? { ...u, role: updated.role } : u)));
    } catch (err) {
      setActionError((err as Error).message);
    }
  }

  async function handleStatusToggle(userId: string, isActive: boolean) {
    setActionError('');
    try {
      const res = await fetch(`${apiBase}/api/v1/admin/users/${userId}/status`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ is_active: isActive }),
      });
      if (!res.ok) {
        const body = (await res.json()) as { detail?: string };
        throw new Error(body.detail ?? `HTTP ${res.status}`);
      }
      const updated = (await res.json()) as AdminUser;
      setUsers((prev) => prev.map((u) => (u.id === userId ? { ...u, isActive: updated.isActive } : u)));
    } catch (err) {
      setActionError((err as Error).message);
    }
  }

  return (
    <section className="border rounded-lg bg-white overflow-hidden">
      <div className="px-6 py-4 border-b">
        <h2 className="text-lg font-semibold">Gestion des utilisateurs</h2>
      </div>
      {actionError && (
        <div className="px-6 py-3">
          <p role="alert" className="text-sm text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2">
            {actionError}
          </p>
        </div>
      )}
      {loading && <p className="px-6 py-4 text-sm text-gray-500">Chargement…</p>}
      {!loading && error && (
        <p role="alert" className="px-6 py-4 text-sm text-red-600">{error}</p>
      )}
      {!loading && !error && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b">
              <tr>
                <th className="text-left px-4 py-3 font-medium text-gray-700">Nom</th>
                <th className="text-left px-4 py-3 font-medium text-gray-700">Email</th>
                <th className="text-left px-4 py-3 font-medium text-gray-700">Rôle</th>
                <th className="text-left px-4 py-3 font-medium text-gray-700">Statut</th>
                <th className="text-left px-4 py-3 font-medium text-gray-700">Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className="border-b last:border-0 hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3 text-gray-900">{u.fullName}</td>
                  <td className="px-4 py-3 text-gray-600">{u.email}</td>
                  <td className="px-4 py-3">
                    <select
                      value={u.role}
                      disabled={u.id === currentUserId}
                      onChange={(e) => void handleRoleChange(u.id, e.target.value)}
                      className="border rounded px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {ROLES.map((r) => (
                        <option key={r} value={r}>{r}</option>
                      ))}
                    </select>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${u.isActive ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
                      {u.isActive ? 'Actif' : 'Inactif'}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <button
                      type="button"
                      disabled={u.id === currentUserId && u.isActive}
                      onClick={() => void handleStatusToggle(u.id, !u.isActive)}
                      className="text-sm font-medium text-blue-600 hover:text-blue-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                      {u.isActive ? 'Désactiver' : 'Activer'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

// ─── Section 2: Statistics Dashboard ─────────────────────────────────────────

function StatCard({ label, value }: { label: string; value: number | undefined }) {
  return (
    <div className="border rounded-lg bg-white p-6 flex flex-col gap-2">
      <span className="text-sm text-gray-500">{label}</span>
      <span className="text-3xl font-bold text-blue-600">
        {value !== undefined ? value.toLocaleString('fr-FR') : '—'}
      </span>
    </div>
  );
}

function StatsDashboardSection({ apiBase }: { apiBase: string }) {
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    async function fetchStats() {
      setLoading(true);
      setError('');
      try {
        const res = await fetch(`${apiBase}/api/v1/admin/stats`, { credentials: 'include' });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = (await res.json()) as AdminStats;
        setStats(data);
      } catch {
        setError('Erreur lors du chargement des statistiques.');
      } finally {
        setLoading(false);
      }
    }
    void fetchStats();
  }, [apiBase]);

  return (
    <section>
      <h2 className="text-lg font-semibold mb-4">Tableau de bord statistiques</h2>
      {loading && <p className="text-sm text-gray-500">Chargement…</p>}
      {!loading && error && (
        <p role="alert" className="text-sm text-red-600">{error}</p>
      )}
      {!loading && !error && stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard label="Patients" value={stats.total_patients} />
          <StatCard label="Consultations" value={stats.total_consultations} />
          <StatCard label="Documents" value={stats.total_documents} />
          <StatCard label="Utilisateurs actifs" value={stats.active_users} />
        </div>
      )}
    </section>
  );
}

// ─── Section 3: Audit Log ─────────────────────────────────────────────────────

function AuditLogSection({ apiBase }: { apiBase: string }) {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    async function fetchAudit() {
      setLoading(true);
      setError('');
      try {
        const res = await fetch(`${apiBase}/api/v1/audit?page=1&page_size=50`, {
          credentials: 'include',
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = (await res.json()) as { items: AuditEntry[] };
        setEntries(data.items);
      } catch {
        setError("Erreur lors du chargement du journal d'audit.");
      } finally {
        setLoading(false);
      }
    }
    void fetchAudit();
  }, [apiBase]);

  return (
    <section className="border rounded-lg bg-white overflow-hidden">
      <div className="px-6 py-4 border-b">
        <h2 className="text-lg font-semibold">Journal d&apos;audit</h2>
      </div>
      {loading && <p className="px-6 py-4 text-sm text-gray-500">Chargement…</p>}
      {!loading && error && (
        <p role="alert" className="px-6 py-4 text-sm text-red-600">{error}</p>
      )}
      {!loading && !error && entries.length === 0 && (
        <p className="px-6 py-4 text-sm text-gray-500">Aucune entrée d&apos;audit.</p>
      )}
      {!loading && !error && entries.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b">
              <tr>
                <th className="text-left px-4 py-3 font-medium text-gray-700">Horodatage</th>
                <th className="text-left px-4 py-3 font-medium text-gray-700">Acteur</th>
                <th className="text-left px-4 py-3 font-medium text-gray-700">Action</th>
                <th className="text-left px-4 py-3 font-medium text-gray-700">Ressource</th>
                <th className="text-left px-4 py-3 font-medium text-gray-700">ID ressource</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((entry) => (
                <tr key={entry.id} className="border-b last:border-0 hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3 text-gray-500 whitespace-nowrap">{formatTimestamp(entry.timestamp)}</td>
                  <td className="px-4 py-3 text-gray-600">{entry.actorEmail}</td>
                  <td className="px-4 py-3 text-gray-900 font-mono text-xs">{entry.action}</td>
                  <td className="px-4 py-3 text-gray-600">{entry.resource}</td>
                  <td className="px-4 py-3 text-gray-400 font-mono text-xs">{entry.resourceId ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

// ─── Section 4: Create Doctor ─────────────────────────────────────────────────

function CreateDoctorSection({ apiBase }: { apiBase: string }) {
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState('');
  const [error, setError] = useState('');

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setSuccess('');
    setError('');
    try {
      const res = await fetch(`${apiBase}/api/v1/admin/users`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ email, password, full_name: fullName, role: 'medecin' }),
      });
      if (!res.ok) {
        const body = (await res.json()) as { detail?: string };
        throw new Error(body.detail ?? `HTTP ${res.status}`);
      }
      setSuccess('Compte médecin créé avec succès.');
      setFullName('');
      setEmail('');
      setPassword('');
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="border rounded-lg bg-white overflow-hidden">
      <div className="px-6 py-4 border-b">
        <h2 className="text-lg font-semibold">Créer un médecin</h2>
      </div>
      <form onSubmit={(e) => void handleSubmit(e)} className="px-6 py-4 space-y-4 max-w-md">
        <div>
          <label htmlFor="doctor-fullname" className="block text-sm font-medium text-gray-700 mb-1">
            Nom complet
          </label>
          <input
            id="doctor-fullname"
            type="text"
            required
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            className="w-full border rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            placeholder="Dr. Jean Dupont"
          />
        </div>
        <div>
          <label htmlFor="doctor-email" className="block text-sm font-medium text-gray-700 mb-1">
            Email
          </label>
          <input
            id="doctor-email"
            type="email"
            required
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full border rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            placeholder="medecin@exemple.com"
          />
        </div>
        <div>
          <label htmlFor="doctor-password" className="block text-sm font-medium text-gray-700 mb-1">
            Mot de passe
          </label>
          <input
            id="doctor-password"
            type="password"
            autoComplete="new-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full border rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            placeholder="••••••••"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Rôle</label>
          <input
            type="text"
            value="medecin"
            readOnly
            className="w-full border rounded px-3 py-2 text-sm bg-gray-50 text-gray-500 cursor-not-allowed"
          />
        </div>
        {success && (
          <p role="status" className="text-sm text-green-700 bg-green-50 border border-green-200 rounded px-3 py-2">
            {success}
          </p>
        )}
        {error && (
          <p role="alert" className="text-sm text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2">
            {error}
          </p>
        )}
        <button
          type="submit"
          disabled={submitting}
          className="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {submitting ? 'Création…' : 'Créer le compte médecin'}
        </button>
      </form>
    </section>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function AdminPanelPage() {
  const tCommon = useTranslations('common');
  const { user, isLoading: authLoading } = useAuth();
  const router = useRouter();
  const locale = useLocale();

  // Use createApiClient consistent with the rest of the app; derive base URL for admin fetch calls
  const apiBase = useMemo(() => {
    const baseUrl = process.env.NEXT_PUBLIC_API_URL ?? '';
    // Instantiate client to follow the same pattern as other pages; admin endpoints
    // are called via fetch directly since they are not yet in the typed client surface.
    createApiClient(baseUrl, undefined, () => locale);
    return baseUrl;
  }, [locale]);

  // RBAC guard — redirect non-admins to /
  useEffect(() => {
    if (!authLoading) {
      if (!user) {
        router.push('/login');
      } else if (user.role !== 'admin') {
        router.push('/');
      }
    }
  }, [authLoading, user, router]);

  // Loading auth
  if (authLoading) {
    return (
      <main className="min-h-screen p-8 flex items-center justify-center">
        <p className="text-gray-500">{tCommon('loading')}</p>
      </main>
    );
  }

  // Not admin — render nothing while redirect fires
  if (!user || user.role !== 'admin') {
    return (
      <main className="min-h-screen p-8 flex items-center justify-center">
        <p className="text-red-600">Accès refusé.</p>
      </main>
    );
  }

  return (
    <main className="min-h-screen p-8 max-w-6xl mx-auto space-y-10">
      <h1 className="text-2xl font-bold">Panneau d&apos;administration</h1>

      {/* Section 1 — User Management */}
      <UserManagementSection apiBase={apiBase} currentUserId={user.id} />

      {/* Section 2 — Statistics Dashboard */}
      <StatsDashboardSection apiBase={apiBase} />

      {/* Section 3 — Audit Log */}
      <AuditLogSection apiBase={apiBase} />

      {/* Section 4 — Create Doctor */}
      <CreateDoctorSection apiBase={apiBase} />
    </main>
  );
}
