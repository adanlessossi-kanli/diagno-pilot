# Bugfix Requirements Document

## Introduction

Le système RBAC (Role-Based Access Control) de Diagno-Pilot présente plusieurs incohérences entre les règles d'accès définies et leur application effective dans le frontend et le backend. Les règles attendues sont :

- **Guest** (non connecté) : accès à l'assistant Q&A uniquement ; lien "Se connecter" visible dans la NavBar ; redirigé vers la connexion pour toute route protégée
- **Infirmière** : accès à Q&A Assistant, Chat (authentifié), Diagnostic guidé, et Patients
- **Médecin** : accès à Q&A, Chat, Diagnostic guidé, Patients, Documents + possibilité de créer des comptes infirmière + upload de documents
- **Admin** : tous les droits + création de comptes médecin + menu d'administration exclusif

Les bugs identifiés sont : (1) la NavBar affiche des liens non autorisés selon le rôle, (2) la page Documents est accessible à tous les rôles authentifiés sans garde de rôle, (3) il n'existe pas de formulaire de création d'infirmière pour le médecin, (4) il n'existe pas de formulaire de création de médecin pour l'admin, (5) le backend `/api/v1/documents/upload` n'autorise que `admin` alors que `medecin` devrait pouvoir uploader, (6) le guest ne voit pas de lien "Se connecter" dans la NavBar, (7) l'infirmière ne peut pas accéder au Chat authentifié ni à l'endpoint `/api/v1/chat`.

---

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN un utilisateur avec le rôle `infirmière` est connecté THEN le système affiche dans la NavBar les liens Documents et Chat en plus de Diagnostic et Patients

1.2 WHEN un utilisateur avec le rôle `infirmière` navigue vers `/[locale]/documents` THEN le système affiche la page Documents sans redirection ni message d'accès refusé

1.3 WHEN un utilisateur avec le rôle `medecin` tente d'uploader un document via `POST /api/v1/documents/upload` THEN le système retourne HTTP 403 (Forbidden)

1.4 WHEN un utilisateur avec le rôle `medecin` est connecté THEN le système ne propose aucun formulaire ni interface pour créer un compte infirmière

1.5 WHEN un utilisateur avec le rôle `admin` est connecté THEN le système ne propose aucun formulaire dédié pour créer un compte médecin (le panneau admin permet la création générique mais sans flux spécifique médecin)

1.6 WHEN un utilisateur avec le rôle `infirmière` est connecté THEN le système affiche le lien Documents dans la NavBar alors que l'infirmière ne devrait pas avoir accès aux documents

1.7 WHEN un utilisateur non authentifié (guest) consulte la NavBar THEN le système n'affiche aucun lien "Se connecter" permettant d'accéder à la page de connexion

1.8 WHEN un utilisateur avec le rôle `infirmière` envoie une requête à `POST /api/v1/chat` THEN le système retourne HTTP 403 (Forbidden) alors que l'infirmière devrait pouvoir utiliser le Chat authentifié

### Expected Behavior (Correct)

2.1 WHEN un utilisateur avec le rôle `infirmière` est connecté THEN le système SHALL afficher dans la NavBar uniquement les liens : Q&A, Chat, Diagnostic guidé, Patients

2.2 WHEN un utilisateur avec le rôle `infirmière` navigue vers `/[locale]/documents` THEN le système SHALL rediriger l'utilisateur vers la page d'accueil avec un message d'accès refusé

2.3 WHEN un utilisateur avec le rôle `medecin` tente d'uploader un document via `POST /api/v1/documents/upload` THEN le système SHALL autoriser la requête et retourner HTTP 201

2.4 WHEN un utilisateur avec le rôle `medecin` est connecté THEN le système SHALL proposer un formulaire de création de compte infirmière accessible depuis son interface

2.5 WHEN un utilisateur avec le rôle `admin` est connecté THEN le système SHALL proposer un formulaire dédié pour créer un compte médecin depuis le panneau d'administration

2.6 WHEN un utilisateur avec le rôle `infirmière` est connecté THEN le système SHALL ne pas afficher le lien Documents dans la NavBar

2.7 WHEN un utilisateur avec le rôle `medecin` est connecté THEN le système SHALL afficher dans la NavBar les liens : Q&A, Chat, Diagnostic guidé, Patients, Documents

2.8 WHEN un utilisateur non authentifié (guest) consulte la NavBar THEN le système SHALL afficher un lien "Se connecter" pointant vers `/[locale]/login`

2.9 WHEN un utilisateur avec le rôle `medecin` soumet le formulaire de création d'infirmière via `POST /api/v1/medecin/users` THEN le système SHALL créer le compte avec le rôle `infirmière` et retourner HTTP 201 ; si le rôle demandé n'est pas `infirmière` THEN le système SHALL retourner HTTP 403

2.10 WHEN un utilisateur avec le rôle `infirmière` envoie une requête à `POST /api/v1/chat` THEN le système SHALL autoriser la requête et retourner une réponse valide

### Unchanged Behavior (Regression Prevention)

3.1 WHEN un utilisateur non authentifié accède à `/qa` ou `/[locale]/qa` THEN le système SHALL CONTINUE TO afficher l'assistant Q&A sans redirection vers la connexion

3.2 WHEN un utilisateur non authentifié accède à toute route protégée autre que `/qa` THEN le système SHALL CONTINUE TO rediriger vers `/[locale]/login`

3.3 WHEN un utilisateur avec le rôle `admin` accède à `/[locale]/admin` THEN le système SHALL CONTINUE TO afficher le panneau d'administration complet

3.4 WHEN un utilisateur avec un rôle autre que `admin` tente d'accéder à `/[locale]/admin` THEN le système SHALL CONTINUE TO rediriger vers la page d'accueil

3.5 WHEN un utilisateur avec le rôle `medecin` accède aux pages Diagnostic, Patients ou Chat THEN le système SHALL CONTINUE TO autoriser l'accès sans restriction

3.6 WHEN un utilisateur avec le rôle `admin` accède aux endpoints `/api/v1/patients`, `/api/v1/diagnose`, `/api/v1/chat` THEN le système SHALL CONTINUE TO autoriser les requêtes

3.7 WHEN un utilisateur avec le rôle `medecin` ou `infirmière` envoie une requête à `/api/v1/patients`, `/api/v1/diagnose`, `/api/v1/chat` THEN le système SHALL CONTINUE TO autoriser les requêtes

3.8 WHEN un utilisateur avec le rôle `admin` utilise le panneau d'administration (gestion utilisateurs, statistiques, audit, protocoles) THEN le système SHALL CONTINUE TO fonctionner de manière identique

3.9 WHEN un token JWT contient le rôle `pharmacien` (rôle hérité) THEN le système SHALL CONTINUE TO traiter ce rôle avec les permissions `guest`
