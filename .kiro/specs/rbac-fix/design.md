# RBAC Fix — Bugfix Design

## Overview

Le système RBAC de Diagno-Pilot présente plusieurs incohérences entre les règles d'accès définies et leur application effective. Ce document formalise les conditions de bug, les comportements attendus, les causes racines hypothétiques et la stratégie de correction pour les six défauts identifiés :

1. **NavBar** : liens Documents visibles pour `infirmière` ; lien "Se connecter" absent pour guest
2. **Page Documents** : accessible à tous les rôles authentifiés sans garde de rôle
3. **Backend upload** : `POST /api/v1/documents/upload` refuse le rôle `medecin` (HTTP 403)
4. **Backend chat** : `POST /api/v1/chat` refuse le rôle `infirmière` (HTTP 403)
5. **Interface médecin** : absence de formulaire de création de compte `infirmière`
6. **Interface admin** : absence de formulaire dédié de création de compte `medecin`

L'approche de correction est minimale et ciblée : modifier uniquement les points d'application des règles RBAC sans toucher aux comportements existants corrects.

---

## Glossary

- **Bug_Condition (C)** : La condition qui déclenche le bug — une combinaison (rôle, action/route) qui produit un comportement incorrect
- **Property (P)** : Le comportement correct attendu quand la condition de bug est satisfaite
- **Preservation** : Les comportements existants corrects qui ne doivent pas être modifiés par le correctif
- **NavBar** : Composant `apps/web/src/components/NavBar.tsx` — barre de navigation principale
- **links[]** : Tableau de liens construit dans NavBar, actuellement sans filtrage par rôle (sauf admin) et sans lien "Se connecter" pour guest
- **ROLE_NAV_LINKS** : Map de permissions NavBar par rôle : `guest` → `[qa, signin]` ; `infirmière` → `[qa, chat, diagnose, patients]` ; `medecin` → `[qa, chat, diagnose, patients, documents]` ; `admin` → `[qa, chat, diagnose, patients, documents, admin]`
- **documents/page.tsx** : Page `apps/web/src/app/[locale]/documents/page.tsx` — gestion des documents médicaux
- **require_role** : Dépendance FastAPI dans `backend/core/auth.py` qui lève HTTP 403 si le rôle n'est pas dans la liste autorisée
- **ALLOWED_ROLES_UPLOAD** : Ensemble des rôles autorisés à uploader des documents — actuellement `["admin"]`, devrait être `["admin", "medecin"]`
- **ALLOWED_ROLES_CHAT** : Ensemble des rôles autorisés à utiliser le Chat authentifié — actuellement `["admin", "medecin"]`, devrait être `["admin", "medecin", "infirmière"]`
- **CreateNurseForm** : Formulaire de création de compte infirmière à exposer aux médecins
- **CreateDoctorForm** : Formulaire de création de compte médecin à exposer dans le panneau admin

---

## Bug Details

### Bug Condition

Les bugs se manifestent quand un utilisateur authentifié avec un rôle spécifique tente d'accéder à une ressource ou voit une interface qui ne correspond pas à ses permissions RBAC définies.

**Formal Specification :**

```
FUNCTION isBugCondition(input)
  INPUT: input = { role: UserRole, action: Action }
  OUTPUT: boolean

  -- Bug 1 : NavBar affiche Documents pour infirmière
  IF action = RENDER_NAVBAR AND role = 'infirmière'
    AND DOCUMENTS_LINK in rendered_links
    RETURN true

  -- Bug 2 : NavBar guest sans lien "Se connecter"
  IF action = RENDER_NAVBAR AND role = 'guest'
    AND SIGNIN_LINK not in rendered_links
    RETURN true

  -- Bug 3 : Page Documents accessible sans garde de rôle
  IF action = NAVIGATE_TO_DOCUMENTS
    AND role IN ['infirmière', 'guest']
    AND page_renders_without_redirect
    RETURN true

  -- Bug 4 : Upload refusé pour medecin
  IF action = POST_DOCUMENTS_UPLOAD
    AND role = 'medecin'
    AND http_response_status = 403
    RETURN true

  -- Bug 5 : Chat refusé pour infirmière
  IF action = POST_CHAT
    AND role = 'infirmière'
    AND http_response_status = 403
    RETURN true

  -- Bug 6 : Formulaire création infirmière absent pour medecin
  IF action = RENDER_MEDECIN_INTERFACE
    AND role = 'medecin'
    AND create_nurse_form_absent
    RETURN true

  -- Bug 7 : Formulaire création médecin absent pour admin
  IF action = RENDER_ADMIN_PANEL
    AND role = 'admin'
    AND create_doctor_dedicated_form_absent
    RETURN true

  RETURN false
END FUNCTION
```

