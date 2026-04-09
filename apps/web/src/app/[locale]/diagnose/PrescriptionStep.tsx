'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import type { Prescription, SafetyAlert } from '@diagno-pilot/types';
import type { PrescriptionResponse } from '@diagno-pilot/api-client';

// ─── Types ────────────────────────────────────────────────────────────────────

/** CamelCase diagnosis entry as returned by the API client after key normalization */
export interface DiagnosisEntry {
  condition: string;
  probability: number;
  icdCode?: string;
  concordantSymptoms: string[];
}

export interface PrescriptionStepProps {
  diagnoses: DiagnosisEntry[];
  antibiotics: string[];
  onGetPrescription: (antibiotic: string) => Promise<PrescriptionResponse>;
  onGetLLMPrescription: (condition: string) => Promise<string>;
}

// ─── Alert level helpers ──────────────────────────────────────────────────────

const alertLevelClasses: Record<string, string> = {
  critical: 'bg-red-50 border-l-4 border-red-600 text-red-900',
  warning: 'bg-amber-50 border-l-4 border-amber-500 text-amber-900',
  info: 'bg-blue-50 border-l-4 border-blue-500 text-blue-900',
};

const alertIcons: Record<string, string> = {
  critical: '🚨',
  warning: '⚠️',
  info: 'ℹ️',
};

// ─── Sub-components ───────────────────────────────────────────────────────────

function PrescriptionDetails({ prescription: rx }: { prescription: Prescription }) {
  const t = useTranslations('diagnose.prescriptionStep');

  return (
    <div className="border rounded-lg p-5 bg-white space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-lg font-bold text-gray-900">{rx.antibiotic}</h3>
        {rx.isCappedToAdultDose && (
          <span className="text-xs font-semibold bg-amber-100 text-amber-800 border border-amber-300 rounded-full px-3 py-0.5">
            ⚠ {t('cappedToAdultDose')}
          </span>
        )}
      </div>

      {/* Details grid */}
      <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
        <dt className="text-gray-500 font-medium">{t('dose')}</dt>
        <dd className="text-gray-900">
          {rx.doseMg} mg
          {rx.dosePerKg !== undefined && (
            <span className="text-gray-500 ml-1">({rx.dosePerKg} mg/kg)</span>
          )}
        </dd>

        <dt className="text-gray-500 font-medium">{t('frequency')}</dt>
        <dd className="text-gray-900">{rx.frequency}</dd>

        <dt className="text-gray-500 font-medium">{t('duration')}</dt>
        <dd className="text-gray-900">{t('durationDays', { days: rx.durationDays })}</dd>

        <dt className="text-gray-500 font-medium">{t('route')}</dt>
        <dd className="text-gray-900">{rx.route}</dd>
      </dl>
    </div>
  );
}

function AlertItem({ alert }: { alert: SafetyAlert }) {
  const t = useTranslations('diagnose.prescriptionStep');
  const classes = alertLevelClasses[alert.level] ?? alertLevelClasses.info;
  const icon = alertIcons[alert.level] ?? alertIcons.info;
  const typeLabel = t(`alertType.${alert.type}` as Parameters<typeof t>[0]);

  return (
    <div role="alert" aria-live={alert.level === 'critical' ? 'assertive' : 'polite'} className={`rounded px-4 py-3 ${classes}`}>
      <div className="flex gap-2 items-start">
        <span aria-hidden="true" className="text-base">{icon}</span>
        <div className="flex-1 min-w-0">
          <p className="text-xs font-semibold uppercase tracking-wide">
            {typeLabel}
            {alert.affectedDrug && (
              <span className="ml-2 font-bold normal-case">{alert.affectedDrug}</span>
            )}
          </p>
          <p className="mt-0.5 text-sm">{alert.message}</p>
        </div>
      </div>
    </div>
  );
}

// ─── Condition → recommended antibiotics mapping ──────────────────────────────

/** Maps condition keywords (lowercase) to recommended antibiotic protocol names.
 *  When a diagnosis matches, these antibiotics are shown first in the selector. */
