# Requirements Document

## Introduction

Ce document décrit les exigences du contrôle d'accès basé sur les rôles (RBAC) pour l'application Diagno-Pilot. Le système doit supporter quatre rôles : `admin`, `medecin`, `infirmière` et `guest`. L'administrateur dispose d'un accès complet incluant la gestion des utilisateurs et les statistiques. Les autres rôles ont un accès restreint aux fonctionnalités médicales selon leur profil. Le menu d'administration est invisible pour les rôles non-admin. Cette fonctionnalité doit être introduite sans régression sur les comportements existants.

## Glossaire

- **RBAC_System** : Le système de contrôle d'accès basé sur les rôles de Diagno-Pilot
- **Admin** : Rôle disposant de tous les droits, incluant la gestion des utilisateurs et l'accès aux statistiques
- **Medecin** : Rôle médical avec accès au mode guidé, au chat, aux dossiers patients et aux prescriptions
- **Infirmière** : Rôle paramédical avec accès complet aux ressources médicales (patients, diagnostic, chat), identique au rôle `medecin`
- **Guest** : Rôle invité (anonyme, sans compte) avec accès exclusif à l'assistant QA, sans obligation de s'enregistrer
- **QA_Assistant** : Fonctionnalité d'assistant questions-réponses accessible via l'endpoint `/api/v1/qa` et la page `/qa`, ouverte aux utilisateurs non authentifiés
- **Menu_Admin** : Section de navigation donnant accès aux fonctionnalités d'administration (gestion utilisateurs, statistiques, protocoles)
- **Auth_Guard** : Composant ou middleware vérifiant le rôle de l'utilisateur avant d'autoriser l'accès à une ressource
- **UserRole** : Type énuméré représentant les rôles possibles d'un utilisateur dans le système
- **Permission** : Droit d'accès associé à un rôle pour une ressource ou une action donnée

---

## Requirements

### Requirement 1 : Définition des rôles

**User Story:** En tant qu'architecte système, je veux que les quatre rôles soient formellement définis dans le système, afin que toutes les couches de l'application puissent s'y référer de manière cohérente.

#### Acceptance Criteria

1. THE RBAC_System SHALL reconnaître exactement quatre rôles valides : `admin`, `medecin`, `infirmière` et `guest`
2. THE RBAC_System SHALL rejeter toute valeur de rôle qui n'appartient pas à l'ensemble `{admin, medecin, infirmière, guest}`
3. WHEN un utilisateur est créé sans rôle explicite, THE RBAC_System SHALL lui attribuer le rôle `guest` par défaut
4. THE RBAC_System SHALL exposer le rôle de l'utilisateur authentifié dans la réponse de l'endpoint `/api/v1/auth/me`
5. THE RBAC_System SHALL définir le rôle `guest` comme donnant accès exclusivement à l'assistant QA, sans nécessiter de compte ni d'authentification

---

### Requirement 2 : Contrôle d'accès backend par rôle

**User Story:** En tant que développeur backend, je veux que chaque endpoint soit protégé selon le rôle requis, afin qu'aucun utilisateur ne puisse accéder à des ressources au-delà de ses droits.

#### Acceptance Criteria

1. WHEN un utilisateur avec le rôle `admin` envoie une requête à un endpoint d'administration (`/api/v1/admin/*`), THE Auth_Guard SHALL autoriser la requête
2. WHEN un utilisateur avec un rôle autre que `admin` envoie une requête à un endpoint d'administration (`/api/v1/admin/*`), THE Auth_Guard SHALL retourner une réponse HTTP 403
3. WHEN un utilisateur authentifié (rôle `admin`, `medecin` ou `infirmière`) envoie une requête aux endpoints `/api/v1/patients`, `/api/v1/diagnose` ou `/api/v1/chat`, THE Auth_Guard SHALL autoriser la requête quelle que soit la méthode HTTP
4. WHEN un utilisateur avec le rôle `guest` envoie une requête à l'endpoint `/api/v1/qa`, THE Auth_Guard SHALL autoriser la requête sans exiger de token JWT
5. WHEN un utilisateur avec le rôle `guest` envoie une requête à tout endpoint autre que `/api/v1/qa`, THE Auth_Guard SHALL rediriger l'utilisateur vers la page de connexion
6. IF un token JWT ne contient pas de rôle valide, THEN THE Auth_Guard SHALL retourner une réponse HTTP 401