### Examples

- **Bug 1** : Utilisateur `infirmière` connecté → NavBar affiche `[Documents, Chat, Diagnostic, Patients]` au lieu de `[Q&A, Chat, Diagnostic, Patients]`
- **Bug 2** : Utilisateur `guest` → NavBar n'affiche pas de lien "Se connecter"
- **Bug 3** : Utilisateur `infirmière` navigue vers `/fr-TG/documents` → la page s'affiche normalement au lieu de rediriger vers `/fr-TG`
- **Bug 4** : Utilisateur `medecin` envoie `POST /api/v1/documents/upload` avec un fichier PDF valide → reçoit HTTP 403 au lieu de HTTP 201
- **Bug 5** : Utilisateur `infirmière` envoie `POST /api/v1/chat` → reçoit HTTP 403 au lieu d'une réponse valide
- **Bug 6** : Utilisateur `medecin` connecté → aucun bouton/formulaire "Créer un compte infirmière" n'est visible dans son interface
- **Bug 7** : Utilisateur `admin` dans le panneau d'administration → pas de section dédiée "Créer un médecin"

---

## Expected Behavior

### Preservation Requirements

**Comportements inchangés :**
- L'accès non authentifié à `/qa` et `/[locale]/qa` doit continuer à fonctionner sans redirection
- La redirection vers `/[locale]/login` pour les routes protégées sans token doit rester identique
- Le panneau admin (`/[locale]/admin`) doit continuer à fonctionner pour `admin` et rediriger les autres rôles
- L'accès de `medecin` à Diagnostic, Patients et Chat doit rester autorisé
- Les endpoints `/api/v1/patients`, `/api/v1/diagnose`, `/api/v1/chat` doivent rester accessibles pour `admin`, `medecin`, `infirmière`
- Le rôle `pharmacien` (hérité) doit continuer à être traité comme `guest`
- Les clics souris sur les liens NavBar existants doivent continuer à fonctionner
- La gestion des utilisateurs, statistiques, audit et protocoles dans le panneau admin doivent rester inchangés

**Scope :**
Tous les inputs qui ne correspondent pas aux conditions de bug (rôles non affectés, routes non concernées) doivent être complètement inaffectés par ce correctif.

---

## Hypothesized Root Cause

### Bug 1 — NavBar affiche Documents pour infirmière / pas de lien "Se connecter" pour guest

Dans `NavBar.tsx`, le tableau `links[]` est construit de façon statique pour tous les utilisateurs authentifiés sans filtrage par rôle. Le lien Documents apparaît pour `infirmière`. De plus, aucun lien "Se connecter" n'est rendu pour les utilisateurs non authentifiés.

**Cause probable** : La logique de filtrage RBAC n'a jamais été implémentée pour les liens non-admin. Le tableau `links` devrait être dérivé d'une map `ROLE_NAV_LINKS` par rôle, incluant un cas `guest` avec un lien de connexion.

### Bug 2 — Page Documents sans garde de rôle

Dans `documents/page.tsx`, le `useEffect` de garde ne vérifie que `!user` (non authentifié). Il n'y a pas de vérification `user.role`. La page est donc accessible à tout utilisateur authentifié, quel que soit son rôle.

**Cause probable** : La garde a été copiée depuis une page sans restriction de rôle. La condition `user.role !== 'admin' && user.role !== 'medecin'` n'a pas été ajoutée.

### Bug 3 — Backend upload admin-only

Dans `backend/routers/documents.py`, le décorateur de l'endpoint `POST /upload` utilise `require_role(["admin"])`. Le rôle `medecin` n'est pas inclus dans la liste.

**Cause probable** : La liste des rôles autorisés a été définie trop restrictivement lors de l'implémentation initiale. Changer `["admin"]` en `["admin", "medecin"]` suffit.

### Bug 4 — Backend chat infirmière-bloquée

