# Requirements Document

## Introduction

Ce document couvre les améliorations à apporter à **Diagno-Pilot**, application médicale d'aide au diagnostic des maladies infectieuses et à la prescription antibiotique, destinée aux professionnels de santé en Afrique de l'Ouest (Togo, Bénin). La stack est FastAPI + MongoDB + Next.js + React Native (Expo).

Les améliorations sont regroupées en cinq axes : Sécurité, Robustesse backend, UX/Frontend, Données médicales, et Observabilité.

---

## Glossaire

- **API** : Le backend FastAPI exposé sur `/api/v1`.
- **RateLimiter** : Composant middleware chargé de limiter le nombre de requêtes par IP et par utilisateur sur les endpoints sensibles.
- **CircuitBreaker** : Composant qui surveille les appels vers un service externe (LLM) et ouvre le circuit après un seuil d'échecs consécutifs pour éviter les cascades de pannes.
- **LLMRouter** : Service Python qui route les requêtes de génération vers MedicalQwen3 (primaire) puis GPT-5 (fallback).
- **DiagnosticService** : Service Python qui orchestre le diagnostic différentiel via RAGService.
- **PrescriptionService** : Service Python qui calcule les prescriptions antibiotiques adaptées au profil patient.
- **AlertService** : Service Python qui vérifie les alertes de sécurité (allergies, interactions, contre-indications).
- **AuthContext** : Contexte React (web et mobile) qui gère l'état d'authentification et le token JWT.
- **PatientProfile** : Modèle Pydantic représentant le profil complet d'un patient.
- **AgeGroup** : Énumération (`neonatal`, `infant`, `child`, `adult`) dérivée de la date de naissance.
- **StructuredLogger** : Composant de logging qui émet des entrées JSON structurées.
- **MetricsCollector** : Composant qui collecte et expose des métriques d'observabilité (latences, taux d'erreur, usage LLM).
- **FileValidator** : Composant qui valide les fichiers uploadés (taille, MIME type).
- **RefreshToken** : Token opaque à longue durée de vie permettant de renouveler un JWT expiré sans re-authentification.

---

## Requirements

### Requirement 1 : Restriction des origines CORS en production

**User Story :** En tant qu'administrateur système, je veux que les origines CORS autorisées soient explicitement configurées en production, afin d'empêcher des requêtes cross-origin non autorisées vers l'API.

#### Acceptance Criteria

1. WHEN l'API démarre avec `ALLOWED_ORIGINS="*"` et que la variable d'environnement `ENV` vaut `production`, THEN THE API SHALL rejeter le démarrage avec une erreur de configuration explicite.
2. THE API SHALL lire la liste des origines autorisées depuis la variable d'environnement `ALLOWED_ORIGINS` sous forme de chaîne séparée par des virgules.
3. WHEN `ALLOWED_ORIGINS` contient une liste d'origines explicites, THE API SHALL configurer le middleware CORS pour n'autoriser que ces origines.
4. IF `ALLOWED_ORIGINS` est absent ou vide en production, THEN THE API SHALL refuser de démarrer et journaliser un message d'erreur indiquant la variable manquante.

---

### Requirement 2 : Rate limiting sur les endpoints sensibles

**User Story :** En tant qu'administrateur système, je veux limiter le nombre de requêtes par IP et par utilisateur sur les endpoints `/diagnose` et `/chat`, afin de prévenir les abus et de protéger les ressources LLM coûteuses.

#### Acceptance Criteria

1. THE RateLimiter SHALL appliquer une limite de 30 requêtes par minute par utilisateur authentifié sur `POST /api/v1/diagnose/symptoms`.
2. THE RateLimiter SHALL appliquer une limite de 60 requêtes par minute par utilisateur authentifié sur `POST /api/v1/chat/message`.
3. WHEN un utilisateur dépasse la limite, THE API SHALL retourner une réponse HTTP 429 avec un en-tête `Retry-After` indiquant le nombre de secondes avant réinitialisation.
4. THE RateLimiter SHALL appliquer une limite de 10 requêtes par minute par adresse IP non authentifiée sur tous les endpoints publics.
5. IF le backend de stockage du RateLimiter est indisponible, THEN THE API SHALL laisser passer les requêtes et journaliser un avertissement, sans bloquer le service.

