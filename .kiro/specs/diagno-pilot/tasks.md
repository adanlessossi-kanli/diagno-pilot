# Plan d'implémentation — Diagno-Pilot

## Vue d'ensemble

Implémentation incrémentale de l'application Diagno-Pilot : backend FastAPI (Python), frontend Next.js (TypeScript), application mobile React Native, dans un monorepo partagé. Chaque tâche s'appuie sur les précédentes et aboutit à un système entièrement câblé.

---

## Tâches

- [x] 1. Initialiser le monorepo et l'environnement de développement
  - Créer la structure de répertoires : `apps/web`, `apps/mobile`, `packages/ui`, `packages/api-client`, `packages/types`, `packages/i18n`, `backend/`
  - Configurer `package.json` racine avec workspaces (npm/yarn workspaces)
  - Créer `docker-compose.yml` avec les services `frontend`, `backend`, `mongo` (mongodb-atlas-local), `localstack`
  - Créer `backend/Dockerfile`, `apps/web/Dockerfile`, `scripts/localstack-init.sh`
  - Créer le fichier `.env` avec toutes les variables d'environnement requises
  - _Requirements : REQ-05 (S3/LocalStack), REQ-11 (monorepo)_

- [x] 2. Mettre en place les types partagés et le client API
  - [x] 2.1 Créer `packages/types/index.ts` avec tous les types TypeScript partagés
    - Définir `AgeGroup`, `AlertLevel`, `UserRole`, `Locale`, `PatientProfile`, `Consultation`, `ChatMessage`, `ChatSession`, `Prescription`, `SafetyAlert`, `DifferentialDiagnosis`, `DocumentSource`, `Symptom`
    - _Requirements : REQ-02, REQ-03, REQ-06, REQ-08, REQ-09_
  - [x] 2.2 Créer `packages/api-client/index.ts` avec les fonctions HTTP pour chaque endpoint
    - Implémenter les appels vers `/auth`, `/chat`, `/diagnose`, `/patients`, `/documents`, `/files`, `/alerts`
    - _Requirements : REQ-01 à REQ-09_
  - [x] 2.3 Écrire les tests unitaires pour les types et le client API
    - Tester la sérialisation/désérialisation des types
    - _Requirements : REQ-02, REQ-06_