Dans `backend/routers/chat.py` (ou équivalent), l'endpoint `POST /chat` utilise `require_role(["admin", "medecin"])`. Le rôle `infirmière` n'est pas inclus.

**Cause probable** : Le chat authentifié a été initialement réservé aux médecins et admins. Ajouter `infirmière` à la liste suffit.

### Bug 5 — Formulaire création infirmière absent

Il n'existe pas de composant ni de page permettant à un `medecin` de créer un compte `infirmière`. L'endpoint `POST /api/v1/admin/users` existe côté backend mais est protégé par `require_role(["admin"])`, ce qui empêche aussi les médecins de l'utiliser.

**Cause probable** : La fonctionnalité n'a pas été implémentée. Il faut (a) créer un endpoint dédié `POST /api/v1/medecin/users`, et (b) créer l'interface frontend.

### Bug 6 — Formulaire création médecin absent dans admin

Le panneau admin permet la création générique d'utilisateurs via `PATCH /api/v1/admin/users/{id}/role`, mais il n'y a pas de formulaire dédié "Créer un médecin" avec un flux guidé (email, mot de passe, nom complet, rôle pré-sélectionné à `medecin`).

**Cause probable** : Le flux de création d'utilisateur dans le panneau admin est générique. Un formulaire dédié avec le rôle `medecin` pré-sélectionné n'a pas été ajouté.

---

## Correctness Properties

Property 1: Bug Condition — Filtrage NavBar par rôle

_For any_ utilisateur authentifié avec le rôle `infirmière`, le composant NavBar corrigé SHALL afficher uniquement les liens Q&A, Chat, Diagnostic guidé et Patients — sans le lien Documents.

_For any_ utilisateur non authentifié (guest), le composant NavBar corrigé SHALL afficher un lien "Se connecter" pointant vers `/[locale]/login`.

**Validates: Requirements 2.1, 2.6, 2.7, 2.8**

Property 2: Bug Condition — Garde de rôle sur la page Documents

_For any_ utilisateur authentifié avec un rôle non autorisé (`infirmière` ou `guest`), la page Documents corrigée SHALL rediriger l'utilisateur vers la page d'accueil (`/[locale]`) au lieu d'afficher le contenu.

**Validates: Requirements 2.2**

Property 3: Bug Condition — Upload autorisé pour medecin

_For any_ requête `POST /api/v1/documents/upload` avec un token JWT valide de rôle `medecin` et un fichier de format supporté, l'endpoint corrigé SHALL retourner HTTP 201 (Created).

**Validates: Requirements 2.3**

Property 3b: Bug Condition — Chat autorisé pour infirmière

_For any_ requête `POST /api/v1/chat` avec un token JWT valide de rôle `infirmière`, l'endpoint corrigé SHALL retourner une réponse valide (non HTTP 403).

**Validates: Requirements 2.10**

Property 4: Bug Condition — Formulaire création infirmière pour medecin

_For any_ utilisateur authentifié avec le rôle `medecin`, l'interface corrigée SHALL proposer un formulaire de création de compte `infirmière` accessible depuis son interface.

**Validates: Requirements 2.4, 2.9**

Property 5: Bug Condition — Formulaire création médecin pour admin

_For any_ utilisateur authentifié avec le rôle `admin`, le panneau d'administration corrigé SHALL proposer un formulaire dédié pour créer un compte `medecin`.

**Validates: Requirements 2.5**

Property 6: Preservation — Comportements non affectés par le correctif

_For any_ utilisateur dont le rôle et l'action ne correspondent PAS à une condition de bug (isBugCondition retourne false), le code corrigé SHALL produire exactement le même résultat que le code original, préservant tous les accès et redirections existants.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9**

---

## Fix Implementation

### Changes Required

#### Fichier 1 : `apps/web/src/components/NavBar.tsx`

**Fonction** : Construction du tableau `links[]`

**Changements spécifiques** :
1. Définir une map `ROLE_NAV_LINKS` par rôle :
   - `guest` → `[qa, signin]`
   - `infirmière` → `[qa, chat, diagnose, patients]`
   - `medecin` → `[qa, chat, diagnose, patients, documents]`
   - `admin` → `[qa, chat, diagnose, patients, documents, admin]`
