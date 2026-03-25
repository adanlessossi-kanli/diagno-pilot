# Document des Exigences

## Introduction

Cette fonctionnalité vise à améliorer la cohérence globale de l'application médicale Diagno-Pilot,
disponible sur deux plateformes : une application web (Next.js) et une application mobile (React Native / Expo).
Les améliorations couvrent les bonnes pratiques UX, le changement de langue, la navigation persistante,
la cohérence de l'authentification, la représentation visuelle adaptée à l'Afrique de l'Ouest,
le copyright dans le pied de page, et la qualité de la suite de tests.

## Glossaire

- **Application** : l'ensemble du système Diagno-Pilot, comprenant l'app web et l'app mobile.
- **App_Web** : l'application Next.js hébergée dans `apps/web`.
- **App_Mobile** : l'application React Native / Expo hébergée dans `apps/mobile`.
- **Utilisateur** : tout professionnel de santé authentifié utilisant l'Application.
- **Sélecteur_Langue** : le composant d'interface permettant de basculer entre les langues disponibles.
- **Barre_Navigation** : le composant de navigation principal affiché sur chaque page.
- **Système_Auth** : le sous-système gérant la connexion, la déconnexion et la persistance de session.
- **Registre_Images** : le module centralisé (`images.ts`) référençant toutes les images de l'Application.
- **Pied_De_Page** : la section de bas de page affichée sur chaque page de l'App_Web.
- **Suite_Tests** : l'ensemble des tests automatisés (unitaires, intégration) de l'Application.
- **Docker_Compose** : l'outil d'orchestration de conteneurs défini dans le fichier `docker-compose.yml` du projet.
- **Script_Démarrage** : le script shell ou la commande permettant de lancer l'ensemble des services de l'Application.
- **Script_Arrêt** : le script shell ou la commande permettant d'arrêter proprement l'ensemble des services de l'Application.
- **Seed** : le script d'initialisation de la base de données insérant les données de référence nécessaires au fonctionnement de l'Application.

---

## Exigences

### Exigence 1 : Bonnes pratiques UX

**User Story :** En tant qu'utilisateur, je veux une interface cohérente et accessible, afin de pouvoir utiliser l'application efficacement sans friction.

#### Critères d'acceptation

1. THE App_Web SHALL afficher un retour visuel (état de chargement) lors de toute opération asynchrone dépassant 300 ms.
2. THE App_Web SHALL afficher un message d'erreur explicite lorsqu'une opération échoue, sans exposer de détails techniques internes.
3. THE App_Mobile SHALL afficher un indicateur de chargement lors de toute opération asynchrone dépassant 300 ms.
4. THE App_Mobile SHALL afficher un message d'erreur lisible lorsqu'une opération échoue.
5. THE App_Web SHALL respecter un ratio de contraste d'au moins 4,5:1 entre le texte et son arrière-plan, conformément aux critères WCAG 2.1 AA.
6. THE App_Web SHALL utiliser des éléments HTML sémantiques (`<nav>`, `<main>`, `<footer>`, `<button>`) pour chaque section de l'interface.
7. WHEN un formulaire est soumis avec des données invalides, THE App_Web SHALL afficher un message de validation inline à côté du champ concerné.
8. WHEN un formulaire est soumis avec des données invalides, THE App_Mobile SHALL afficher un message de validation inline à côté du champ concerné.

---

### Exigence 2 : Sélecteur de langue

**User Story :** En tant qu'utilisateur, je veux pouvoir changer la langue de l'interface (français par défaut, anglais disponible), afin de consulter l'application dans la langue de mon choix.

#### Critères d'acceptation

1. THE App_Web SHALL proposer un Sélecteur_Langue visible sur chaque page de l'interface, avec le français comme langue par défaut.
2. THE App_Mobile SHALL proposer un Sélecteur_Langue accessible depuis le profil utilisateur, avec le français comme langue par défaut.
3. WHEN l'utilisateur sélectionne une langue via le Sélecteur_Langue, THE App_Web SHALL mettre à jour l'intégralité de l'interface dans la langue choisie sans rechargement complet de la page.
4. WHEN l'utilisateur sélectionne une langue via le Sélecteur_Langue, THE App_Mobile SHALL mettre à jour l'intégralité de l'interface dans la langue choisie.
5. THE App_Web SHALL conserver le choix de langue de l'utilisateur entre les sessions via un cookie ou le stockage local.
6. THE App_Mobile SHALL conserver le choix de langue de l'utilisateur entre les sessions via le stockage persistant.
7. IF la langue préférée du navigateur ou de l'appareil n'est pas supportée, THEN THE Application SHALL utiliser le français comme langue de repli.