---

### Requirement 3 : Validation des fichiers uploadés

**User Story :** En tant qu'administrateur système, je veux que les fichiers uploadés soient validés avant traitement, afin d'éviter l'injection de fichiers malveillants ou surdimensionnés dans le système.

#### Acceptance Criteria

1. THE FileValidator SHALL rejeter tout fichier dont la taille dépasse 20 Mo avec une réponse HTTP 413.
2. THE FileValidator SHALL vérifier le MIME type réel du fichier (via inspection des magic bytes) et n'accepter que les types `application/pdf`, `image/jpeg`, `image/png`, `text/csv`, `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`.
3. WHEN le MIME type déclaré par le client diffère du MIME type détecté, THEN THE FileValidator SHALL rejeter le fichier avec une réponse HTTP 415 et un message d'erreur descriptif.
4. IF un fichier est rejeté, THEN THE API SHALL journaliser l'événement avec l'adresse IP de l'appelant, le nom du fichier, et la raison du rejet.
5. THE FileValidator SHALL valider le nom de fichier pour rejeter tout chemin contenant des séquences de traversée de répertoire (`../`, `..\\`).

---

### Requirement 4 : Refresh token JWT

**User Story :** En tant que professionnel de santé, je veux que ma session reste active sans avoir à me reconnecter toutes les 60 minutes, afin de ne pas interrompre mon flux de travail clinique.

#### Acceptance Criteria

1. WHEN un utilisateur s'authentifie avec succès, THE API SHALL retourner un access token JWT (durée de vie : 15 minutes) et un refresh token opaque (durée de vie : 7 jours).
2. THE API SHALL exposer un endpoint `POST /api/v1/auth/refresh` qui accepte un refresh token valide et retourne un nouveau access token JWT.
3. WHEN un refresh token est utilisé, THE API SHALL invalider l'ancien refresh token et en émettre un nouveau (rotation).
4. IF un refresh token expiré ou révoqué est présenté, THEN THE API SHALL retourner HTTP 401 avec le message `"refresh_token_invalid"`.
5. THE AuthContext SHALL détecter automatiquement une réponse HTTP 401 sur n'importe quel appel API et tenter un refresh silencieux avant de rediriger vers la page de login.
6. WHEN la page est rechargée, THE AuthContext SHALL restaurer la session en appelant `GET /api/v1/auth/me` avec le cookie httpOnly existant, sans nécessiter de re-saisie des identifiants.

---

### Requirement 5 : Circuit breaker sur le LLMRouter

**User Story :** En tant qu'administrateur système, je veux qu'un circuit breaker protège les appels vers les LLM, afin d'éviter les cascades de pannes et de réduire les temps d'attente lors d'une indisponibilité du modèle primaire.

#### Acceptance Criteria

1. THE CircuitBreaker SHALL surveiller les appels vers le LLM primaire (MedicalQwen3) et ouvrir le circuit après 5 échecs consécutifs dans une fenêtre de 60 secondes.
2. WHILE le circuit est ouvert, THE LLMRouter SHALL router directement vers le LLM fallback (GPT-5) sans tenter le LLM primaire.
3. THE CircuitBreaker SHALL tenter de refermer le circuit après une période de récupération de 120 secondes en laissant passer une requête de test.
4. WHEN le circuit passe à l'état ouvert, THE API SHALL journaliser un événement de niveau WARNING avec le nombre d'échecs et l'heure d'ouverture.
5. IF le LLM fallback est également indisponible alors que le circuit est ouvert, THEN THE API SHALL retourner HTTP 503 avec le message `"llm_unavailable"` et journaliser un événement de niveau CRITICAL.