2. Remplacer la liste statique par un filtrage conditionnel basé sur `user?.role ?? 'guest'`
3. Afficher le lien "Se connecter" pour les utilisateurs non authentifiés

#### Fichier 2 : `apps/web/src/app/[locale]/documents/page.tsx`

**Fonction** : `useEffect` de garde d'authentification

**Changements spécifiques** :
1. Étendre la condition de redirection : `!user || (user.role !== 'admin' && user.role !== 'medecin')`
2. Rediriger vers `/${locale}` (accueil) avec un message d'accès refusé pour les rôles non autorisés
3. Masquer le formulaire d'upload pour les rôles non-admin (seul `admin` peut uploader/supprimer, `medecin` peut lister)

#### Fichier 3 : `backend/routers/documents.py`

**Fonction** : Décorateur de l'endpoint `POST /upload`

**Changements spécifiques** :
1. Changer `require_role(["admin"])` en `require_role(["admin", "medecin"])` sur l'endpoint `/upload`
2. Conserver `require_role(["admin"])` sur l'endpoint `DELETE /{document_id}`

#### Fichier 3b : `backend/routers/chat.py` (ou équivalent)

**Fonction** : Décorateur de l'endpoint `POST /chat`

**Changements spécifiques** :
1. Ajouter `infirmière` à la liste des rôles autorisés : `require_role(["admin", "medecin", "infirmière"])`

#### Fichier 4 : Interface médecin — nouveau composant

**Fichier** : `apps/web/src/app/[locale]/create-nurse/page.tsx`

**Changements spécifiques** :
1. Créer un formulaire de création de compte `infirmière` (email, mot de passe, nom complet)
2. Appeler `POST /api/v1/medecin/users` (nouvel endpoint dédié)
3. Rendre accessible uniquement pour `medecin` (garde de rôle)

#### Fichier 5 : `backend/routers/medecin.py` — nouvel endpoint

**Changements spécifiques** :
1. Créer `POST /api/v1/medecin/users` avec `require_role(["medecin"])` permettant de créer uniquement des comptes `infirmière`
2. Valider que le rôle demandé est strictement `infirmière` (HTTP 403 sinon)

#### Fichier 6 : `apps/web/src/app/[locale]/admin/page.tsx`

**Changements spécifiques** :
1. Ajouter une section "Créer un médecin" avec un formulaire dédié (email, mot de passe, nom complet, rôle pré-sélectionné `medecin`)
2. Appeler `POST /api/v1/admin/users` avec `role: 'medecin'`

---

## Testing Strategy

### Validation Approach

La stratégie suit deux phases : d'abord, faire échouer des tests sur le code non corrigé pour confirmer les bugs et la cause racine, puis vérifier que le correctif fonctionne et préserve les comportements existants.

### Exploratory Bug Condition Checking

**Goal** : Faire surface des contre-exemples qui démontrent les bugs AVANT d'implémenter le correctif. Confirmer ou réfuter l'analyse de cause racine.

**Test Plan** : Écrire des tests qui simulent chaque condition de bug et assertent le comportement attendu (correct). Ces tests ÉCHOUERONT sur le code non corrigé.

