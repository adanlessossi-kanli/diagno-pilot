# Plan d'implémentation : Diagno-Pilot Improvements

## Vue d'ensemble

Implémentation des 18 améliorations de Diagno-Pilot en cinq axes : Sécurité (REQ 1–4), Robustesse backend (REQ 5–6), UX/Frontend (REQ 7–10), Données médicales (REQ 11–13), Logging/UI/Observabilité (REQ 14–18). Stack : FastAPI (Python 3.12) + MongoDB + Next.js 15 + React Native Expo.

## Tâches

- [x] 1. Sécurité — Restriction CORS et configuration production
  - [x] 1.1 Ajouter le champ `ENV` et le validateur `validate_cors_in_production` dans `backend/core/config.py`
    - Ajouter `ENV: str = "development"` dans `Settings`
    - Implémenter `@model_validator(mode="after")` qui lève `ValueError` si `ENV=production` et `ALLOWED_ORIGINS` est `"*"` ou vide
    - Mettre à jour `main.py` pour parser `ALLOWED_ORIGINS` en liste et configurer le middleware CORS
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [x] 1.2 Écrire le test property-based P1 — CORS config invalide en production
    - **Property 1 : Configuration CORS invalide en production lève une erreur**
    - **Validates: Requirements 1.1, 1.4**
    - Fichier : `backend/tests/test_config.py`
    - Utiliser Hypothesis pour générer des combinaisons `ENV=production` + `ALLOWED_ORIGINS` invalides

  - [x] 1.3 Écrire le test property-based P2 — Round-trip parsing des origines CORS
    - **Property 2 : Round-trip parsing des origines CORS**
    - **Validates: Requirements 1.2**
    - Fichier : `backend/tests/test_config.py`
    - Vérifier que `",".join(origins)` puis parsing reproduit exactement la liste d'origine

- [x] 2. Sécurité — Rate limiting sur les endpoints sensibles
  - [x] 2.1 Créer `backend/core/rate_limit.py` avec `slowapi` et configurer les limites
    - Installer `slowapi` dans `requirements.txt`
    - Créer le `Limiter` avec `swallow_errors=True` et `RATE_LIMIT_STORAGE_URI` configurable
    - Ajouter `RATE_LIMIT_STORAGE_URI: str = "memory://"` dans `Settings`
    - Appliquer `@limiter.limit("30/minute")` sur `POST /diagnose/symptoms` (par user_id)
    - Appliquer `@limiter.limit("60/minute")` sur `POST /chat/message` (par user_id)
    - Appliquer `@limiter.limit("10/minute")` sur les endpoints publics (par IP)
    - Enregistrer le middleware `SlowAPIMiddleware` dans `main.py`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [x] 2.2 Écrire le test property-based P3 — Rate limiter retourne 429 avec Retry-After
    - **Property 3 : Rate limiter retourne 429 avec Retry-After au dépassement**
    - **Validates: Requirements 2.1, 2.2, 2.3**
    - Fichier : `backend/tests/test_rate_limit.py`
    - Utiliser Hypothesis pour générer des séquences de requêtes dépassant les limites

- [x] 3. Sécurité — Validation des fichiers uploadés
  - [x] 3.1 Créer `backend/core/file_validator.py` avec `FileValidator`
    - Installer `python-magic` dans `requirements.txt`
    - Implémenter la validation de taille (> 20 Mo → HTTP 413)
    - Implémenter la détection MIME via magic bytes et la liste blanche autorisée
    - Implémenter la validation du nom de fichier (regex `\.\.[/\\]` → HTTP 400)
    - Journaliser les rejets avec IP, nom de fichier, raison
    - Intégrer `FileValidator` dans le router `backend/routers/files.py`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 3.2 Écrire le test property-based P4 — FileValidator taille > 20 Mo
    - **Property 4 : FileValidator rejette tout fichier dépassant 20 Mo**
    - **Validates: Requirements 3.1**
    - Fichier : `backend/tests/test_file_validator.py`

  - [x] 3.3 Écrire le test property-based P5 — FileValidator MIME non autorisé
    - **Property 5 : FileValidator rejette les MIME types non autorisés**
    - **Validates: Requirements 3.2, 3.3**
    - Fichier : `backend/tests/test_file_validator.py`

  - [x] 3.4 Écrire le test property-based P6 — FileValidator traversée de répertoire
    - **Property 6 : FileValidator rejette les noms de fichier avec traversée de répertoire**
    - **Validates: Requirements 3.5**
    - Fichier : `backend/tests/test_file_validator.py`