---

### Requirement 3 : Visibilité du menu d'administration

**User Story:** En tant qu'utilisateur non-admin, je veux que le menu d'administration ne soit pas visible dans l'interface, afin de ne pas être exposé à des fonctionnalités qui ne me sont pas accessibles.

#### Acceptance Criteria

1. WHILE l'utilisateur authentifié a le rôle `admin`, THE RBAC_System SHALL afficher le Menu_Admin dans la navigation
2. WHILE l'utilisateur authentifié a un rôle différent de `admin`, THE RBAC_System SHALL masquer le Menu_Admin dans la navigation
3. WHEN un utilisateur non-admin tente d'accéder directement à l'URL `/[locale]/admin`, THE RBAC_System SHALL rediriger l'utilisateur vers la page d'accueil
4. THE RBAC_System SHALL appliquer la vérification de visibilité du Menu_Admin côté client et côté serveur (middleware Next.js)

---

### Requirement 4 : Accès aux statistiques (admin uniquement)

**User Story:** En tant qu'administrateur, je veux accéder aux statistiques d'utilisation de l'application, afin de superviser l'activité et la santé du système.

#### Acceptance Criteria

1. WHEN un utilisateur avec le rôle `admin` accède à la section statistiques, THE RBAC_System SHALL afficher les données d'utilisation agrégées
2. WHEN un utilisateur avec un rôle autre que `admin` tente d'accéder à l'endpoint `/api/v1/admin/stats`, THE Auth_Guard SHALL retourner une réponse HTTP 403
3. THE RBAC_System SHALL journaliser dans le journal d'audit chaque accès aux statistiques avec l'identifiant de l'utilisateur, l'horodatage et l'adresse IP

---

### Requirement 5 : Gestion des utilisateurs (admin uniquement)

**User Story:** En tant qu'administrateur, je veux gérer les comptes utilisateurs (créer, modifier le rôle, désactiver), afin de contrôler qui accède à l'application et avec quels droits.

#### Acceptance Criteria

1. WHEN un utilisateur avec le rôle `admin` envoie une requête POST à `/api/v1/admin/users`, THE Auth_Guard SHALL autoriser la création d'un nouvel utilisateur
2. WHEN un utilisateur avec le rôle `admin` envoie une requête PUT à `/api/v1/admin/users/{id}`, THE Auth_Guard SHALL autoriser la modification du rôle ou du statut de l'utilisateur
3. WHEN un utilisateur avec un rôle autre que `admin` envoie une requête à `/api/v1/admin/users`, THE Auth_Guard SHALL retourner une réponse HTTP 403
4. WHEN un administrateur modifie le rôle d'un utilisateur, THE RBAC_System SHALL journaliser l'action dans le journal d'audit avec les valeurs avant et après modification
5. IF un administrateur tente d'attribuer un rôle invalide à un utilisateur, THEN THE RBAC_System SHALL retourner une erreur HTTP 422 avec un message descriptif

---

### Requirement 9 : Accès anonyme à l'assistant QA

**User Story:** En tant que visiteur non enregistré, je veux accéder à l'assistant QA sans créer de compte, afin de pouvoir poser des questions sans friction d'inscription.

#### Acceptance Criteria