---

### Requirement 6 : Validation des réponses LLM

**User Story :** En tant que professionnel de santé, je veux que les réponses du LLM soient validées avant d'être affichées, afin de garantir que les diagnostics retournés sont structurellement cohérents et exploitables.

#### Acceptance Criteria

1. WHEN le LLMRouter retourne une réponse, THE DiagnosticService SHALL valider que la réponse contient au moins 1 et au plus 10 diagnostics différentiels.
2. WHEN la réponse LLM ne peut pas être parsée en liste de `DifferentialDiagnosis`, THEN THE DiagnosticService SHALL journaliser la réponse brute et retourner HTTP 502 avec le message `"llm_response_invalid"`.
3. THE DiagnosticService SHALL valider que chaque `DifferentialDiagnosis` contient un champ `condition` non vide et un champ `probability` compris entre 0 et 1.
4. IF un champ `icd_code` est présent dans la réponse LLM, THEN THE DiagnosticService SHALL valider que sa valeur correspond au format ICD-10 (`[A-Z][0-9]{2}(\.[0-9]{1,4})?`).
5. THE DiagnosticService SHALL être instancié une seule fois au démarrage de l'application et partagé via l'injection de dépendances FastAPI, sans reconstruction à chaque requête.

---

### Requirement 7 : Persistance du token JWT après rechargement de page

**User Story :** En tant que professionnel de santé, je veux que ma session soit restaurée automatiquement après un rechargement de page, afin de ne pas perdre mon contexte de travail.

#### Acceptance Criteria

1. WHEN la page est rechargée, THE AuthContext SHALL appeler `GET /api/v1/auth/me` en utilisant le cookie httpOnly pour restaurer l'état utilisateur.
2. WHILE la vérification de session est en cours, THE AuthContext SHALL maintenir `isLoading` à `true` pour empêcher les redirections prématurées.
3. IF `GET /api/v1/auth/me` retourne HTTP 401, THEN THE AuthContext SHALL effacer le token en mémoire et rediriger vers la page de login.
4. THE AuthContext mobile (React Native / Expo) SHALL stocker le token dans `SecureStore` d'Expo et le restaurer au démarrage de l'application.

---

### Requirement 8 : Pagination de la liste des patients

**User Story :** En tant que professionnel de santé, je veux que la liste des patients soit paginée, afin de naviguer efficacement dans un grand nombre de dossiers sans dégradation des performances.

#### Acceptance Criteria

1. THE API SHALL accepter les paramètres de requête `page` (entier ≥ 1, défaut : 1) et `page_size` (entier entre 1 et 100, défaut : 20) sur `GET /api/v1/patients`.
2. THE API SHALL retourner un objet de réponse contenant `items` (liste de patients), `total` (nombre total de patients), `page` et `page_size`.
3. WHEN `page * page_size` dépasse `total`, THE API SHALL retourner une liste `items` vide sans erreur.
4. THE PatientsPage (web) SHALL afficher des contrôles de navigation (page précédente / suivante / numéros de page) et mettre à jour la liste sans rechargement complet de la page.
5. THE PatientsPage (web) SHALL afficher le nombre total de patients et la plage courante (ex. : « 21–40 sur 150 »).

---

### Requirement 9 : Feedback en temps réel sur les formulaires

**User Story :** En tant que professionnel de santé, je veux recevoir un retour visuel immédiat lors de la saisie dans les formulaires, afin de corriger les erreurs avant soumission et de réduire les allers-retours avec le serveur.

#### Acceptance Criteria

