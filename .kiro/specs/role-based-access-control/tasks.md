# Plan d'implémentation : Contrôle d'accès basé sur les rôles (RBAC)

## Vue d'ensemble

Implémentation du RBAC sur trois couches (backend FastAPI, frontend Next.js, mobile Expo) avec les quatre rôles `admin`, `medecin`, `infirmière`, `guest`. Les tâches suivent un ordre incrémental : modèles de données → guards backend → routes → middleware frontend → composants → mobile.

## Tâches

- [x] 1. Mettre à jour les types et modèles de données partagés
  - [x] 1.1 Mettre à jour `UserRole` dans `packages/types/index.ts`
    - Remplacer le type existant par l'union `'admin' | 'medecin' | 'infirmière' | 'guest'`
    - _Requirements: 1.1, 7.4_

  - [x] 1.2 Écrire un test unitaire pour le type `UserRole`
    - Vérifier que le type contient exactement les 4 valeurs attendues (Exemple 7.4)
    - _Requirements: 1.1, 7.4_

  - [x] 1.3 Mettre à jour l'enum `UserRole` dans `backend/models/common.py`
    - Remplacer l'enum existant par `admin`, `medecin`, `infirmière`, `guest`
    - Retirer `pharmacien` de l'enum
    - _Requirements: 1.1, 1.2_

  - [x] 1.4 Écrire un test de propriété pour la validation des rôles
    - **Property 1 : Validation des rôles valides**
    - **Validates: Requirements 1.1, 1.2**
    - `@given(role=st.text())` — seuls les 4 rôles valides sont acceptés par l'enum
    - Fichier : `backend/tests/test_rbac_property.py`

- [x] 2. Mettre à jour l'authentification backend
  - [x] 2.1 Modifier `get_current_user` dans `backend/core/auth.py`
    - Ajouter le mapping `LEGACY_ROLE_MAP = {"pharmacien": "guest"}`
    - Mapper le rôle `pharmacien` vers `guest` lors du décodage du JWT
    - _Requirements: 6.3, 6.4_

  - [x] 2.2 Ajouter `get_current_user_optional` dans `backend/core/auth.py`
    - Accepter un token optionnel (retourne `None` si absent)
    - Utilisé pour les routes publiques comme `/api/v1/qa`
    - _Requirements: 2.4, 9.2, 9.3_

  - [x] 2.3 Écrire un test de propriété pour la rétrocompatibilité des tokens
    - **Property 10 : Rétrocompatibilité des tokens JWT existants**
    - **Validates: Requirements 6.3**
    - `@given(role=st.sampled_from(["medecin", "admin"]))` — tokens acceptés et autorisés
    - Fichier : `backend/tests/test_rbac_property.py`

  - [x] 2.4 Écrire un test unitaire pour le mapping `pharmacien` → `guest`
    - Exemple 6.4 : token avec rôle `pharmacien` → traité comme `guest`
    - _Requirements: 6.4_

- [x] 3. Créer le router QA public
  - [x] 3.1 Créer `backend/routers/qa.py` avec l'endpoint `POST /qa`
    - Utiliser `get_current_user_optional` (pas de JWT requis)
    - Brancher la logique QA existante sur ce nouveau router
    - _Requirements: 2.4, 9.2, 9.3_

  - [x] 3.2 Écrire un test unitaire pour l'accès public à `/api/v1/qa`
    - Exemple 2.4 : requête sans JWT → HTTP 200
    - Exemple 9.3 : sans Authorization header → HTTP 200
    - _Requirements: 2.4, 9.1, 9.3_

- [x] 4. Créer les routers d'administration
  - [x] 4.1 Créer `backend/routers/admin.py` avec les endpoints de gestion des utilisateurs
    - `GET /admin/users`, `POST /admin/users`, `PUT /admin/users/{id}` protégés par `require_role(["admin"])`
    - Ajouter le champ `is_active` au modèle `UserDocument`
    - Retourner HTTP 422 si le rôle fourni est invalide
    - _Requirements: 5.1, 5.2, 5.3, 5.5_

  - [x] 4.2 Ajouter l'endpoint `GET /admin/stats` dans `backend/routers/admin.py`
    - Protégé par `require_role(["admin"])`
    - Journaliser chaque accès dans le journal d'audit (user_id, timestamp, IP)
    - _Requirements: 4.1, 4.2, 4.3_

  - [x] 4.3 Ajouter la journalisation d'audit pour les modifications de rôle
    - Lors d'un `PUT /admin/users/{id}`, enregistrer les valeurs avant/après dans le journal d'audit
    - _Requirements: 5.4_

  - [x] 4.4 Écrire un test de propriété pour l'accès admin aux endpoints d'administration
    - **Property 3 : Admin autorisé sur tous les endpoints d'administration**
    - **Validates: Requirements 2.1**
    - `@given(role=st.just("admin"), endpoint=st.sampled_from(ADMIN_ENDPOINTS))`
    - Fichier : `backend/tests/test_rbac_property.py`

  - [x] 4.5 Écrire un test de propriété pour le rejet des non-admins
    - **Property 4 : Non-admin rejeté sur les endpoints d'administration**
    - **Validates: Requirements 2.2, 4.2, 5.3**
    - `@given(role=st.sampled_from(NON_ADMIN_ROLES), endpoint=st.sampled_from(ADMIN_ENDPOINTS))`
    - Fichier : `backend/tests/test_rbac_property.py`

  - [x] 4.6 Écrire un test unitaire pour le rôle invalide à la création
    - Exemple 5.5 : attribution d'un rôle invalide → HTTP 422
    - _Requirements: 5.5_