1. WHEN un utilisateur non authentifié accède à la page `/qa`, THE RBAC_System SHALL afficher l'interface de l'assistant QA sans redirection vers une page de connexion
2. WHEN un utilisateur non authentifié envoie une requête à l'endpoint `/api/v1/qa`, THE Auth_Guard SHALL traiter la requête avec les permissions du rôle `guest`
3. THE RBAC_System SHALL ne pas exiger de token JWT pour accéder à l'endpoint `/api/v1/qa`
4. WHEN un utilisateur non authentifié tente d'accéder à tout autre endpoint ou page protégée que `/api/v1/qa` ou `/qa`, THE Auth_Guard SHALL rediriger l'utilisateur vers la page de connexion
5. THE RBAC_System SHALL ne pas afficher de données médicales sensibles (dossiers patients, diagnostics, prescriptions) dans l'interface de l'assistant QA accessible aux guests

---

### Requirement 6 : Non-régression des rôles existants

**User Story:** En tant que développeur, je veux que l'introduction des nouveaux rôles ne casse pas les comportements existants des rôles `medecin` et `admin`, afin de garantir la stabilité de l'application.

#### Acceptance Criteria

1. WHEN un utilisateur avec le rôle `medecin` utilise les fonctionnalités de diagnostic, de chat ou de gestion des patients, THE RBAC_System SHALL se comporter de manière identique à avant l'introduction du RBAC étendu
2. WHEN un utilisateur avec le rôle `admin` utilise les fonctionnalités d'administration existantes (protocoles, interactions médicamenteuses, documents), THE RBAC_System SHALL se comporter de manière identique à avant l'introduction du RBAC étendu
3. THE RBAC_System SHALL maintenir la compatibilité avec les tokens JWT existants contenant les rôles `medecin` ou `admin`
4. IF un token JWT contient le rôle `pharmacien` (rôle hérité), THEN THE RBAC_System SHALL traiter ce rôle avec les mêmes permissions que le rôle `guest` pour assurer la rétrocompatibilité

---

### Requirement 7 : Propagation du rôle dans le frontend

**User Story:** En tant que développeur frontend, je veux que le rôle de l'utilisateur soit disponible dans le contexte d'authentification, afin que tous les composants puissent adapter leur rendu en fonction des permissions.

#### Acceptance Criteria

1. WHEN un utilisateur se connecte avec succès, THE RBAC_System SHALL stocker le rôle de l'utilisateur dans le AuthContext accessible à tous les composants React
2. THE RBAC_System SHALL exposer un hook `useAuth` retournant le rôle de l'utilisateur courant sous forme de valeur typée `UserRole`
3. WHEN le rôle de l'utilisateur change (ex. modification par un admin), THE RBAC_System SHALL invalider la session courante et forcer une reconnexion
4. THE RBAC_System SHALL typer `UserRole` comme l'union `'admin' | 'medecin' | 'infirmière' | 'guest'` dans le package `@diagno-pilot/types`

---

### Requirement 8 : Accès mobile selon le rôle

**User Story:** En tant qu'utilisateur de l'application mobile, je veux que les onglets et fonctionnalités affichés correspondent à mon rôle, afin de ne voir que ce qui m'est accessible.

#### Acceptance Criteria

1. WHILE l'utilisateur mobile a le rôle `medecin`, THE RBAC_System SHALL afficher les onglets : Diagnostic, Chat, Patients, Profil
2. WHILE l'utilisateur mobile a le rôle `infirmière`, THE RBAC_System SHALL afficher les onglets : Diagnostic, Chat, Patients, Profil
3. WHILE l'utilisateur mobile a le rôle `guest`, THE RBAC_System SHALL afficher uniquement l'accès à l'assistant QA, sans exiger de connexion
4. WHILE l'utilisateur mobile a le rôle `admin`, THE RBAC_System SHALL afficher tous les onglets disponibles
5. IF un utilisateur mobile tente d'accéder à un écran non autorisé par son rôle, THEN THE RBAC_System SHALL rediriger l'utilisateur vers l'écran Profil