---

### Exigence 3 : Navigation persistante

**User Story :** En tant qu'utilisateur, je veux voir le menu de navigation sur chaque page, afin de pouvoir naviguer dans l'application à tout moment.

#### Critères d'acceptation

1. THE App_Web SHALL afficher la Barre_Navigation sur chaque page accessible après authentification.
2. THE App_Mobile SHALL afficher la barre d'onglets de navigation sur chaque écran accessible après authentification.
3. WHILE l'utilisateur est authentifié, THE App_Web SHALL mettre en évidence l'élément de navigation correspondant à la page active.
4. WHILE l'utilisateur est authentifié, THE App_Mobile SHALL mettre en évidence l'onglet correspondant à l'écran actif.
5. THE App_Web SHALL afficher la Barre_Navigation de manière responsive, avec un menu hamburger sur les écrans de largeur inférieure à 768 px.
6. IF l'utilisateur n'est pas authentifié, THEN THE App_Web SHALL masquer la Barre_Navigation et rediriger vers la page de connexion.
7. IF l'utilisateur n'est pas authentifié, THEN THE App_Mobile SHALL masquer la barre d'onglets et rediriger vers l'écran de connexion.

---

### Exigence 4 : Cohérence de l'authentification

**User Story :** En tant qu'utilisateur, je veux que la connexion et la déconnexion fonctionnent de manière fiable et cohérente sur les deux plateformes, afin de ne jamais me retrouver dans un état incohérent.

#### Critères d'acceptation

1. WHEN l'utilisateur soumet des identifiants valides, THE Système_Auth SHALL établir une session authentifiée et rediriger l'utilisateur vers la page d'accueil dans un délai de 2 secondes.
2. WHEN l'utilisateur soumet des identifiants invalides, THE Système_Auth SHALL afficher un message d'erreur générique sans révéler si l'email ou le mot de passe est incorrect.
3. WHEN l'utilisateur clique sur le bouton de déconnexion, THE Système_Auth SHALL invalider la session, effacer le token d'accès et rediriger vers la page de connexion.
4. WHILE une session est active, THE Système_Auth SHALL renouveler silencieusement le token d'accès avant son expiration.
5. IF le renouvellement du token échoue, THEN THE Système_Auth SHALL déconnecter l'utilisateur et le rediriger vers la page de connexion.
6. THE App_Web SHALL conserver la session authentifiée après un rechargement de page via le cookie httpOnly.
7. THE App_Mobile SHALL conserver la session authentifiée après un redémarrage de l'application via SecureStore.
8. WHEN l'utilisateur se connecte avec le rôle `admin`, THE Système_Auth SHALL rediriger vers la page d'administration.
9. WHEN l'utilisateur se connecte avec un rôle autre que `admin`, THE Système_Auth SHALL rediriger vers la page d'accueil.

---

### Exigence 5 : Images représentatives (Afrique de l'Ouest)

**User Story :** En tant qu'utilisateur basé en Afrique de l'Ouest, je veux voir des images qui reflètent ma réalité géographique et culturelle, afin de me sentir représenté dans l'application.

#### Critères d'acceptation

1. THE Registre_Images SHALL référencer uniquement des images représentant des professionnels de santé ou des patients d'Afrique de l'Ouest avec une représentation de la race noire.
2. THE App_Web SHALL utiliser exclusivement les images définies dans le Registre_Images pour toutes les illustrations de l'interface.
3. THE App_Mobile SHALL utiliser exclusivement les images définies dans le Registre_Images pour toutes les illustrations de l'interface.
4. THE Registre_Images SHALL documenter pour chaque image : la source, la licence d'utilisation, et une description textuelle (`alt`) en français.
5. WHEN une image ne peut pas être chargée, THE Application SHALL afficher le texte alternatif (`alt`) défini dans le Registre_Images.

---

### Exigence 6 : Copyright dans le pied de page

**User Story :** En tant que propriétaire du produit, je veux que le copyright affiché dans le pied de page soit correct, afin de protéger les droits de l'organisation.

#### Critères d'acceptation