- [x] 5. Protéger les endpoints médicaux existants
  - [x] 5.1 Vérifier et mettre à jour les guards sur `/api/v1/patients`, `/api/v1/diagnose`, `/api/v1/chat`
    - S'assurer que `require_role(["admin", "medecin", "infirmière"])` est appliqué
    - _Requirements: 2.3, 6.1_

  - [x] 5.2 Écrire un test de propriété pour les rôles médicaux sur les ressources médicales
    - **Property 5 : Rôles médicaux autorisés sur les ressources médicales**
    - **Validates: Requirements 2.3, 6.1**
    - `@given(role=st.sampled_from(MEDICAL_ROLES), endpoint=st.sampled_from(MEDICAL_ENDPOINTS))`
    - Fichier : `backend/tests/test_rbac_property.py`

- [x] 6. Checkpoint — Vérifier que tous les tests backend passent
  - S'assurer que tous les tests passent, poser des questions à l'utilisateur si nécessaire.

- [x] 7. Mettre à jour le middleware Next.js
  - [x] 7.1 Étendre `apps/web/src/middleware.ts`
    - Lire le token JWT depuis le cookie `access_token`
    - Décoder le rôle sans vérification de signature (`decodeRoleFromJwt`)
    - Rediriger `/[locale]/admin` vers `/[locale]` si le rôle n'est pas `admin`
    - Laisser passer `/qa` et `/[locale]/qa` sans authentification
    - Rediriger toute route protégée sans token vers `/[locale]/login`
    - _Requirements: 3.3, 3.4, 9.1, 9.4_

  - [x] 7.2 Écrire un test de propriété pour la redirection middleware hors de /admin
    - **Property 8 : Middleware redirige les non-admins hors de /admin**
    - **Validates: Requirements 3.3**
    - `fc.property(fc.constantFrom(...NON_ADMIN_ROLES), role => middleware redirige hors de /admin)`
    - Fichier : `apps/web/src/middleware.test.ts`

  - [x] 7.3 Écrire un test de propriété pour la redirection sans token
    - **Property 6 : Requêtes non authentifiées redirigées vers login**
    - **Validates: Requirements 2.5, 9.4**
    - `fc.property(fc.constantFrom(...PROTECTED_PATHS), path => sans token → redirect login)`
    - Fichier : `apps/web/src/middleware.test.ts`

  - [x] 7.4 Écrire un test unitaire pour le middleware
    - Middleware laisse passer `/qa` sans token
    - Admin accède à `/admin` sans redirection
    - _Requirements: 3.3, 9.1_

- [x] 8. Mettre à jour les composants frontend web
  - [x] 8.1 Mettre à jour `apps/web/src/components/NavBar.tsx`
    - Mettre à jour l'import du type `UserRole` depuis `@diagno-pilot/types`
    - Vérifier que la condition `user?.role !== 'admin'` masque bien le Menu_Admin
    - _Requirements: 3.1, 3.2_

  - [x] 8.2 Écrire un test de propriété pour la visibilité du menu admin dans NavBar
    - **Property 7 : Visibilité du menu admin corrélée au rôle**
    - **Validates: Requirements 3.1, 3.2**
    - `fc.property(fc.constantFrom(...NON_ADMIN_ROLES), role => renderNavBar(role) ne contient pas le lien admin)`
    - Fichier : `apps/web/src/components/__tests__/NavBar.rbac.test.tsx`

  - [x] 8.3 Écrire des tests unitaires pour NavBar
    - Admin voit le lien admin, `medecin`/`infirmière`/`guest` ne le voient pas
    - _Requirements: 3.1, 3.2_

- [x] 9. Mettre à jour le round-trip rôle via /auth/me
  - [x] 9.1 Vérifier que l'endpoint `/api/v1/auth/me` retourne le champ `role` dans sa réponse
    - S'assurer que le schéma de réponse inclut `role: UserRole`
    - _Requirements: 1.4, 7.1_

  - [x] 9.2 Écrire un test de propriété pour le round-trip rôle
    - **Property 2 : Round-trip rôle via /auth/me**
    - **Validates: Requirements 1.4, 7.1**
    - `@given(role=st.sampled_from(VALID_ROLES))` — login puis /auth/me retourne le même rôle
    - Fichier : `backend/tests/test_rbac_property.py`

  - [x] 9.3 Écrire un test unitaire pour la création d'utilisateur sans rôle
    - Exemple 1.3 : création sans rôle → rôle `guest` par défaut
    - _Requirements: 1.3_

