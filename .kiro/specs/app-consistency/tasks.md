# Plan d'implémentation : app-consistency

## Vue d'ensemble

Amélioration de la cohérence de l'application Diagno-Pilot sur les deux plateformes (App_Web et App_Mobile) : bonnes pratiques UX, sélecteur de langue, navigation persistante, authentification cohérente, images représentatives, copyright, qualité des tests, scripts d'infrastructure, Docker Compose et seed automatique.

## Tâches

- [x] 1. Nettoyer la suite de tests existante
  - Identifier et supprimer les tests référençant des composants, routes ou comportements supprimés ou renommés dans `apps/web` et `apps/mobile`
  - Vérifier que `apps/web` et `apps/mobile` ne contiennent aucun test en échec avant d'ajouter du nouveau code
  - _Exigences : 7.1, 7.2, 7.3_

- [x] 2. Créer le composant `Footer` (App_Web)
  - [x] 2.1 Créer `apps/web/src/components/Footer.tsx` affichant `© 2026 protic-togo` dans un `<footer>`
    - Utiliser les éléments HTML sémantiques (`<footer>`, `<p>`)
    - _Exigences : 6.1, 6.3, 1.6_
  - [x] 2.2 Écrire les tests unitaires pour `Footer`
    - Vérifier la présence du texte `© 2026 protic-togo`
    - Vérifier que l'élément `<footer>` est rendu
    - _Exigences : 7.4, 7.8_
  - [x] 2.3 Écrire le test de propriété P17 pour `Footer`
    - **Propriété 17 : Copyright présent sur les pages authentifiées**
    - **Valide : Exigences 6.1, 6.2**
    - Annoter : `// Feature: app-consistency, Property 17: Pour toute page auth, Footer contient © 2026 protic-togo`
    - _Exigences : 6.1, 6.2_

- [x] 3. Intégrer `NavBar` et `Footer` dans le layout principal (App_Web)
  - [x] 3.1 Modifier `apps/web/src/app/[locale]/layout.tsx` pour inclure `<NavBar locale={locale} />`, `<main>{children}</main>` et `<Footer />`
    - Vérifier que `<html lang={locale}>` est présent
    - _Exigences : 3.1, 6.2, 6.3, 1.6_
  - [x] 3.2 Écrire les tests unitaires pour la présence de `NavBar` et `Footer` dans le layout
    - Vérifier que `NavBar` est rendu sur les pages authentifiées
    - Vérifier que `Footer` est rendu sur les pages authentifiées
    - _Exigences : 7.5, 7.8_
  - [x] 3.3 Écrire le test de propriété P7 pour `NavBar`
    - **Propriété 7 : Navigation présente sur les pages authentifiées**
    - **Valide : Exigences 3.1, 3.2**
    - Annoter : `// Feature: app-consistency, Property 7: Pour toute page auth, NavBar est présente`
    - _Exigences : 3.1_
  - [x] 3.4 Écrire le test de propriété P9 pour `NavBar`
    - **Propriété 9 : Redirection vers login si non authentifié**
    - **Valide : Exigences 3.6, 3.7**
    - Annoter : `// Feature: app-consistency, Property 9: Pour tout utilisateur non-auth, NavBar masquée et redirection /login`
    - _Exigences : 3.6_

- [x] 4. Vérifier et corriger `NavBar` (App_Web)
  - [x] 4.1 Vérifier que `apps/web/src/components/NavBar.tsx` contient `<nav aria-label="Main navigation">`, le menu hamburger pour `< 768px`, et le masquage conditionnel si `!user && !isLoading`
    - Ajouter les attributs manquants si nécessaire
    - _Exigences : 1.6, 3.5, 3.6_
  - [x] 4.2 Écrire les tests unitaires pour `NavBar`
    - Tester la présence sur pages authentifiées, l'élément actif mis en évidence, le masquage si non-auth, le menu hamburger
    - _Exigences : 7.5_
  - [x] 4.3 Écrire le test de propriété P8 pour `NavBar`
    - **Propriété 8 : Élément actif mis en évidence**
    - **Valide : Exigences 3.3, 3.4**
    - Annoter : `// Feature: app-consistency, Property 8: Pour toute page active, l'élément nav correspondant a un style distinct`
    - _Exigences : 3.3_