const CONDITION_ANTIBIOTICS: Record<string, string[]> = {
  // Bacterial infections
  'pneumoni':       ['amoxicillin', 'amoxicillin-clavulanate', 'azithromycin', 'ceftriaxone'],
  'bronchit':       ['amoxicillin', 'azithromycin', 'doxycycline'],
  'otit':           ['amoxicillin', 'amoxicillin-clavulanate', 'azithromycin'],
  'sinusit':        ['amoxicillin', 'amoxicillin-clavulanate'],
  'angine':         ['amoxicillin', 'penicillin-v', 'azithromycin'],
  'pharyngit':      ['amoxicillin', 'penicillin-v', 'azithromycin'],
  'tonsill':        ['amoxicillin', 'penicillin-v', 'azithromycin'],
  // Tropical / West African
  'typho':          ['ciprofloxacin', 'ceftriaxone', 'azithromycin', 'cotrimoxazole'],
  'fièvre typhoïde':['ciprofloxacin', 'ceftriaxone', 'azithromycin'],
  'typhoid':        ['ciprofloxacin', 'ceftriaxone', 'azithromycin'],
  'méningit':       ['ceftriaxone', 'amoxicillin', 'gentamicin'],
  'meningit':       ['ceftriaxone', 'amoxicillin', 'gentamicin'],
  'dysenteri':      ['ciprofloxacin', 'azithromycin', 'cotrimoxazole'],
  'shigell':        ['ciprofloxacin', 'azithromycin', 'ceftriaxone'],
  'cholera':        ['doxycycline', 'azithromycin', 'ciprofloxacin'],
  'choléra':        ['doxycycline', 'azithromycin', 'ciprofloxacin'],
  // Urinary / GI
  'urinair':        ['ciprofloxacin', 'cotrimoxazole', 'amoxicillin-clavulanate', 'ceftriaxone'],
  'urinary':        ['ciprofloxacin', 'cotrimoxazole', 'amoxicillin-clavulanate', 'ceftriaxone'],
  'cystit':         ['ciprofloxacin', 'cotrimoxazole', 'amoxicillin-clavulanate'],
  'pyélonéphrit':   ['ceftriaxone', 'ciprofloxacin', 'gentamicin'],
  'pyelonephrit':   ['ceftriaxone', 'ciprofloxacin', 'gentamicin'],
  'gastro':         ['azithromycin', 'ciprofloxacin', 'metronidazole'],
  'diarrh':         ['azithromycin', 'ciprofloxacin', 'cotrimoxazole'],
  // Parasitic (antibiotics as adjunct)
  'amibiase':       ['metronidazole'],
  'amoebiasis':     ['metronidazole'],
  'giardia':        ['metronidazole'],
  // Skin / soft tissue
  'cellulite':      ['amoxicillin-clavulanate', 'ceftriaxone'],
  'cellulitis':     ['amoxicillin-clavulanate', 'ceftriaxone'],
  'abcès':          ['amoxicillin-clavulanate', 'metronidazole'],
  'abscess':        ['amoxicillin-clavulanate', 'metronidazole'],
  // Sepsis
  'sepsis':         ['ceftriaxone', 'gentamicin', 'metronidazole'],
  'septicémi':      ['ceftriaxone', 'gentamicin', 'metronidazole'],
};

/** Return recommended antibiotics for a condition, falling back to the full list. */
function getRecommendedAntibiotics(condition: string, allAntibiotics: string[]): { recommended: string[]; others: string[] } {
  const lower = condition.toLowerCase();
  for (const [keyword, recs] of Object.entries(CONDITION_ANTIBIOTICS)) {
    if (lower.includes(keyword)) {
      const available = recs.filter((r) => allAntibiotics.includes(r));
      if (available.length > 0) {
        const others = allAntibiotics.filter((a) => !available.includes(a));
        return { recommended: available, others };
      }
    }
  }
  return { recommended: [], others: allAntibiotics };
}

/** Check if a condition is known to need antibiotics. */
function needsAntibiotics(condition: string): boolean {
  const lower = condition.toLowerCase();
  return Object.keys(CONDITION_ANTIBIOTICS).some((kw) => lower.includes(kw));
}

// ─── Main component ───────────────────────────────────────────────────────────