1. THE DiagnosePage SHALL valider en temps réel que le champ texte libre de symptômes contient au moins 3 caractères avant d'activer le bouton de soumission.
2. THE CreatePatientModal SHALL valider en temps réel que le champ `full_name` n'est pas vide et que `weight_kg`, si renseigné, est un nombre positif.
3. WHEN un champ obligatoire est vide au moment de la soumission, THE Form SHALL afficher un message d'erreur inline sous le champ concerné, sans effacer les autres champs.
4. WHEN une requête API est en cours, THE Form SHALL désactiver le bouton de soumission et afficher un indicateur de chargement.
5. WHEN une requête API réussit, THE Form SHALL afficher un message de confirmation visible pendant au moins 2 secondes avant de fermer ou réinitialiser le formulaire.

---

### Requirement 10 : Tests du mode mobile

**User Story :** En tant que développeur, je veux que les composants React Native critiques soient couverts par des tests automatisés, afin de détecter les régressions sur le mode mobile.

#### Acceptance Criteria

1. THE MobileSymptomInput SHALL être couvert par des tests unitaires vérifiant le rendu, la saisie de texte, et l'ajout de symptômes structurés.
2. THE MobilePatientCard SHALL être couvert par des tests unitaires vérifiant l'affichage du nom, de la date de naissance, et du groupe d'âge.
3. THE AuthContext mobile SHALL être couvert par des tests vérifiant la restauration de session depuis `SecureStore` au démarrage.
4. WHEN les tests mobiles sont exécutés, THE Test_Suite SHALL produire un rapport de couverture indiquant au moins 70% de couverture de branches sur les composants testés.

---

### Requirement 11 : Protocoles antibiotiques configurables

**User Story :** En tant qu'administrateur médical, je veux que les protocoles antibiotiques soient stockés en base de données et modifiables sans redéploiement, afin de mettre à jour les recommandations thérapeutiques selon les directives locales (PNLP Togo/Bénin).

#### Acceptance Criteria

1. THE API SHALL exposer un endpoint `GET /api/v1/admin/protocols` retournant la liste complète des protocoles antibiotiques stockés en MongoDB.
2. THE API SHALL exposer un endpoint `PUT /api/v1/admin/protocols/{name}` permettant à un utilisateur avec le rôle `admin` de mettre à jour un protocole existant.
3. THE API SHALL exposer un endpoint `POST /api/v1/admin/protocols` permettant à un utilisateur avec le rôle `admin` de créer un nouveau protocole.
4. WHEN un protocole est mis à jour ou créé, THE PrescriptionService SHALL utiliser la version en base de données en priorité sur les protocoles codés en dur.
5. IF un protocole demandé n'existe ni en base de données ni dans les protocoles codés en dur, THEN THE PrescriptionService SHALL retourner HTTP 422 avec le message `"unknown_antibiotic"`.
6. THE API SHALL journaliser toute modification de protocole dans le journal d'audit avec l'identifiant de l'utilisateur, l'action, et les valeurs avant/après.

---

### Requirement 12 : Base de données des interactions médicamenteuses

**User Story :** En tant que professionnel de santé, je veux que les interactions médicamenteuses soient vérifiées contre une base de données complète et maintenue, afin de détecter les risques non couverts par la liste statique actuelle.

#### Acceptance Criteria

1. THE AlertService SHALL charger les interactions médicamenteuses depuis une collection MongoDB `drug_interactions` au démarrage.
2. THE API SHALL exposer un endpoint `POST /api/v1/admin/drug-interactions` permettant à un utilisateur `admin` d'ajouter une nouvelle interaction.
3. WHEN une interaction est ajoutée, THE AlertService SHALL recharger sa liste d'interactions sans redémarrage du service.
4. THE AlertService SHALL vérifier les interactions de manière symétrique (A→B équivaut à B→A).
5. IF la collection `drug_interactions` est vide au démarrage, THEN THE AlertService SHALL charger les interactions codées en dur comme données de secours et journaliser un avertissement.

---

### Requirement 13 : Calcul automatique du groupe d'âge

**User Story :** En tant que professionnel de santé, je veux que le groupe d'âge du patient soit calculé automatiquement depuis sa date de naissance, afin d'éviter les erreurs de saisie manuelle qui pourraient conduire à des prescriptions inadaptées.