- [x] 5. Checkpoint — Vérifier que tous les tests App_Web passent jusqu'ici
  - S'assurer que tous les tests passent, poser des questions à l'utilisateur si nécessaire.

- [x] 6. Implémenter le sélecteur de langue et la persistance i18n (App_Web)
  - [x] 6.1 Vérifier que `apps/web/src/i18n/routing.ts` (ou `request.ts`) implémente le fallback vers `fr` pour toute locale non supportée
    - Ajouter la logique de fallback si absente
    - _Exigences : 2.7_
  - [x] 6.2 Vérifier que `LanguageSwitcher` persiste le choix via cookie `NEXT_LOCALE` (durée 1 an) et met à jour l'interface sans rechargement complet
    - _Exigences : 2.1, 2.3, 2.5_
  - [x] 6.3 Écrire les tests unitaires pour `LanguageSwitcher`
    - Tester le changement de langue, la persistance du cookie, le fallback vers `fr`
    - _Exigences : 7.6_
  - [x] 6.4 Écrire le test de propriété P4 pour `LanguageSwitcher`
    - **Propriété 4 : Changement de langue met à jour l'interface**
    - **Valide : Exigences 2.3, 2.4**
    - Annoter : `// Feature: app-consistency, Property 4: Pour toute locale supportée, l'interface est mise à jour`
    - _Exigences : 2.3, 2.4_
  - [x] 6.5 Écrire le test de propriété P5 pour `LanguageSwitcher`
    - **Propriété 5 : Persistance du choix de langue (round-trip)**
    - **Valide : Exigences 2.5, 2.6**
    - Annoter : `// Feature: app-consistency, Property 5: Pour toute locale sélectionnée, elle est persistée et restaurée`
    - _Exigences : 2.5, 2.6_
  - [x] 6.6 Écrire le test de propriété P6 pour le fallback i18n
    - **Propriété 6 : Langue de repli vers le français**
    - **Valide : Exigence 2.7**
    - Créer `apps/web/src/i18n/__tests__/routing.test.ts`
    - Annoter : `// Feature: app-consistency, Property 6: Pour toute locale non supportée, la locale effective est 'fr'`
    - _Exigences : 2.7_

- [x] 7. Implémenter le sélecteur de langue (App_Mobile)
  - [x] 7.1 Ajouter un sélecteur de langue inline dans `apps/mobile/app/(tabs)/profile.tsx`
    - Utiliser `AsyncStorage` avec la clé `diagno_locale` pour persister la locale (`fr` | `en`)
    - Déclencher la mise à jour des traductions via le contexte i18n
    - Langue par défaut : `fr`
    - _Exigences : 2.2, 2.4, 2.6_
  - [x] 7.2 Écrire les tests pour le sélecteur de langue mobile
    - Vérifier la présence du sélecteur, le changement de langue, la persistance via `AsyncStorage`
    - Créer ou mettre à jour `apps/mobile/app/(tabs)/__tests__/profile.test.tsx`
    - _Exigences : 7.6_