export function PrescriptionStep({ diagnoses, antibiotics, onGetPrescription, onGetLLMPrescription }: PrescriptionStepProps) {
  const t = useTranslations('diagnose.prescriptionStep');
  const tCommon = useTranslations('common');

  const [selectedDiagnosisIndex, setSelectedDiagnosisIndex] = useState<number>(0);
  const selectedCondition = diagnoses[selectedDiagnosisIndex]?.condition ?? '';
  const isAntibioticCase = needsAntibiotics(selectedCondition);
  const { recommended, others } = getRecommendedAntibiotics(selectedCondition, antibiotics);
  const effectiveList = [...recommended, ...others];
  const [selectedAntibiotic, setSelectedAntibiotic] = useState<string>(effectiveList[0] ?? '');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [prescriptionData, setPrescriptionData] = useState<PrescriptionResponse | null>(null);
  const [llmPrescription, setLlmPrescription] = useState<string | null>(null);
  const [criticalConfirmed, setCriticalConfirmed] = useState(false);

  const criticalAlerts = prescriptionData?.alerts.filter((a) => a.level === 'critical') ?? [];
  const warningAlerts = prescriptionData?.alerts.filter((a) => a.level === 'warning') ?? [];
  const infoAlerts = prescriptionData?.alerts.filter((a) => a.level === 'info') ?? [];
  const hasCritical = criticalAlerts.length > 0;

  // Collect alternatives from critical alerts
  const alternatives = criticalAlerts
    .map((a) => (a as SafetyAlert & { alternative?: string }).alternative)
    .filter((alt): alt is string => Boolean(alt));

  async function handleGetPrescription() {
    setError('');
    setPrescriptionData(null);
    setLlmPrescription(null);
    setCriticalConfirmed(false);
    setLoading(true);
    try {
      if (isAntibioticCase) {
        const result = await onGetPrescription(selectedAntibiotic);
        setPrescriptionData(result);
      } else {
        const result = await onGetLLMPrescription(selectedCondition);
        setLlmPrescription(result);
      }
    } catch {
      setError(t('errorPrescription'));
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="border rounded-lg p-6 space-y-5">
      <h2 className="text-lg font-semibold">{t('title')}</h2>

      {/* Diagnosis selector */}
      <div className="space-y-2">
        <label className="block text-sm font-medium text-gray-700">{t('selectedDiagnosis')}</label>
        <select
          value={selectedDiagnosisIndex}
          onChange={(e) => {
            const newIndex = Number(e.target.value);
            setSelectedDiagnosisIndex(newIndex);
            const newCondition = diagnoses[newIndex]?.condition ?? '';
            const { recommended: newRec, others: newOthers } = getRecommendedAntibiotics(newCondition, antibiotics);
            const newList = [...newRec, ...newOthers];
            setSelectedAntibiotic(newList[0] ?? '');
            setPrescriptionData(null);
            setLlmPrescription(null);
            setCriticalConfirmed(false);
            setError('');
          }}
          className="w-full border rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          {diagnoses.map((diag, i) => (
            <option key={`${diag.condition}-${i}`} value={i}>
              {diag.condition}
              {diag.icdCode ? ` (${diag.icdCode})` : ''}
              {' — '}
              {Math.round(diag.probability * 100)}%
            </option>
          ))}
        </select>
      </div>

      {/* Antibiotic selector — only for bacterial conditions */}
      {isAntibioticCase && (
        <div className="space-y-2">
          <label className="block text-sm font-medium text-gray-700">{t('selectAntibiotic')}</label>
          <select
            value={selectedAntibiotic}
            onChange={(e) => {
              setSelectedAntibiotic(e.target.value);
              setPrescriptionData(null);
              setCriticalConfirmed(false);
              setError('');
            }}
            className="w-full border rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            {recommended.length > 0 && (
              <optgroup label={t('recommendedAntibiotics')}>
                {recommended.map((ab) => (
                  <option key={ab} value={ab}>★ {ab}</option>
                ))}
              </optgroup>
            )}
            {others.length > 0 && (
              <optgroup label={recommended.length > 0 ? t('otherAntibiotics') : ''}>
                {others.map((ab) => (
                  <option key={ab} value={ab}>{ab}</option>
                ))}
              </optgroup>
            )}
          </select>
        </div>
      )}

      {/* Non-antibiotic hint */}
      {!isAntibioticCase && (
        <div className="bg-blue-50 border border-blue-200 rounded px-4 py-3 text-sm text-blue-800">
          💊 {t('llmPrescriptionHint')}
        </div>
      )}

      {/* Get prescription button */}
      {!prescriptionData && !llmPrescription && (
        <button
          type="button"
          onClick={() => void handleGetPrescription()}
          disabled={loading || diagnoses.length === 0}
          className="w-full bg-blue-600 text-white px-4 py-2.5 rounded font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {loading ? tCommon('loading') : t('getPrescription')}
        </button>
      )}

      {/* Error */}
      {error && (
        <p role="alert" className="text-sm text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2">
          {error}
        </p>
      )}

      {/* LLM-generated treatment recommendation */}
      {llmPrescription && (
        <div className="space-y-3">
          <div className="border rounded-lg p-5 bg-white space-y-3">
            <h3 className="text-lg font-bold text-gray-900">{t('llmPrescriptionTitle')}</h3>
            <div className="text-sm text-gray-800 whitespace-pre-wrap leading-relaxed">
              {llmPrescription}
            </div>
          </div>
          <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-3 py-2">
            ⚠️ {t('llmPrescriptionDisclaimer')}
          </p>
          <button
            type="button"
            onClick={() => { setLlmPrescription(null); void handleGetPrescription(); }}
            disabled={loading}
            className="text-sm text-blue-600 hover:underline disabled:opacity-50"
          >
            {t('regenerate')}
          </button>
        </div>
      )}

      {/* Antibiotic prescription result */}
      {prescriptionData && (
        <div className="space-y-5">
          {/* Prescription details */}
          <PrescriptionDetails prescription={prescriptionData.prescription} />

          {/* ── Critical alerts block ── */}
          {hasCritical && (
            <div className="rounded-lg border-2 border-red-600 bg-red-50 p-4 space-y-3">
              <div className="flex items-center gap-2">
                <span className="text-xl" aria-hidden="true">🚨</span>
                <h3 className="font-bold text-red-800 text-base">{t('criticalAlertTitle')}</h3>
              </div>
              <p className="text-sm text-red-700">{t('criticalAlertDescription')}</p>

              <div className="space-y-2">
                {criticalAlerts.map((alert, i) => (
                  <AlertItem key={`critical-${alert.type}-${i}`} alert={alert} />
                ))}
              </div>

              {/* Therapeutic alternative */}
              {alternatives.length > 0 && (
                <div className="mt-3 rounded bg-white border border-red-200 p-3 space-y-1">
                  <p className="text-xs font-semibold text-red-700 uppercase tracking-wide">
                    {t('alternativeTitle')}
                  </p>
                  <ul className="list-disc list-inside space-y-0.5">
                    {alternatives.map((alt, i) => (
                      <li key={`alt-${alt}-${i}`} className="text-sm text-gray-800">{alt}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Explicit confirmation */}
              <label className="flex items-start gap-3 cursor-pointer mt-2">
                <input
                  type="checkbox"
                  checked={criticalConfirmed}
                  onChange={(e) => setCriticalConfirmed(e.target.checked)}
                  className="mt-0.5 h-4 w-4 rounded border-gray-300 text-red-600 focus:ring-red-500"
                  aria-label={t('confirmCriticalLabel')}
                />
                <span className="text-sm text-red-800 font-medium">{t('confirmCriticalLabel')}</span>
              </label>

              {criticalConfirmed && (
                <div className="rounded bg-green-50 border border-green-300 px-3 py-2 text-sm text-green-800 font-medium">
                  ✓ {t('confirmCriticalButton')}
                </div>
              )}
            </div>
          )}

          {/* ── Warning alerts ── */}
          {warningAlerts.length > 0 && (
            <div className="space-y-2">
              <h4 className="text-sm font-semibold text-amber-800">{t('warningAlertsTitle')}</h4>
              {warningAlerts.map((alert, i) => (
                <AlertItem key={`warning-${alert.type}-${i}`} alert={alert} />
              ))}
            </div>
          )}

          {/* ── Info alerts ── */}
          {infoAlerts.length > 0 && (
            <div className="space-y-2">
              <h4 className="text-sm font-semibold text-blue-800">{t('infoAlertsTitle')}</h4>
              {infoAlerts.map((alert, i) => (
                <AlertItem key={`info-${alert.type}-${i}`} alert={alert} />
              ))}
            </div>
          )}

          {/* No alerts */}
          {prescriptionData.alerts.length === 0 && (
            <p className="text-sm text-green-700 bg-green-50 border border-green-200 rounded px-3 py-2">
              ✓ {t('noAlerts')}
            </p>
          )}

          {/* LLM used */}
          {prescriptionData.llmUsed && (
            <p className="text-xs text-gray-400">{prescriptionData.llmUsed}</p>
          )}

          {/* Retry button */}
          <button
            type="button"
            onClick={() => void handleGetPrescription()}
            disabled={loading}
            className="text-sm text-blue-600 hover:underline disabled:opacity-50"
          >
            {t('getPrescription')}
          </button>
        </div>
      )}
    </section>
  );
}