- [x] 10. Mettre à jour le TabsLayout mobile
  - [x] 10.1 Modifier `apps/mobile/app/(tabs)/_layout.tsx`
    - Définir `MEDICAL_ROLES: UserRole[] = ['medecin', 'infirmière', 'admin']`
    - Conditionner l'affichage des onglets `diagnose`, `chat`, `patients` aux rôles médicaux
    - Afficher l'onglet `qa` pour tous les rôles
    - Masquer l'onglet `profile` pour le rôle `guest`
    - Rediriger vers l'écran Profil si navigation vers un écran non autorisé
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [x] 10.2 Écrire un test de propriété pour les onglets des rôles médicaux
    - **Property 12 : Onglets mobiles corrects pour les rôles médicaux**
    - **Validates: Requirements 8.1, 8.2**
    - `fc.property(fc.constantFrom('medecin', 'infirmière'), role => les 4 onglets médicaux sont présents)`
    - Fichier : `apps/mobile/app/(tabs)/__tests__/_layout.rbac.test.tsx`

  - [x] 10.3 Écrire un test de propriété pour les onglets guest
    - **Property 13 : Onglet QA uniquement pour les guests mobiles**
    - **Validates: Requirements 8.3**
    - `fc.property(fc.just('guest'), role => seul l'onglet QA est présent)`
    - Fichier : `apps/mobile/app/(tabs)/__tests__/_layout.rbac.test.tsx`

  - [x] 10.4 Écrire un test de propriété pour la redirection mobile
    - **Property 14 : Redirection mobile vers Profil pour écrans non autorisés**
    - **Validates: Requirements 8.5**
    - `fc.property(fc.tuple(fc.constantFrom(...ROLES), fc.constantFrom(...SCREENS)), ([role, screen]) => navigation non autorisée → redirect Profil)`
    - Fichier : `apps/mobile/app/(tabs)/__tests__/_layout.rbac.test.tsx`

  - [x] 10.5 Écrire des tests unitaires pour le TabsLayout mobile
    - Admin voit tous les onglets
    - Guest ne voit pas les onglets médicaux
    - _Requirements: 8.3, 8.4_

- [x] 11. Ajouter les tests de propriété pour l'audit log
  - [x] 11.1 Implémenter la structure du journal d'audit dans le backend
    - S'assurer que chaque entrée contient `user_id`, `timestamp` et `ip_address`
    - _Requirements: 4.3, 5.4_

  - [x] 11.2 Écrire un test de propriété pour le journal d'audit
    - **Property 9 : Audit log contient les métadonnées requises**
    - **Validates: Requirements 4.3, 5.4**
    - `@given(role=st.just("admin"))` — vérifier les champs de l'entrée d'audit
    - Fichier : `backend/tests/test_rbac_property.py`

- [x] 12. Vérifier la propagation du rôle dans AuthContext
  - [x] 12.1 Vérifier que `apps/web/src/contexts/AuthContext.tsx` stocke et expose `user.role` typé `UserRole`
    - Mettre à jour l'import du type depuis `@diagno-pilot/types` si nécessaire
    - _Requirements: 7.1, 7.2_

  - [x] 12.2 Vérifier que `apps/mobile/src/contexts/AuthContext.tsx` expose `user.role` typé `UserRole`
    - Mettre à jour l'import du type depuis `@diagno-pilot/types` si nécessaire
    - _Requirements: 7.1, 7.2_

  - [x] 12.3 Écrire un test de propriété pour `useAuth`
    - **Property 11 : useAuth retourne un UserRole valide**
    - **Validates: Requirements 7.2**
    - Vérifier que `user.role` appartient à l'union valide ou est `null`
    - _Requirements: 7.2_

  - [x] 12.4 Écrire un test unitaire pour l'invalidation de session après changement de rôle
    - Exemple 7.3 : modification de rôle par admin → session invalidée
    - _Requirements: 7.3_

- [x] 13. Checkpoint final — Vérifier que tous les tests passent
  - S'assurer que tous les tests passent sur les trois couches, poser des questions à l'utilisateur si nécessaire.

## Notes

- Les tâches marquées `*` sont optionnelles et peuvent être ignorées pour un MVP rapide
- Chaque tâche référence les exigences spécifiques pour la traçabilité
- Les tests de propriété utilisent `hypothesis` (backend) et `fast-check` (frontend/mobile)
- `fast-check` doit être ajouté comme dépendance de dev dans `apps/web` et `apps/mobile`
- Les tests de propriété backend doivent être annotés : `# Feature: role-based-access-control, Property {N}: {property_text}`
- Minimum 100 itérations par test de propriété (`@settings(max_examples=100)`)