- [x] 8. Vérifier et corriger `AuthContext` (App_Web)
  - [x] 8.1 Vérifier que `apps/web/src/contexts/AuthContext.tsx` couvre : persistance cookie httpOnly, renouvellement silencieux, redirection par rôle (`admin` → `/admin`, autre → `/`), déconnexion propre, déconnexion forcée si refresh échoue
    - Corriger ou compléter les cas manquants
    - _Exigences : 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.8, 4.9_
  - [x] 8.2 Écrire les tests unitaires pour `AuthContext` (App_Web)
    - Tester : login réussi, login échoué, logout, redirection par rôle, refresh token
    - Mettre à jour `apps/web/src/contexts/__tests__/AuthContext.test.tsx`
    - _Exigences : 7.7_
  - [x] 8.3 Écrire le test de propriété P2 pour `AuthContext`
    - **Propriété 2 : Messages d'erreur sans détails techniques**
    - **Valide : Exigences 1.2, 1.4**
    - Annoter : `// Feature: app-consistency, Property 2: Pour toute erreur, le message ne contient ni stack trace ni détail interne`
    - _Exigences : 1.2, 1.4_
  - [x] 8.4 Écrire le test de propriété P10 pour `AuthContext`
    - **Propriété 10 : Connexion réussie redirige selon le rôle**
    - **Valide : Exigences 4.1, 4.8, 4.9**
    - Annoter : `// Feature: app-consistency, Property 10: Pour tout utilisateur valide, redirection selon rôle`
    - _Exigences : 4.1, 4.8, 4.9_
  - [x] 8.5 Écrire le test de propriété P11 pour `AuthContext`
    - **Propriété 11 : Message d'erreur générique pour identifiants invalides**
    - **Valide : Exigence 4.2**
    - Annoter : `// Feature: app-consistency, Property 11: Pour tout couple email/mdp invalide, message générique sans révéler lequel est incorrect`
    - _Exigences : 4.2_
  - [x] 8.6 Écrire le test de propriété P12 pour `AuthContext`
    - **Propriété 12 : Déconnexion efface la session (round-trip)**
    - **Valide : Exigence 4.3**
    - Annoter : `// Feature: app-consistency, Property 12: Après déconnexion, token effacé et redirection /login`
    - _Exigences : 4.3_
  - [x] 8.7 Écrire le test de propriété P13 pour `AuthContext`
    - **Propriété 13 : Persistance de session après rechargement (round-trip)**
    - **Valide : Exigences 4.6, 4.7**
    - Annoter : `// Feature: app-consistency, Property 13: Après rechargement, session restaurée sans nouvelle connexion`
    - _Exigences : 4.6, 4.7_

- [x] 9. Vérifier et corriger `AuthContext` (App_Mobile)
  - [x] 9.1 Vérifier que `apps/mobile/src/contexts/AuthContext.tsx` couvre : persistance via `SecureStore`, restauration de session au démarrage, déconnexion propre
    - Corriger ou compléter les cas manquants
    - _Exigences : 4.7, 4.3_
  - [x] 9.2 Écrire les tests pour `AuthContext` mobile
    - Tester : login, logout, persistance `SecureStore`
    - Mettre à jour `apps/mobile/src/contexts/__tests__/AuthContext.test.tsx`
    - _Exigences : 7.7_

- [x] 10. Écrire le test de propriété P3 — Validation inline des formulaires
  - [x] 10.1 Écrire le test de propriété P3 dans `apps/web/src/components/__tests__/NavBar.test.tsx` ou le fichier de test du formulaire concerné
    - **Propriété 3 : Validation inline pour les formulaires invalides**
    - **Valide : Exigences 1.7, 1.8**
    - Annoter : `// Feature: app-consistency, Property 3: Pour tout formulaire invalide soumis, message de validation inline affiché`
    - _Exigences : 1.7, 1.8_
  - [x] 10.2 Écrire le test de propriété P1 pour les indicateurs de chargement
    - **Propriété 1 : Indicateur de chargement présent pour les opérations longues**
    - **Valide : Exigences 1.1, 1.3**
    - Annoter : `// Feature: app-consistency, Property 1: Pour toute opération async > 300ms, un indicateur de chargement est présent`
    - _Exigences : 1.1, 1.3_

- [x] 11. Checkpoint — Vérifier que tous les tests App_Web et App_Mobile passent
  - S'assurer que tous les tests passent, poser des questions à l'utilisateur si nécessaire.