- [x] 3. Initialiser le backend FastAPI et la couche base de données
  - [x] 3.1 Créer la structure du projet FastAPI (`backend/main.py`, `backend/routers/`, `backend/models/`, `backend/services/`, `backend/core/`)
    - Configurer FastAPI avec CORS, middleware de logging, gestion d'erreurs globale
    - Configurer la connexion MongoDB Atlas via `motor` (AsyncIOMotorClient)
    - _Requirements : REQ-01, REQ-10_
  - [x] 3.2 Créer les modèles Pydantic dans `backend/models/`
    - Implémenter `PatientProfile`, `Prescription`, `SafetyAlert`, `RAGResponse`, `AgeGroup`, `AlertLevel`, `Locale`, `Consultation`, `User`, `AuditLog`
    - _Requirements : REQ-02, REQ-03, REQ-06, REQ-08, REQ-09_
  - [x] 3.3 Écrire les tests de validation des modèles Pydantic
    - Tester les contraintes de validation (poids négatif, groupe d'âge, etc.)
    - _Requirements : REQ-06, REQ-08_

- [x] 4. Implémenter l'authentification et la gestion des rôles (REQ-01)
  - [x] 4.1 Créer `backend/routers/auth.py` avec les endpoints `POST /api/v1/auth/login`, `POST /api/v1/auth/logout`, `GET /api/v1/auth/me`
    - Implémenter le hachage de mot de passe (bcrypt), génération et validation JWT
    - Implémenter l'expiration de session par inactivité
    - _Requirements : REQ-01_
  - [x] 4.2 Créer le middleware de contrôle d'accès basé sur les rôles (`backend/core/auth.py`)
    - Implémenter les dépendances FastAPI `require_role(roles)` et `get_current_user`
    - Restreindre les routes admin aux utilisateurs avec rôle `admin`
    - _Requirements : REQ-01_
  - [x] 4.3 Écrire les tests unitaires pour l'authentification
    - Tester login valide/invalide, expiration JWT, contrôle d'accès par rôle
    - _Requirements : REQ-01_
  - [x] 4.4 Écrire le test de propriété pour l'authentification
    - **Propriété 1 : Tout token JWT généré est valide uniquement pour l'utilisateur émetteur et expire après la durée configurée**
    - **Valide : REQ-01**
    - _Requirements : REQ-01_

- [x] 5. Implémenter le service d'audit et de traçabilité (REQ-10)
  - [x] 5.1 Créer `backend/services/audit_service.py`
    - Implémenter `log_action(user_id, action, resource, resource_id, details, ip_address)`
    - Persister les logs dans la collection `audit_logs` MongoDB
    - _Requirements : REQ-10_
  - [x] 5.2 Intégrer le middleware d'audit dans les routes sensibles (auth, consultations, prescriptions, documents)
    - _Requirements : REQ-10_
  - [x] 5.3 Écrire le test de propriété pour l'audit
    - **Propriété 2 : Toute action sensible génère exactement un log d'audit avec utilisateur, action, ressource et horodatage**
    - **Valide : REQ-10**
    - _Requirements : REQ-10_

- [x] 6. Point de contrôle — Vérifier que tous les tests passent
  - S'assurer que les tests d'authentification et d'audit passent. Poser des questions à l'utilisateur si nécessaire.

- [x] 7. Implémenter la gestion des profils patients (REQ-06)
  - [x] 7.1 Créer `backend/routers/patients.py` avec les endpoints CRUD patients
    - Implémenter `GET /api/v1/patients`, `POST /api/v1/patients`, `GET /api/v1/patients/{id}`, `PUT /api/v1/patients/{id}`
    - _Requirements : REQ-06_
  - [x] 7.2 Créer `backend/services/patient_service.py`
    - Implémenter le calcul automatique du groupe d'âge (`neonatal` 0–28j, `infant` 1–23 mois, `child` 2–17 ans, `adult` 18+) à partir de `date_of_birth`
    - Persister et récupérer les profils dans la collection `patients` MongoDB
    - _Requirements : REQ-06, REQ-08_
  - [x] 7.3 Écrire le test de propriété pour le calcul du groupe d'âge
    - **Propriété 3 : Pour tout `date_of_birth` valide, le groupe d'âge calculé correspond exactement aux tranches définies (néonatal 0–28j, nourrisson 1–23 mois, enfant 2–17 ans, adulte 18+)**
    - **Valide : REQ-06, REQ-08**
    - _Requirements : REQ-06, REQ-08_
  - [x] 7.4 Écrire les tests unitaires pour le service patient
    - Tester création, mise à jour, calcul d'âge aux limites de tranche
    - _Requirements : REQ-06_

- [x] 8. Implémenter le dossier patient, l'historique et les fichiers cliniques (REQ-07)
  - [x] 8.1 Créer les endpoints de consultations dans `backend/routers/patients.py`
    - Implémenter `GET /api/v1/patients/{id}/consultations`, `POST /api/v1/patients/{id}/consultations`
    - Gérer les consultations one-shot (sans `patient_id`)
    - _Requirements : REQ-07_
  - [x] 8.2 Créer `backend/services/s3_service.py` (classe `S3Service`)
    - Implémenter `upload(file, patient_id) -> str` et `get_presigned_url(key, expires_in) -> str`
    - Configurer le client boto3 avec `AWS_ENDPOINT_URL` pour LocalStack
    - _Requirements : REQ-07_
  - [x] 8.3 Créer `backend/routers/files.py` avec les endpoints `POST /api/v1/files/upload` et `GET /api/v1/files/{file_id}`
    - Persister les métadonnées dans la collection `patient_files` MongoDB
    - Retourner une URL présignée S3 pour l'accès aux fichiers
    - _Requirements : REQ-07_
  - [x] 8.4 Écrire les tests unitaires pour S3Service (avec mock LocalStack)
    - Tester upload, génération d'URL présignée, gestion d'erreurs
    - _Requirements : REQ-07_

- [x] 9. Implémenter la couche IA — LLMRouter, Embedding et RAGService (REQ-04, REQ-02)
  - [x] 9.1 Créer `backend/services/llm_router.py` (classe `LLMRouter`)
    - Implémenter `generate(prompt, context)` avec appel à MedicalQwen3 en priorité et fallback GPT-5 sur `LLMUnavailableError`
    - _Requirements : REQ-02, REQ-04_
  - [x] 9.2 Créer `backend/services/embedding_service.py` (classe `EmbeddingModel`)
    - Implémenter `encode(text) -> list[float]` via l'API d'embedding configurée
    - _Requirements : REQ-05_
  - [x] 9.3 Créer `backend/services/rag_service.py` (classe `RAGService`)
    - Implémenter `query(question, context, top_k)` : encode la requête → `$vectorSearch` MongoDB → génération LLM avec passages + sources
    - _Requirements : REQ-04, REQ-02_
  - [x] 9.4 Écrire le test de propriété pour le LLMRouter
    - **Propriété 4 : Si MedicalQwen3 lève `LLMUnavailableError`, le LLMRouter retourne toujours une réponse via GPT-5 (fallback)**
    - **Valide : REQ-04**
    - _Requirements : REQ-04_
  - [x] 9.5 Écrire les tests unitaires pour RAGService (avec mocks LLM et MongoDB)
    - Tester la construction du pipeline `$vectorSearch`, la citation des sources
    - _Requirements : REQ-04_

- [x] 10. Implémenter le service de diagnostic différentiel (REQ-02)
  - [x] 10.1 Créer `backend/services/diagnostic_service.py`
    - Implémenter `get_differential_diagnosis(symptoms, patient_profile)` : construit le prompt RAG avec profil patient, retourne ≥3 diagnostics avec score de probabilité et code CIM-10
    - _Requirements : REQ-02_
  - [x] 10.2 Créer `backend/routers/diagnose.py` avec `POST /api/v1/diagnose/symptoms` et `GET /api/v1/diagnose/session/{session_id}`
    - _Requirements : REQ-02_
  - [x] 10.3 Écrire le test de propriété pour le diagnostic différentiel
    - **Propriété 5 : Pour tout ensemble de symptômes valide, le service retourne au moins 3 diagnostics différentiels avec un score de probabilité entre 0 et 1**
    - **Valide : REQ-02**
    - _Requirements : REQ-02_

- [x] 11. Implémenter le service de prescription antibiotique et les alertes de sécurité (REQ-03, REQ-08, REQ-09)
  - [x] 11.1 Créer `backend/services/prescription_service.py`
    - Implémenter le calcul de dose au poids (mg/kg) pour les groupes pédiatriques
    - Implémenter le plafonnement à la dose adulte maximale (`is_capped_to_adult_dose`)
    - Implémenter les ajustements pour insuffisance rénale/hépatique
    - _Requirements : REQ-03, REQ-08_
  - [x] 11.2 Créer `backend/services/alert_service.py` (classe `AlertService`)
    - Implémenter `check_prescription(prescription, patient)` : vérifier allergies, interactions médicamenteuses, contre-indications par âge
    - Retourner des alertes `critical` (bloquantes) et `warning` avec alternative thérapeutique si critique
    - _Requirements : REQ-09_
  - [x] 11.3 Créer l'endpoint `POST /api/v1/diagnose/prescription` dans `backend/routers/diagnose.py`
    - Appeler `prescription_service` puis `alert_service`, retourner prescription + alertes
    - _Requirements : REQ-03, REQ-09_
  - [x] 11.4 Créer l'endpoint `GET /api/v1/alerts/check` dans `backend/routers/alerts.py`
    - _Requirements : REQ-09_
  - [x] 11.5 Écrire le test de propriété pour le calcul de dose pédiatrique
    - **Propriété 6 : Pour tout patient pédiatrique (non adulte) avec poids > 0, la dose calculée est toujours ≤ dose adulte maximale (`is_capped_to_adult_dose` = true si dépassement)**
    - **Valide : REQ-03, REQ-08**
    - _Requirements : REQ-03, REQ-08_
  - [x] 11.6 Écrire le test de propriété pour les alertes de sécurité
    - **Propriété 7 : Toute prescription contenant un antibiotique figurant dans les allergies connues du patient génère au minimum une alerte de niveau `critical`**
    - **Valide : REQ-09**
    - _Requirements : REQ-09_
  - [x] 11.7 Écrire les tests unitaires pour le service de prescription
    - Tester les cas limites : poids nul, plafonnement dose, ajustements rénaux/hépatiques
    - _Requirements : REQ-03, REQ-08_

- [x] 12. Point de contrôle — Vérifier que tous les tests backend passent
  - S'assurer que les tests de diagnostic, prescription et alertes passent. Poser des questions à l'utilisateur si nécessaire.

- [x] 13. Implémenter le service de chat RAG conversationnel (REQ-04)
  - [x] 13.1 Créer `backend/services/chat_service.py`
    - Implémenter la gestion de sessions multi-tours avec historique des messages
    - Appeler `RAGService.query()` avec contexte patient optionnel
    - _Requirements : REQ-04_
  - [x] 13.2 Créer `backend/routers/chat.py` avec `POST /api/v1/chat/message` et `GET /api/v1/chat/history/{session_id}`
    - _Requirements : REQ-04_
  - [x] 13.3 Écrire le test de propriété pour le chat RAG
    - **Propriété 8 : Toute réponse du chat RAG contient au moins une source citée (document + section)**
    - **Valide : REQ-04**
    - _Requirements : REQ-04_

- [x] 14. Implémenter la base de connaissances médicale — indexation documents (REQ-05)
  - [x] 14.1 Créer `backend/services/document_service.py`
    - Implémenter l'ingestion de fichiers PDF, DOCX, TXT, CSV : extraction texte → découpage en chunks → encodage en vecteurs → insertion dans `document_chunks` MongoDB
    - Stocker le fichier source sur S3 via `S3Service`
    - _Requirements : REQ-05_
  - [x] 14.2 Créer `backend/routers/documents.py` avec `POST /api/v1/documents/upload`, `GET /api/v1/documents`, `DELETE /api/v1/documents/{id}`
    - Restreindre les endpoints d'écriture au rôle `admin`
    - _Requirements : REQ-05, REQ-01_
  - [x] 14.3 Écrire les tests unitaires pour le service de documents
    - Tester le découpage en chunks, l'encodage, la suppression avec nettoyage S3
    - _Requirements : REQ-05_

- [x] 15. Mettre en place le frontend Next.js — structure et authentification (REQ-01, REQ-12)
  - [x] 15.1 Initialiser `apps/web` avec Next.js App Router et TypeScript
    - Configurer les routes : `/`, `/login`, `/chat`, `/diagnose`, `/patients`, `/patients/[id]`, `/admin`
    - Configurer `next-intl` ou `i18next` dans `packages/i18n` avec les fichiers de traduction FR/EN
    - _Requirements : REQ-12_
  - [x] 15.2 Créer la page `/login` et le contexte d'authentification (`AuthContext`)
    - Implémenter le formulaire de connexion, la gestion du token JWT en cookie httpOnly, la redirection selon le rôle
    - _Requirements : REQ-01_
  - [x] 15.3 Implémenter le sélecteur de langue dans l'interface (sans rechargement de page)
    - Détecter la langue depuis les préférences navigateur au premier chargement
    - _Requirements : REQ-12_
  - [x] 15.4 Écrire les tests unitaires pour le contexte d'authentification
    - Tester login, logout, persistance du token, redirection
    - _Requirements : REQ-01_

- [x] 16. Implémenter les composants partagés UI (REQ-11)
  - [x] 16.1 Créer `packages/ui` avec les composants React partagés web/mobile
    - Implémenter : `AlertBanner` (critical/warning/info), `PatientCard`, `SymptomInput`, `PrescriptionCard`, `SourceCitation`
    - _Requirements : REQ-09, REQ-02, REQ-03, REQ-04_
  - [x] 16.2 Écrire les tests unitaires pour les composants UI partagés
    - Tester le rendu des alertes critiques, l'affichage des sources
    - _Requirements : REQ-09, REQ-04_

- [ ] 17. Implémenter le mode guidé — diagnostic différentiel (frontend) (REQ-02)
  - [ ] 17.1 Créer la page `/diagnose` avec le formulaire de saisie des symptômes
    - Implémenter la saisie en texte libre et via liste structurée
    - Afficher les diagnostics différentiels avec score de probabilité et code CIM-10
    - _Requirements : REQ-02_
  - [ ] 17.2 Intégrer le profil patient dans le formulaire de diagnostic (sélection ou saisie one-shot)
    - _Requirements : REQ-02, REQ-06_

- [ ] 18. Implémenter le mode guidé — prescription et alertes (frontend) (REQ-03, REQ-09)
  - [ ] 18.1 Créer l'étape prescription dans la page `/diagnose`
    - Afficher la prescription (molécule, dose, fréquence, durée, voie)
    - Afficher les alertes de sécurité avec blocage sur alerte `critical` et confirmation explicite requise
    - Proposer une alternative thérapeutique en cas d'alerte critique
    - _Requirements : REQ-03, REQ-09_
  - [ ] 18.2 Écrire les tests unitaires pour le flux prescription/alertes
    - Tester le blocage sur alerte critique, l'affichage de l'alternative
    - _Requirements : REQ-09_

- [ ] 19. Implémenter l'interface de chat Q&A (frontend) (REQ-04)
  - [ ] 19.1 Créer la page `/chat` avec l'interface de conversation multi-tours
    - Afficher les messages utilisateur/assistant, les sources citées par réponse
    - Permettre l'attachement d'un contexte patient à la session
    - _Requirements : REQ-04_

- [ ] 20. Implémenter la gestion des patients et du dossier patient (frontend) (REQ-06, REQ-07)
  - [ ] 20.1 Créer la page `/patients` avec la liste des patients et le formulaire de création
    - _Requirements : REQ-06_
  - [ ] 20.2 Créer la page `/patients/[id]` avec le dossier patient
    - Afficher l'historique des consultations (date, symptômes, diagnostic, prescription)
    - Implémenter l'upload de fichiers cliniques (résultats labo, imagerie, PDF, CSV) vers S3
    - Afficher les fichiers avec lien de téléchargement via URL présignée
    - _Requirements : REQ-07_

- [ ] 21. Implémenter la page d'administration (frontend) (REQ-05, REQ-10)
  - [ ] 21.1 Créer la page `/admin` (accès restreint rôle `admin`)
    - Afficher la liste des documents indexés avec statut et bouton de suppression
    - Implémenter le formulaire d'upload de nouveaux documents médicaux
    - _Requirements : REQ-05_

- [ ] 22. Point de contrôle — Vérifier que tous les tests frontend passent
  - S'assurer que les tests des composants et des pages passent. Poser des questions à l'utilisateur si nécessaire.

- [ ] 23. Implémenter l'application mobile React Native (REQ-11)
  - [ ] 23.1 Initialiser `apps/mobile` avec Expo et TypeScript
    - Configurer la navigation native (React Navigation)
    - Réutiliser `packages/types`, `packages/api-client`, `packages/i18n`
    - _Requirements : REQ-11_
  - [ ] 23.2 Implémenter les écrans mobiles : mode guidé, chat Q&A, dossier patient
    - Réutiliser les composants de `packages/ui` adaptés mobile
    - _Requirements : REQ-11_
  - [ ] 23.3 Adapter les composants `packages/ui` pour React Native (StyleSheet vs CSS)
    - _Requirements : REQ-11_

- [ ] 24. Câblage final et intégration
  - [ ] 24.1 Connecter tous les routers FastAPI dans `backend/main.py`
    - Enregistrer les routers : auth, chat, diagnose, patients, documents, files, alerts
    - Vérifier que le middleware d'audit est actif sur toutes les routes sensibles
    - _Requirements : REQ-01, REQ-10_
  - [ ] 24.2 Vérifier l'intégration end-to-end du flux RAG (symptômes → diagnostic → prescription → alertes)
    - Écrire des tests d'intégration automatisés couvrant le flux complet
    - _Requirements : REQ-02, REQ-03, REQ-04, REQ-09_
  - [ ] 24.3 Écrire les tests d'intégration pour le flux complet
    - Tester le flux : login → saisie symptômes → diagnostic → prescription → alerte → audit log
    - _Requirements : REQ-01, REQ-02, REQ-03, REQ-09, REQ-10_

- [ ] 25. Point de contrôle final — Vérifier que tous les tests passent
  - S'assurer que l'ensemble des tests unitaires, de propriété et d'intégration passent. Poser des questions à l'utilisateur si nécessaire.

---

## Notes

- Les tâches marquées `*` sont optionnelles et peuvent être ignorées pour un MVP rapide
- Chaque tâche référence les requirements correspondants pour la traçabilité
- Les tests de propriété valident des invariants universels (ex. : calcul de dose, fallback LLM, audit)
- Les tests unitaires valident des cas spécifiques et les cas limites
- Les points de contrôle permettent une validation incrémentale à chaque étape majeure