**Test Cases** :
1. **NavBar infirmière — lien Documents interdit** : Rendre NavBar avec `role='infirmière'`, vérifier que Documents est absent et Chat est présent (échouera sur code non corrigé — Documents est présent)
2. **NavBar guest — lien Se connecter absent** : Rendre NavBar sans utilisateur, vérifier la présence du lien "Se connecter" (échouera — absent)
3. **Page Documents — garde de rôle** : Simuler navigation vers `/documents` avec `role='infirmière'`, vérifier la redirection (échouera — la page s'affiche)
4. **Upload medecin — HTTP 403** : Appeler `POST /api/v1/documents/upload` avec token `medecin`, vérifier HTTP 201 (échouera — retourne 403)
5. **Chat infirmière — HTTP 403** : Appeler `POST /api/v1/chat` avec token `infirmière`, vérifier réponse valide (échouera — retourne 403)
6. **Formulaire création infirmière** : Rendre l'interface médecin, vérifier la présence du formulaire (échouera — absent)
7. **Formulaire création médecin** : Rendre le panneau admin, vérifier la présence du formulaire dédié médecin (échouera — absent)

**Expected Counterexamples** :
- NavBar avec `infirmière` : `links` contient `href` incluant `/documents`
- NavBar avec `guest` : aucun lien "Se connecter" dans le DOM
- Page Documents : `router.push` n'est pas appelé pour `infirmière`
- Upload : `require_role(["admin"])` lève HTTP 403 pour `medecin`
- Chat : `require_role(["admin", "medecin"])` lève HTTP 403 pour `infirmière`
- Formulaires : composants absents du DOM

### Fix Checking

**Goal** : Vérifier que pour tous les inputs où la condition de bug est vraie, le code corrigé produit le comportement attendu.

**Pseudocode :**
```
FOR ALL input WHERE isBugCondition(input) DO
  result := fixedCode(input)
  ASSERT expectedBehavior(result)
END FOR
```

### Preservation Checking

**Goal** : Vérifier que pour tous les inputs où la condition de bug est fausse, le code corrigé produit le même résultat que le code original.

**Pseudocode :**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT originalCode(input) = fixedCode(input)
END FOR
```

**Testing Approach** : Les tests basés sur les propriétés (property-based testing) sont recommandés pour la vérification de préservation car :
- Ils génèrent automatiquement de nombreux cas de test sur le domaine d'entrée
- Ils capturent les cas limites que les tests unitaires manuels pourraient manquer
- Ils fournissent des garanties fortes que le comportement est inchangé pour tous les inputs non-buggy

**Test Plan** : Observer le comportement sur le code non corrigé pour les rôles non affectés, puis écrire des tests de propriété capturant ce comportement.

**Test Cases** :
1. **Preservation NavBar admin** : Vérifier que `admin` voit toujours Q&A, Chat, Diagnostic, Patients, Documents, Admin
2. **Preservation NavBar medecin** : Vérifier que `medecin` voit toujours Q&A, Chat, Diagnostic, Patients, Documents
3. **Preservation accès /qa** : Vérifier que les utilisateurs non authentifiés accèdent toujours à `/qa`
4. **Preservation redirection non-auth** : Vérifier que les routes protégées redirigent toujours vers login
5. **Preservation upload admin** : Vérifier que `admin` peut toujours uploader (HTTP 201)
6. **Preservation delete admin** : Vérifier que `admin` peut toujours supprimer des documents
7. **Preservation chat medecin** : Vérifier que `medecin` peut toujours utiliser le chat (HTTP 200)
8. **Preservation panneau admin** : Vérifier que le panneau admin fonctionne identiquement pour `admin`

### Unit Tests

- Tester le rendu NavBar pour chaque rôle (`admin`, `medecin`, `infirmière`, `guest`) et vérifier les liens présents/absents
- Tester la garde de rôle de la page Documents pour chaque rôle
- Tester l'endpoint upload avec chaque rôle (`admin` → 201, `medecin` → 201, `infirmière` → 403, `guest` → 401)
- Tester l'endpoint chat avec chaque rôle (`admin` → 200, `medecin` → 200, `infirmière` → 200, `guest` → 401)
- Tester le formulaire de création infirmière : rendu conditionnel selon le rôle
- Tester le formulaire de création médecin dans le panneau admin
- Tester `POST /api/v1/medecin/users` : `medecin` crée `infirmière` → 201 ; `medecin` tente de créer `medecin` → 403

### Property-Based Tests

- Générer des rôles aléatoires parmi `['admin', 'medecin', 'infirmière', 'guest']` et vérifier que NavBar affiche exactement les liens autorisés pour ce rôle (Property 1 & 6)
- Générer des rôles non autorisés pour la page Documents et vérifier la redirection systématique (Property 2)
- Générer des tokens JWT valides pour `admin` et `medecin` et vérifier que l'upload retourne 201 (Property 3)
- Générer des rôles non affectés et vérifier que le comportement est identique avant/après correctif (Property 6)

### Integration Tests

- Test de flux complet : connexion en tant qu'`infirmière`, navigation vers `/documents` → redirection vers accueil
- Test de flux complet : connexion en tant que `medecin`, upload d'un document → HTTP 201
- Test de flux complet : connexion en tant que `medecin`, création d'un compte `infirmière` via le formulaire
- Test de flux complet : connexion en tant qu'`admin`, création d'un compte `medecin` via le formulaire dédié
- Test de non-régression : connexion en tant qu'`admin`, accès au panneau admin → toutes les sections fonctionnent