- [x] 12. Mettre à jour le Registre d'images (`images.ts`)
  - [x] 12.1 Modifier `apps/web/src/lib/images.ts` pour que chaque entrée contienne les champs `src`, `alt` (en français), `source` et `licence`
    - Remplacer toutes les images existantes par des images représentant des professionnels de santé ou patients d'Afrique de l'Ouest (race noire)
    - _Exigences : 5.1, 5.2, 5.4_
  - [x] 12.2 Écrire les tests unitaires pour le Registre d'images
    - Vérifier que chaque entrée a `src`, `alt`, `source`, `licence` non vides
    - Créer `apps/web/src/lib/__tests__/images.test.ts`
    - _Exigences : 7.4_
  - [x] 12.3 Écrire le test de propriété P15 pour le Registre d'images
    - **Propriété 15 : Intégrité structurelle du Registre d'images**
    - **Valide : Exigences 5.1, 5.4**
    - Annoter : `// Feature: app-consistency, Property 15: Pour toute entrée du registre, src/alt/source/licence présents et non vides`
    - _Exigences : 5.1, 5.4_
  - [x] 12.4 Écrire le test de propriété P16 pour le fallback alt des images
    - **Propriété 16 : Texte alternatif affiché si image non chargeable**
    - **Valide : Exigence 5.5**
    - Annoter : `// Feature: app-consistency, Property 16: Pour toute image avec src invalide, le texte alt est affiché`
    - _Exigences : 5.5_

- [x] 13. Mettre à jour `docker-compose.yml` avec les healthchecks
  - [x] 13.1 Ajouter les healthchecks pour les services `mongo`, `backend` et `frontend` dans `docker-compose.yml` selon la configuration définie dans le design
    - `mongo` : `mongosh --eval "db.adminCommand('ping').ok"`, interval 5s, retries 12
    - `backend` : `curl -f http://localhost:8000/health`, interval 10s, retries 5
    - `frontend` : `curl -f http://localhost:3000`, interval 10s, retries 5
    - _Exigences : 9.1, 9.5_
  - [x] 13.2 Vérifier que le service `seed` dépend du healthcheck de `mongo` (`depends_on: mongo: condition: service_healthy`)
    - Vérifier que `backend` dépend également du healthcheck de `mongo`
    - _Exigences : 9.2, 10.5_

- [x] 14. Améliorer les scripts `start.sh` / `stop.sh`
  - [x] 14.1 Modifier `start.sh` pour capturer les erreurs de `docker compose up --build -d`, afficher le service en échec et retourner le code 1 en cas d'erreur
    - _Exigences : 8.1, 8.3_
  - [x] 14.2 Modifier `stop.sh` pour capturer les erreurs de `docker compose down`, afficher le service concerné et retourner le code 1 en cas d'erreur
    - _Exigences : 8.2, 8.4_
  - [x] 14.3 Vérifier que `start.bat` et `stop.bat` ont un comportement équivalent sur Windows
    - _Exigences : 8.1, 8.2_

- [x] 15. Vérifier et corriger `scripts/seed.py`
  - [x] 15.1 Vérifier que `scripts/seed.py` utilise `find_one` par email avant tout `insert_one` pour garantir l'idempotence
    - Ajouter un log de confirmation avec le nombre d'enregistrements insérés/ignorés
    - Retourner un code non nul en cas d'échec
    - _Exigences : 10.1, 10.2, 10.3, 10.4_
  - [x] 15.2 Écrire le test de propriété P18 pour le seed
    - **Propriété 18 : Seed idempotent**
    - **Valide : Exigences 10.1, 10.4**
    - Créer `backend/tests/test_seed.py` avec `hypothesis`
    - Annoter : `# Feature: app-consistency, Property 18: Pour toute DB contenant déjà les utilisateurs, seed ne crée aucun doublon`
    - _Exigences : 10.1, 10.4_

- [x] 16. Checkpoint final — Vérifier que l'ensemble des tests passent
  - S'assurer que tous les tests (App_Web, App_Mobile, Backend) passent sans erreurs ni avertissements, poser des questions à l'utilisateur si nécessaire.

## Notes

- Les tâches marquées `*` sont optionnelles et peuvent être ignorées pour un MVP rapide
- Chaque tâche référence les exigences spécifiques pour la traçabilité
- Les tests de propriétés utilisent `fast-check` (App_Web) et `hypothesis` (Backend Python)
- Les tests unitaires utilisent `Vitest + Testing Library` (App_Web) et `Jest + Testing Library React Native` (App_Mobile)
- Les propriétés P14 (déconnexion forcée si refresh échoue) est couverte par les tests de P12/P13 dans `AuthContext.test.tsx`