1. THE Pied_De_Page SHALL afficher le texte de copyright suivant : `© 2026 protic-togo`.
2. THE Pied_De_Page SHALL être visible sur chaque page de l'App_Web accessible après authentification.
3. THE App_Web SHALL afficher le Pied_De_Page en bas de chaque page, après le contenu principal.

---

### Exigence 7 : Qualité de la suite de tests

**User Story :** En tant que développeur, je veux que tous les tests passent sans erreurs ni avertissements et que les tests obsolètes soient supprimés, afin de maintenir une base de code saine et fiable.

#### Critères d'acceptation

1. THE Suite_Tests SHALL s'exécuter intégralement sans erreurs ni avertissements sur l'App_Web.
2. THE Suite_Tests SHALL s'exécuter intégralement sans erreurs ni avertissements sur l'App_Mobile.
3. THE Suite_Tests SHALL ne contenir aucun test référençant des composants, des routes ou des comportements supprimés ou renommés.
4. WHEN un nouveau composant est ajouté à l'Application, THE Suite_Tests SHALL inclure au moins un test couvrant son comportement principal.
5. THE Suite_Tests SHALL inclure des tests de rendu pour la Barre_Navigation vérifiant sa présence sur les pages authentifiées.
6. THE Suite_Tests SHALL inclure des tests pour le Sélecteur_Langue vérifiant le changement de langue et la persistance du choix.
7. THE Suite_Tests SHALL inclure des tests pour le Système_Auth couvrant la connexion réussie, la connexion échouée, et la déconnexion.
8. THE Suite_Tests SHALL inclure des tests pour le Pied_De_Page vérifiant l'affichage du texte `© 2026 protic-togo`.

---

### Exigence 8 : Scripts de démarrage et d'arrêt

**User Story :** En tant que développeur, je veux que les scripts de démarrage et d'arrêt de l'application s'exécutent avec succès, afin de pouvoir lancer et arrêter l'environnement de manière fiable.

#### Critères d'acceptation

1. WHEN le script de démarrage est exécuté, THE Application SHALL démarrer l'ensemble des services sans erreur.
2. WHEN le script d'arrêt est exécuté, THE Application SHALL arrêter l'ensemble des services proprement, sans processus résiduel.
3. IF le script de démarrage rencontre une erreur, THEN THE Application SHALL afficher un message d'erreur explicite indiquant le service en échec.
4. IF le script d'arrêt rencontre une erreur, THEN THE Application SHALL afficher un message d'erreur explicite indiquant le service concerné.

---

### Exigence 9 : Configuration Docker Compose

**User Story :** En tant que développeur, je veux que la configuration Docker Compose soit valide et sans erreurs, afin de pouvoir déployer l'application dans des conteneurs de manière fiable.

#### Critères d'acceptation

1. THE Application SHALL disposer d'un fichier `docker-compose.yml` valide, sans erreurs de syntaxe ni de configuration.
2. WHEN la commande `docker compose up` est exécutée, THE Application SHALL démarrer tous les services définis sans erreur.
3. WHEN la commande `docker compose down` est exécutée, THE Application SHALL arrêter et supprimer tous les conteneurs définis sans erreur.
4. IF un service Docker Compose ne peut pas démarrer, THEN THE Application SHALL journaliser un message d'erreur explicite identifiant le service en échec.
5. THE Application SHALL définir des vérifications de santé (`healthcheck`) pour chaque service critique dans le fichier `docker-compose.yml`.

---

### Exigence 10 : Seed automatique de la base de données

**User Story :** En tant que développeur, je veux que le seed de la base de données s'exécute automatiquement au démarrage de l'application, afin de disposer d'un environnement initialisé sans intervention manuelle.

#### Critères d'acceptation

1. WHEN l'Application démarre, THE Application SHALL exécuter automatiquement le script de seed de la base de données si celle-ci est vide.
2. WHEN le seed s'exécute avec succès, THE Application SHALL journaliser un message de confirmation indiquant le nombre d'enregistrements insérés.
3. IF le seed échoue, THEN THE Application SHALL journaliser un message d'erreur explicite et interrompre le démarrage.
4. THE Application SHALL garantir que le seed est idempotent : une exécution répétée ne doit pas créer de doublons ni provoquer d'erreur.
5. WHILE le seed est en cours d'exécution, THE Application SHALL empêcher l'acceptation de requêtes utilisateur jusqu'à la fin de l'initialisation.