#### Acceptance Criteria

1. WHEN un `PatientProfile` est créé ou mis à jour avec une `date_of_birth`, THE PatientProfile SHALL calculer et stocker automatiquement le champ `age_group` selon les règles : 0–28 jours → `neonatal`, 29 jours–23 mois → `infant`, 2–17 ans → `child`, 18 ans et plus → `adult`.
2. IF `date_of_birth` est absent, THEN THE PatientProfile SHALL conserver la valeur `age_group` fournie explicitement, ou `null` si aucune n'est fournie.
3. WHEN `age_group` est calculé depuis `date_of_birth`, THE PatientProfile SHALL ignorer toute valeur `age_group` fournie explicitement dans la requête.
4. THE API SHALL recalculer `age_group` à chaque mise à jour du `PatientProfile` si `date_of_birth` est présent.
5. FOR ALL `PatientProfile` avec une `date_of_birth` valide, le calcul de `age_group` puis le recalcul depuis la même `date_of_birth` SHALL produire le même résultat (propriété d'idempotence).

---

### Requirement 14 : Logging structuré JSON

**User Story :** En tant qu'administrateur système, je veux que tous les logs de l'application soient émis au format JSON structuré, afin de faciliter leur ingestion par des outils d'agrégation (ex. : Loki, CloudWatch Logs).

#### Acceptance Criteria

1. THE StructuredLogger SHALL émettre chaque entrée de log sous forme d'un objet JSON sur une seule ligne, contenant au minimum les champs : `timestamp` (ISO 8601), `level`, `message`, `service`, `request_id`.
2. WHEN une requête HTTP est traitée, THE StructuredLogger SHALL inclure dans l'entrée de log les champs `method`, `path`, `status_code`, et `duration_ms`.
3. WHEN une exception non gérée est capturée, THE StructuredLogger SHALL inclure le champ `error` avec le type d'exception et le message, et le champ `stack_trace`.
4. THE StructuredLogger SHALL être configurable via la variable d'environnement `LOG_LEVEL` (valeurs acceptées : `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`).
5. IF `LOG_FORMAT` est défini à `text`, THEN THE StructuredLogger SHALL émettre des logs en texte brut pour faciliter le développement local.

---

### Requirement 15 : Navigation principale et menu persistant

**User Story :** En tant que professionnel de santé, je veux disposer d'un menu de navigation toujours visible sur toutes les pages, afin de passer rapidement d'une section à l'autre sans me perdre dans l'application.

#### Acceptance Criteria

1. THE NavBar SHALL être visible sur toutes les pages authentifiées (Diagnostic, Chat, Patients, Admin) en web et en mobile.
2. THE NavBar web SHALL afficher les liens : Accueil, Diagnostic, Chat, Patients, et Admin (uniquement pour le rôle `admin`), avec mise en évidence visuelle de la page active.
3. THE NavBar mobile SHALL utiliser une barre de navigation inférieure (bottom tab bar) avec icônes et libellés pour : Diagnostic, Chat, Patients, et Profil.
4. WHEN l'utilisateur navigue vers une page, THE NavBar SHALL mettre à jour l'indicateur de page active sans rechargement complet.
5. THE NavBar SHALL afficher le nom et le rôle de l'utilisateur connecté, ainsi qu'un bouton de déconnexion accessible en un clic.
6. THE NavBar web SHALL être responsive : sur mobile web, elle se transforme en menu hamburger avec drawer latéral.

---

### Requirement 16 : Images illustratives sur les pages principales

**User Story :** En tant que professionnel de santé, je veux que les pages principales de l'application soient illustrées avec des images médicales pertinentes et libres de droits, afin de rendre l'interface plus accueillante et professionnelle.

#### Acceptance Criteria

1. THE HomePage SHALL afficher une image hero illustrant un contexte médical africain (professionnel de santé, consultation), issue d'une source libre de droits (Unsplash, Pexels, ou similaire).
2. THE LoginPage SHALL afficher une image de fond ou latérale illustrant un contexte médical, avec un ratio d'aspect adapté aux écrans desktop et mobile.
3. THE DiagnosePage SHALL afficher une illustration contextuelle (ex. : stéthoscope, consultation) dans l'en-tête de section, de taille réduite pour ne pas gêner le flux de travail.
4. THE PatientsPage SHALL afficher une illustration dans l'état vide (aucun patient) guidant l'utilisateur vers la création du premier dossier.
5. WHEN une image ne peut pas être chargée, THE Page SHALL afficher un placeholder avec la même dimension pour éviter les sauts de mise en page (layout shift).
6. ALL images SHALL avoir un attribut `alt` descriptif pour l'accessibilité.
7. ALL images utilisées SHALL provenir de sources libres de droits (licence CC0, Unsplash, Pexels) et leurs URLs SHALL être documentées dans le code source.

---

### Requirement 17 : Design system et bonnes pratiques UI

**User Story :** En tant que professionnel de santé, je veux une interface cohérente, lisible et professionnelle sur toutes les pages, afin de réduire la charge cognitive lors de consultations médicales.

#### Acceptance Criteria

1. THE Application SHALL utiliser une palette de couleurs cohérente : bleu médical primaire (`#1D4ED8`), blanc fond, gris neutres, rouge pour les alertes critiques, orange pour les avertissements, vert pour les confirmations.
2. THE Application SHALL utiliser une typographie lisible : police sans-serif (Inter ou système), taille minimale 14px pour le corps de texte, 16px pour les labels de formulaire.
3. THE Application SHALL afficher des états de chargement (skeleton screens) sur toutes les listes et sections de données asynchrones, plutôt que des spinners bloquants.
4. THE Application SHALL afficher des états vides illustrés (empty states) avec un message d'action clair sur toutes les listes pouvant être vides (patients, consultations, résultats de diagnostic).
5. THE Application SHALL utiliser des composants de feedback toast/notification pour les actions réussies et les erreurs non bloquantes, positionnés en haut à droite de l'écran.
6. THE Application SHALL respecter un contraste de couleur minimum de 4.5:1 entre le texte et l'arrière-plan pour les éléments interactifs.
7. THE Application SHALL être entièrement navigable au clavier (focus visible, ordre de tabulation logique) sur la version web.

---

### Requirement 18 : Métriques d'observabilité (anciennement REQ-15)

**User Story :** En tant qu'administrateur système, je veux disposer de métriques sur les taux d'erreur LLM, les latences par endpoint, et l'usage par utilisateur, afin de surveiller la santé du système et d'optimiser les ressources.

#### Acceptance Criteria

1. THE MetricsCollector SHALL exposer un endpoint `GET /metrics` au format Prometheus (text/plain) contenant au minimum : `diagno_pilot_http_requests_total` (compteur par méthode, path, status), `diagno_pilot_http_request_duration_seconds` (histogramme par méthode, path), `diagno_pilot_llm_requests_total` (compteur par modèle et statut : success/error), `diagno_pilot_llm_duration_seconds` (histogramme par modèle).
2. THE MetricsCollector SHALL incrémenter `diagno_pilot_llm_requests_total{model="qwen3", status="error"}` à chaque échec du LLM primaire.
3. THE MetricsCollector SHALL incrémenter `diagno_pilot_llm_requests_total{model="gpt5", status="success"}` à chaque utilisation réussie du fallback.
4. WHEN le circuit breaker passe à l'état ouvert, THE MetricsCollector SHALL incrémenter le compteur `diagno_pilot_circuit_breaker_open_total{service="llm_primary"}`.
5. THE endpoint `/metrics` SHALL être protégé par authentification HTTP Basic ou par restriction d'accès à un réseau interne, et ne pas être exposé publiquement.