- [x] 4. Sécurité — Refresh token JWT
  - [x] 4.1 Implémenter la collection `refresh_tokens` et les endpoints d'authentification
    - Créer le modèle Pydantic `RefreshToken` et le schéma MongoDB avec TTL index (7 jours)
    - Modifier `POST /api/v1/auth/login` pour retourner access token (15 min) + refresh token opaque (UUID)
    - Créer `POST /api/v1/auth/refresh` : valider le token, rotation (invalider l'ancien, émettre un nouveau), retourner un nouveau JWT
    - Retourner HTTP 401 `"refresh_token_invalid"` si token expiré ou révoqué
    - Mettre à jour `Settings` : `JWT_EXPIRE_MINUTES: int = 15`, `JWT_REFRESH_EXPIRE_DAYS: int = 7`
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [x] 4.2 Écrire le test property-based P7 — Rotation des refresh tokens
    - **Property 7 : Rotation des refresh tokens — l'ancien token est invalidé après usage**
    - **Validates: Requirements 4.3, 4.4**
    - Fichier : `backend/tests/test_auth.py`
    - Vérifier qu'une seconde utilisation du même token retourne HTTP 401

- [x] 5. Checkpoint — Sécurité
  - Vérifier que tous les tests de sécurité passent, demander à l'utilisateur si des questions se posent.

- [x] 6. Robustesse — Circuit breaker sur le LLMRouter
  - [x] 6.1 Créer `backend/core/circuit_breaker.py` avec la machine à états CLOSED/OPEN/HALF_OPEN
    - Implémenter `CircuitBreaker` avec `failure_threshold=5`, `recovery_timeout=120`
    - Implémenter `CircuitOpenError` levée quand le circuit est ouvert
    - Journaliser un WARNING quand le circuit passe à OPEN (nombre d'échecs, heure)
    - _Requirements: 5.1, 5.4_

  - [x] 6.2 Intégrer le `CircuitBreaker` dans `backend/services/llm_router.py`
    - Envelopper l'appel au LLM primaire dans `circuit_breaker.call()`
    - Si `CircuitOpenError` → router directement vers le fallback sans tenter le primaire
    - Si les deux LLM sont indisponibles → HTTP 503 `"llm_unavailable"` + log CRITICAL
    - _Requirements: 5.2, 5.5_

  - [x] 6.3 Écrire le test property-based P8 — Circuit breaker s'ouvre après N échecs
    - **Property 8 : Circuit breaker s'ouvre après N échecs consécutifs**
    - **Validates: Requirements 5.1, 5.2**
    - Fichier : `backend/tests/test_circuit_breaker.py`

  - [x] 6.4 Écrire le test property-based P9 — Circuit breaker passe en half-open
    - **Property 9 : Circuit breaker passe en half-open après la période de récupération**
    - **Validates: Requirements 5.3**
    - Fichier : `backend/tests/test_circuit_breaker.py`

- [x] 7. Robustesse — Validation des réponses LLM et singleton DiagnosticService
  - [x] 7.1 Ajouter `_validate_diagnoses()` dans `backend/services/diagnostic_service.py`
    - Valider 1 ≤ len(diagnoses) ≤ 10
    - Valider `condition` non vide et `probability` ∈ [0.0, 1.0] pour chaque item
    - Valider `icd_code` contre le regex `^[A-Z][0-9]{2}(\.[0-9]{1,4})?$` si présent
    - En cas d'échec → log de la réponse brute + `HTTPException(502, "llm_response_invalid")`
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [x] 7.2 Transformer `DiagnosticService` en singleton via `app.state` dans `main.py`
    - Instancier `DiagnosticService` une seule fois dans `lifespan()` et stocker dans `app.state.diagnostic_service`
    - Modifier la dépendance FastAPI dans `backend/routers/diagnose.py` pour lire depuis `request.app.state`
    - _Requirements: 6.5_

  - [x] 7.3 Écrire le test property-based P10 — Invariants structurels des diagnostics LLM
    - **Property 10 : Invariants structurels des diagnostics LLM**
    - **Validates: Requirements 6.1, 6.3, 6.4**
    - Fichier : `backend/tests/test_diagnostic_service.py`
    - Générer des listes de diagnostics avec Hypothesis et vérifier les invariants

- [x] 8. Checkpoint — Robustesse backend
  - Vérifier que tous les tests de robustesse passent, demander à l'utilisateur si des questions se posent.

- [x] 9. UX/Frontend — Persistance session JWT
  - [x] 9.1 Améliorer `apps/web/src/contexts/AuthContext.tsx` pour la persistance de session
    - Maintenir `isLoading=true` jusqu'à la résolution de `GET /api/v1/auth/me` au montage
    - Implémenter `fetchWithRefresh` : intercepter les 401, tenter `POST /auth/refresh` silencieux, rejouer la requête
    - Rediriger vers `/login` si le refresh échoue (token révoqué/expiré)
    - _Requirements: 4.5, 7.1, 7.2, 7.3_

  - [x] 9.2 Implémenter la persistance du token dans `apps/mobile/src/contexts/AuthContext.tsx`
    - Utiliser `expo-secure-store` pour stocker le token sous la clé `diagno_access_token`
    - Au démarrage, lire le token depuis `SecureStore`, appeler `/auth/me`, restaurer l'état utilisateur
    - _Requirements: 7.4_

  - [x] 9.3 Écrire les tests unitaires pour la restauration de session AuthContext mobile
    - Tester la restauration depuis `SecureStore` au démarrage
    - Tester le comportement si `SecureStore` est vide ou si `/auth/me` retourne 401
    - _Requirements: 10.3_

- [x] 10. UX/Frontend — Pagination de la liste des patients
  - [x] 10.1 Modifier `GET /api/v1/patients` pour supporter la pagination
    - Ajouter le modèle générique `PaginatedResponse[T]` dans `backend/models/common.py`
    - Accepter les query params `page` (≥ 1, défaut 1) et `page_size` (1–100, défaut 20)
    - Retourner `PaginatedResponse[PatientProfile]` avec `items`, `total`, `page`, `page_size`
    - Retourner `items=[]` sans erreur si `page * page_size > total`
    - _Requirements: 8.1, 8.2, 8.3_

  - [x] 10.2 Créer le composant `Pagination` dans `apps/web/src/components/Pagination.tsx`
    - Afficher les contrôles précédent/suivant/numéros de page
    - Synchroniser l'état `page` avec le query param URL (`?page=N`)
    - Afficher la plage courante (ex. : « 21–40 sur 150 »)
    - Mettre à jour la liste sans rechargement complet de la page
    - _Requirements: 8.4, 8.5_

  - [x] 10.3 Écrire le test property-based P11 — Pagination cohérence des métadonnées
    - **Property 11 : Pagination — cohérence des métadonnées de réponse**
    - **Validates: Requirements 8.1, 8.2, 8.3**
    - Fichier : `backend/tests/test_patients_router.py`

- [x] 11. UX/Frontend — Feedback en temps réel sur les formulaires
  - [x] 11.1 Intégrer `react-hook-form` + `zod` sur `DiagnosePage` et `CreatePatientModal`
    - Installer `react-hook-form` et `zod` dans `apps/web/package.json`
    - Valider en temps réel que le texte libre de symptômes contient ≥ 3 caractères (désactiver le bouton sinon)
    - Valider `full_name` non vide et `weight_kg` > 0 si renseigné dans `CreatePatientModal`
    - Afficher les messages d'erreur inline sous chaque champ sans effacer les autres champs
    - Désactiver le bouton de soumission et afficher un spinner pendant les requêtes API
    - Afficher un message de confirmation toast pendant ≥ 2 secondes après succès
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

  - [x] 11.2 Écrire le test property-based P12 — Validation texte libre de symptômes
    - **Property 12 : Validation formulaire — texte libre de symptômes**
    - **Validates: Requirements 9.1**
    - Fichier : `apps/web/src/app/[locale]/diagnose/__tests__/DiagnosePage.test.tsx`
    - Utiliser fast-check pour générer des chaînes de longueur < 3 et vérifier `disabled=true`

  - [x] 11.3 Écrire le test property-based P13 — Validation weight_kg
    - **Property 13 : Validation formulaire — weight_kg doit être positif**
    - **Validates: Requirements 9.2**
    - Fichier : `apps/web/src/components/__tests__/CreatePatientModal.test.tsx`
    - Utiliser fast-check pour générer des valeurs ≤ 0 et vérifier l'erreur inline

- [x] 12. UX/Frontend — Tests composants mobiles
  - [x] 12.1 Écrire les tests unitaires pour `MobileSymptomInput`
    - Tester le rendu, la saisie de texte, et l'ajout de symptômes structurés
    - Fichier : `apps/mobile/src/components/__tests__/MobileSymptomInput.test.tsx`
    - _Requirements: 10.1_

  - [x] 12.2 Écrire les tests unitaires pour `MobilePatientCard`
    - Tester l'affichage du nom, de la date de naissance, et du groupe d'âge
    - Fichier : `apps/mobile/src/components/__tests__/MobilePatientCard.test.tsx`
    - _Requirements: 10.2_

- [x] 13. Checkpoint — UX/Frontend
  - Vérifier que tous les tests frontend passent, demander à l'utilisateur si des questions se posent.

- [x] 14. Données médicales — Protocoles antibiotiques configurables
  - [x] 14.1 Créer le router `backend/routers/admin.py` avec les endpoints de gestion des protocoles
    - Implémenter `GET /api/v1/admin/protocols` (liste complète depuis MongoDB)
    - Implémenter `POST /api/v1/admin/protocols` (création, rôle `admin` requis)
    - Implémenter `PUT /api/v1/admin/protocols/{name}` (mise à jour, rôle `admin` requis)
    - Journaliser chaque modification dans le journal d'audit (user_id, action, valeurs avant/après)
    - Enregistrer le router dans `main.py`
    - _Requirements: 11.1, 11.2, 11.3, 11.6_

  - [x] 14.2 Modifier `PrescriptionService` pour charger les protocoles depuis MongoDB
    - Ajouter une méthode `load_protocols_from_db()` qui charge la collection `antibiotic_protocols`
    - Utiliser les valeurs DB en priorité sur `ANTIBIOTIC_PROTOCOLS` dict
    - Fallback sur le dict codé en dur si la collection est vide
    - Retourner HTTP 422 `"unknown_antibiotic"` si le protocole est absent des deux sources
    - Exposer une méthode `reload_protocols()` appelée après chaque PUT/POST admin
    - _Requirements: 11.4, 11.5_

  - [x] 14.3 Écrire le test property-based P14 — PrescriptionService priorité DB
    - **Property 14 : PrescriptionService utilise la version DB en priorité sur le dict codé en dur**
    - **Validates: Requirements 11.4**
    - Fichier : `backend/tests/test_prescription_service.py`

- [x] 15. Données médicales — Base de données des interactions médicamenteuses
  - [x] 15.1 Modifier `AlertService` pour charger les interactions depuis MongoDB
    - Ajouter une méthode `load_interactions_from_db()` qui charge la collection `drug_interactions`
    - Fallback sur `_DRUG_INTERACTIONS` codé en dur si la collection est vide + log WARNING
    - Exposer une méthode `reload_interactions()` pour rechargement à chaud
    - Vérifier la symétrie (A→B équivaut à B→A) lors de la vérification
    - _Requirements: 12.1, 12.3, 12.4, 12.5_

  - [x] 15.2 Ajouter l'endpoint `POST /api/v1/admin/drug-interactions` dans `backend/routers/admin.py`
    - Valider le payload (drug_a, drug_b, level, message)
    - Appeler `alert_service.reload_interactions()` après insertion
    - _Requirements: 12.2_

  - [x] 15.3 Écrire le test property-based P15 — Symétrie des interactions médicamenteuses
    - **Property 15 : Symétrie des interactions médicamenteuses**
    - **Validates: Requirements 12.4**
    - Fichier : `backend/tests/test_alert_service.py`

- [x] 16. Données médicales — Calcul automatique du groupe d'âge
  - [x] 16.1 Ajouter la fonction `_compute_age_group()` et le validateur dans `backend/models/patient.py`
    - Implémenter `_compute_age_group(dob: date) -> AgeGroup` avec les règles : 0–28 jours → `neonatal`, 29 jours–23 mois → `infant`, 2–17 ans → `child`, 18 ans+ → `adult`
    - Ajouter `@model_validator(mode="after")` dans `PatientProfile` et `PatientCreate`
    - Si `date_of_birth` présent : calculer `age_group` et ignorer la valeur fournie explicitement
    - Si `date_of_birth` absent : conserver `age_group` fourni ou `null`
    - Recalculer `age_group` à chaque mise à jour du profil patient dans le router
    - _Requirements: 13.1, 13.2, 13.3, 13.4_

  - [x] 16.2 Écrire le test property-based P16 — Calcul automatique de age_group
    - **Property 16 : Calcul automatique de age_group depuis date_of_birth**
    - **Validates: Requirements 13.1**
    - Fichier : `backend/tests/test_patient_model.py`
    - Utiliser Hypothesis pour générer des dates de naissance et vérifier le groupe d'âge

  - [x] 16.3 Écrire le test property-based P17 — Idempotence du calcul de age_group
    - **Property 17 : Idempotence du calcul de age_group**
    - **Validates: Requirements 13.5**
    - Fichier : `backend/tests/test_patient_model.py`

- [x] 17. Checkpoint — Données médicales
  - Vérifier que tous les tests de données médicales passent, demander à l'utilisateur si des questions se posent.

- [x] 18. Observabilité — Logging structuré JSON
  - [x] 18.1 Remplacer `logging.basicConfig` par `python-json-logger` dans `backend/main.py`
    - Installer `python-json-logger` dans `requirements.txt`
    - Créer `backend/core/logging_config.py` avec `StructuredLogger` configurable via `LOG_LEVEL` et `LOG_FORMAT`
    - Émettre chaque entrée JSON sur une seule ligne avec `timestamp` (ISO 8601), `level`, `message`, `service`, `request_id`
    - Enrichir le middleware HTTP existant avec `request_id` (UUID par requête), `method`, `path`, `status_code`, `duration_ms`
    - Inclure `error` + `stack_trace` pour les exceptions non gérées
    - Si `LOG_FORMAT=text` → émettre des logs en texte brut
    - Ajouter `LOG_LEVEL: str = "INFO"` et `LOG_FORMAT: str = "json"` dans `Settings`
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5_

  - [x] 18.2 Écrire le test property-based P18 — Structure JSON des entrées de log
    - **Property 18 : Structure JSON des entrées de log**
    - **Validates: Requirements 14.1, 14.2**
    - Fichier : `backend/tests/test_structured_logger.py`
    - Vérifier que chaque entrée est un JSON valide sur une ligne avec les champs requis

- [x] 19. UI — Navigation persistante et design system
  - [x] 19.1 Améliorer `apps/web/src/components/NavBar.tsx`
    - Ajouter l'indicateur de page active via `usePathname()` de Next.js
    - Afficher le nom et le rôle de l'utilisateur connecté
    - Implémenter le menu hamburger responsive (drawer latéral sur mobile web) via état `isOpen`
    - _Requirements: 15.1, 15.2, 15.4, 15.5, 15.6_

  - [x] 19.2 Ajouter l'onglet `Profil` dans `apps/mobile/app/(tabs)/_layout.tsx`
    - Créer `apps/mobile/app/(tabs)/profile.tsx` avec les infos utilisateur et le bouton de déconnexion
    - _Requirements: 15.3_

  - [x] 19.3 Créer les composants partagés du design system dans `apps/web/src/components/`
    - Créer `SkeletonLoader.tsx` — skeleton screens pour les listes async
    - Créer `EmptyState.tsx` — état vide illustré avec message d'action clair
    - Créer `Toast.tsx` — notifications non-bloquantes positionnées en haut à droite
    - Étendre `tailwind.config.ts` avec la palette médicale (`#1D4ED8`, rouge alertes, orange warnings, vert confirmations)
    - Appliquer `SkeletonLoader` sur toutes les listes async (patients, consultations, diagnostics)
    - Appliquer `EmptyState` sur toutes les listes pouvant être vides
    - _Requirements: 17.1, 17.2, 17.3, 17.4, 17.5, 17.6, 17.7_

- [x] 20. UI — Images libres de droits
  - [x] 20.1 Créer `apps/web/src/lib/images.ts` et intégrer les images sur les pages
    - Définir les URLs Unsplash documentées dans `IMAGES` (hero, login, diagnose, patients empty state)
    - Intégrer `next/image` sur `HomePage`, `LoginPage`, `DiagnosePage`, `PatientsPage`
    - Ajouter un placeholder de même dimension si l'image ne charge pas (éviter layout shift)
    - Ajouter un attribut `alt` descriptif sur toutes les images
    - _Requirements: 16.1, 16.2, 16.3, 16.4, 16.5, 16.6, 16.7_

  - [x] 20.2 Écrire le test property-based P20 — Attribut alt présent sur toutes les images
    - **Property 20 : Attribut alt présent sur toutes les images**
    - **Validates: Requirements 16.6**
    - Fichier : `apps/web/src/lib/__tests__/images.test.ts`
    - Vérifier que chaque entrée de `IMAGES` a un `alt` non vide associé

- [x] 21. Observabilité — Métriques Prometheus
  - [x] 21.1 Intégrer `prometheus-fastapi-instrumentator` et les métriques LLM custom
    - Installer `prometheus-fastapi-instrumentator` et `prometheus-client` dans `requirements.txt`
    - Configurer l'instrumentateur pour exposer `diagno_pilot_http_requests_total` et `diagno_pilot_http_request_duration_seconds`
    - Créer les métriques custom : `diagno_pilot_llm_requests_total` (Counter, labels: model, status) et `diagno_pilot_llm_duration_seconds` (Histogram, label: model)
    - Incrémenter `diagno_pilot_llm_requests_total{model="qwen3", status="error"}` à chaque échec LLM primaire
    - Incrémenter `diagno_pilot_llm_requests_total{model="gpt5", status="success"}` à chaque succès fallback
    - Incrémenter `diagno_pilot_circuit_breaker_open_total{service="llm_primary"}` quand le circuit s'ouvre
    - Protéger `GET /metrics` par HTTP Basic Auth via `METRICS_AUTH` (`user:password`)
    - Ajouter `METRICS_AUTH: str = ""` dans `Settings`
    - _Requirements: 18.1, 18.2, 18.3, 18.4, 18.5_

  - [x] 21.2 Écrire le test property-based P19 — Compteur de métriques LLM s'incrémente
    - **Property 19 : Compteur de métriques LLM s'incrémente à chaque échec**
    - **Validates: Requirements 18.2**
    - Fichier : `backend/tests/test_metrics.py`
    - Vérifier que le compteur s'incrémente exactement de 1 à chaque `LLMUnavailableError`

- [x] 22. Checkpoint final — Vérification complète
  - Vérifier que tous les tests passent (backend Python + frontend TypeScript), demander à l'utilisateur si des questions se posent.

## Notes

- Les tâches marquées `*` sont optionnelles et peuvent être ignorées pour un MVP rapide
- Chaque tâche référence les requirements spécifiques pour la traçabilité
- Les tests property-based utilisent **Hypothesis** (Python) et **fast-check** (TypeScript/React)
- Les tests unitaires et property-based sont complémentaires, pas redondants
- Les checkpoints permettent une validation incrémentale à chaque axe d'amélioration
