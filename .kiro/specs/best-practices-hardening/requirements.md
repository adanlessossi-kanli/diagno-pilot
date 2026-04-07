# Document d'exigences — Durcissement des bonnes pratiques

## Introduction

Ce document spécifie les exigences de durcissement sécurité et bonnes pratiques pour l'application Diagno-Pilot. Il couvre 13 axes d'amélioration identifiés lors d'une revue de sécurité : isolation des conteneurs Docker, authentification des services d'infrastructure, restriction des accès réseau, en-têtes de sécurité HTTP, chiffrement conforme HIPAA, optimisation des connexions HTTP et validation des entrées JSON-RPC.

## Glossaire

- **Backend_Dockerfile** : Le fichier `backend/Dockerfile` qui construit l'image Docker du serveur FastAPI
- **Frontend_Dockerfile** : Le fichier `apps/web/Dockerfile` qui construit l'image Docker du frontend Next.js
- **Docker_Compose** : Le fichier `docker-compose.yml` orchestrant les 14 services de l'application
- **Config_Module** : Le module `backend/core/config.py` contenant la classe `Settings` (Pydantic)
- **Security_Headers_Middleware** : Le middleware `backend/core/security_headers.py` injectant les en-têtes HTTP de sécurité
- **Encryption_Service** : Le service `backend/services/encryption_service.py` assurant le chiffrement des champs PHI
- **LLM_Client** : La classe `_LLMClient` dans `backend/services/llm_router.py` effectuant les appels HTTP vers les LLM
- **Base_MCP_Server** : La classe `BaseMCPServer` dans `backend/agents/mcp_servers/base_server.py` gérant le protocole JSON-RPC 2.0
- **MCP_Agent** : Un des 4 serveurs agents spécialistes (Épidémiologie, Symptomatologie, Laboratoire, Traitement)
- **Grafana_Service** : Le service Grafana défini dans Docker_Compose pour la visualisation des métriques
- **Redis_Service** : Le service Redis défini dans Docker_Compose pour le cache et le rate limiting
- **MongoDB_Service** : Le service MongoDB défini dans Docker_Compose pour la base de données
- **PHI** : Protected Health Information — données de santé protégées au sens HIPAA
- **CSP** : Content-Security-Policy — en-tête HTTP contrôlant les sources de contenu autorisées
- **JSON-RPC_Envelope** : Structure JSON contenant les champs `jsonrpc`, `method`, `params` et `id` selon la spécification JSON-RPC 2.0

## Exigences

### Exigence 1 : Exécution non-root du conteneur backend

**User Story :** En tant qu'administrateur système, je veux que le conteneur backend s'exécute avec un utilisateur non-root, afin de limiter l'impact d'une éventuelle compromission du conteneur.

#### Critères d'acceptation

1. THE Backend_Dockerfile SHALL créer un utilisateur système dédié nommé `appuser` avec un UID fixe (par exemple 1001) et sans shell de connexion
2. THE Backend_Dockerfile SHALL définir une directive `USER appuser` après l'installation des dépendances et la copie du code source
3. WHEN le conteneur backend démarre, THE processus uvicorn SHALL s'exécuter sous l'identité `appuser` (UID non-zéro)

### Exigence 2 : Suppression du flag --reload en production

**User Story :** En tant qu'administrateur système, je veux que le conteneur backend n'utilise pas le flag `--reload` de uvicorn par défaut, afin d'éviter la surveillance inutile du système de fichiers en production.

#### Critères d'acceptation

1. THE Backend_Dockerfile SHALL définir un CMD sans le flag `--reload` ni `--reload-include`
2. THE Docker_Compose SHALL permettre de surcharger le CMD du service backend en développement pour ajouter `--reload` via la directive `command`
3. WHEN le conteneur backend démarre en mode production, THE processus uvicorn SHALL fonctionner sans rechargement automatique

### Exigence 3 : Build multi-étapes du frontend

**User Story :** En tant qu'administrateur système, je veux que le Dockerfile frontend utilise un build multi-étapes, afin de produire une image de production optimisée avec `next build` et `next start`.

#### Critères d'acceptation

1. THE fichier `apps/web/next.config.ts` SHALL définir `output: 'standalone'` dans la configuration Next.js afin que `npm run build` produise un dossier `.next/standalone` autonome
2. THE Frontend_Dockerfile SHALL définir une étape `builder` qui exécute `npm run build` pour générer les artefacts de production Next.js (standalone)
3. THE Frontend_Dockerfile SHALL définir une étape finale qui copie uniquement `.next/standalone`, `.next/static` et `public`, et exécute `node server.js` sur le port 3000
4. THE Frontend_Dockerfile SHALL conserver la possibilité d'utiliser `npm run dev` en développement via une surcharge du CMD dans Docker_Compose
5. THE Frontend_Dockerfile SHALL créer et utiliser un utilisateur non-root `nextuser` dans l'étape finale

### Exigence 4 : Authentification MongoDB

**User Story :** En tant qu'administrateur système, je veux que MongoDB soit configuré avec des identifiants d'authentification, afin de protéger la base de données contre les accès non autorisés.

#### Critères d'acceptation

1. THE Docker_Compose SHALL définir les variables d'environnement `MONGO_INITDB_ROOT_USERNAME` et `MONGO_INITDB_ROOT_PASSWORD` pour le service MongoDB, référençant des variables d'environnement du fichier `.env`
2. THE Docker_Compose SHALL inclure les identifiants MongoDB dans l'URI `MONGODB_URI` transmise aux services backend et agents
3. THE Config_Module SHALL documenter les variables `MONGO_USERNAME` et `MONGO_PASSWORD` dans le fichier `.env.example`, ainsi que le `MONGODB_URI` mis à jour avec les identifiants
4. IF les variables `MONGO_INITDB_ROOT_USERNAME` ou `MONGO_INITDB_ROOT_PASSWORD` sont absentes du fichier `.env`, THEN THE Docker_Compose SHALL utiliser des valeurs par défaut de développement (`diagno_dev` / `diagno_dev_pass`)
5. THE documentation (README ou `.env.example`) SHALL mentionner que les environnements de développement existants doivent supprimer le volume MongoDB (`docker volume rm diagno-pilot_mongo_data`) avant le premier démarrage avec authentification, car `MONGO_INITDB_ROOT_USERNAME` n'est exécuté que sur un volume vierge

### Exigence 5 : Authentification Redis

**User Story :** En tant qu'administrateur système, je veux que Redis soit protégé par un mot de passe, afin d'empêcher les accès non autorisés au cache et aux données de session.

#### Critères d'acceptation

1. THE Docker_Compose SHALL configurer le service Redis avec l'argument `--requirepass` référençant une variable d'environnement `REDIS_PASSWORD`
2. THE Docker_Compose SHALL inclure le mot de passe dans l'URI Redis (`redis://:password@redis:6379/0`) transmise au service backend
3. THE Config_Module SHALL documenter la variable `REDIS_PASSWORD` et le `REDIS_URL` authentifié dans le fichier `.env.example`
4. IF la variable `REDIS_PASSWORD` est absente du fichier `.env`, THEN THE Docker_Compose SHALL utiliser une valeur par défaut de développement (`diagno_redis_dev`)
5. THE Config_Module SHALL mettre à jour la valeur par défaut de `REDIS_URL` dans `backend/core/config.py` pour inclure le mot de passe par défaut dev (`redis://:diagno_redis_dev@localhost:6379/0`), afin d'éviter les échecs de connexion silencieux

### Exigence 6 : Restriction de l'accès anonyme Grafana

**User Story :** En tant qu'administrateur système, je veux que Grafana ne donne pas le rôle Admin aux utilisateurs anonymes, afin de limiter les risques en cas d'exposition accidentelle du port.

#### Critères d'acceptation

1. THE Docker_Compose SHALL configurer la variable `GF_AUTH_ANONYMOUS_ORG_ROLE` du service Grafana avec la valeur `Viewer` au lieu de `Admin`
2. THE Docker_Compose SHALL ajouter un commentaire indiquant de désactiver l'accès anonyme (`GF_AUTH_ANONYMOUS_ENABLED=false`) en production

### Exigence 7 : Suppression de l'exposition des ports MCP agents

**User Story :** En tant qu'administrateur système, je veux que les ports des serveurs MCP agents ne soient pas exposés sur l'hôte, afin que ces services internes communiquent uniquement via le réseau Docker.

#### Critères d'acceptation

1. THE Docker_Compose SHALL supprimer les directives `ports` des services `agent-epidemiology`, `agent-symptomatology`, `agent-lab` et `agent-treatment`
2. WHEN les services MCP agents sont démarrés, THE Docker_Compose SHALL permettre la communication entre le service backend et les agents uniquement via le réseau Docker interne
3. THE Docker_Compose SHALL conserver les healthchecks des agents en utilisant `localhost` à l'intérieur du conteneur

### Exigence 8 : Valeur par défaut restrictive pour ALLOWED_ORIGINS

**User Story :** En tant que développeur, je veux que la valeur par défaut de `ALLOWED_ORIGINS` soit restrictive, afin d'éviter qu'un wildcard `*` ne fuite dans un environnement de staging ou de production.

#### Critères d'acceptation

1. THE Config_Module SHALL définir la valeur par défaut de `ALLOWED_ORIGINS` à `http://localhost:3000` au lieu de `*`
2. THE Config_Module SHALL conserver la validation de production existante qui rejette `*` et les chaînes vides
3. THE fichier `.env.example` SHALL documenter `ALLOWED_ORIGINS` avec la valeur `http://localhost:3000` comme exemple par défaut

### Exigence 9 : Ajout de l'en-tête Content-Security-Policy

**User Story :** En tant que responsable sécurité, je veux que le middleware de sécurité backend injecte un en-tête `Content-Security-Policy` restrictif sur les réponses API, afin de renforcer la défense en profondeur même si les réponses sont consommées directement.

> **Note :** Le frontend Next.js injecte déjà son propre en-tête CSP via `next.config.ts` (avec `img-src 'self' data: https://images.unsplash.com` et des directives adaptées au dev/prod). L'en-tête CSP backend s'applique uniquement aux réponses API directes (non proxifiées par Next.js) et ne doit pas entrer en conflit avec la politique frontend.

#### Critères d'acceptation

1. THE Security_Headers_Middleware SHALL ajouter un en-tête `Content-Security-Policy` avec au minimum les directives `default-src 'self'`, `script-src 'self'`, `style-src 'self' 'unsafe-inline'` et `img-src 'self' data:`
2. THE Security_Headers_Middleware SHALL rendre la valeur CSP configurable via une variable d'environnement `CSP_POLICY` dans le Config_Module
3. IF la variable `CSP_POLICY` est définie, THEN THE Security_Headers_Middleware SHALL utiliser cette valeur au lieu de la politique par défaut
4. THE Security_Headers_Middleware SHALL appliquer l'en-tête CSP dans tous les environnements (développement, staging, production)

### Exigence 10 : Chiffrement AES-256-GCM pour les données PHI

**User Story :** En tant que responsable conformité HIPAA, je veux que le service de chiffrement utilise AES-256-GCM au lieu de Fernet (AES-128-CBC), afin que la documentation et l'implémentation soient alignées sur l'exigence AES-256.

#### Critères d'acceptation

1. THE Encryption_Service SHALL utiliser l'algorithme AES-256-GCM via le module `cryptography.hazmat.primitives.ciphers.aead.AESGCM` pour le chiffrement des champs PHI
2. THE Encryption_Service SHALL générer un nonce aléatoire de 12 octets (96 bits) pour chaque opération de chiffrement
3. THE Encryption_Service SHALL accepter une clé de 32 octets (256 bits) encodée en base64 URL-safe
4. THE Encryption_Service SHALL conserver la compatibilité descendante en tentant le déchiffrement Fernet si le déchiffrement AES-256-GCM échoue, afin de supporter la migration des données existantes
5. THE Encryption_Service SHALL conserver le mécanisme de rotation de clés existant
6. FOR ALL chaînes de texte valides, le chiffrement suivi du déchiffrement avec la même clé SHALL produire la chaîne originale (propriété aller-retour)
7. THE documentation (`.env.example` ou docstring) SHALL inclure la commande de génération de clé AES-256-GCM : `python -c "import os, base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"`

### Exigence 11 : Réutilisation du client HTTP dans _LLMClient

**User Story :** En tant que développeur, je veux que `_LLMClient` réutilise une instance unique de `httpx.AsyncClient`, afin de bénéficier du pooling de connexions et de réduire la latence des appels LLM.

#### Critères d'acceptation

1. THE LLM_Client SHALL créer une instance `httpx.AsyncClient` dans son constructeur `__init__` avec le timeout configuré
2. THE LLM_Client SHALL réutiliser cette instance pour toutes les requêtes HTTP au lieu d'en créer une nouvelle à chaque appel
3. THE LLM_Client SHALL exposer une méthode `close()` asynchrone pour fermer proprement le client HTTP
4. WHEN le LLMRouter est détruit ou l'application s'arrête, THE LLM_Client SHALL fermer le client HTTP pour libérer les connexions

### Exigence 12 : Validation de l'enveloppe JSON-RPC dans Base_MCP_Server

**User Story :** En tant que développeur, je veux que `BaseMCPServer` valide rigoureusement l'enveloppe JSON-RPC 2.0 avant le dispatch, afin de rejeter les requêtes malformées avec des codes d'erreur appropriés.

> **Note :** Le code existant valide déjà `jsonrpc != "2.0"` et `not method` (couvre `None` et chaîne vide). Les validations manquantes sont : vérification du type de `method` (un entier passerait le check `not method`), validation du type de `params`, et validation du type de `id`.

#### Critères d'acceptation

1. WHEN une requête JSON-RPC est reçue avec un champ `jsonrpc` différent de `"2.0"`, THEN THE Base_MCP_Server SHALL retourner une erreur JSON-RPC avec le code -32600 (Invalid Request) *(existant — à conserver)*
2. WHEN une requête JSON-RPC est reçue avec un champ `method` absent ou de type non-chaîne, THEN THE Base_MCP_Server SHALL retourner une erreur JSON-RPC avec le code -32600 (Invalid Request) *(renforcement : ajouter `isinstance(method, str)` au check existant)*
3. WHEN une requête JSON-RPC est reçue avec un champ `params` présent mais de type différent de `dict` ou `list`, THEN THE Base_MCP_Server SHALL retourner une erreur JSON-RPC avec le code -32602 (Invalid Params) *(nouveau)*
4. WHEN une requête JSON-RPC est reçue avec un champ `id` de type non valide (ni chaîne, ni entier, ni null), THEN THE Base_MCP_Server SHALL retourner une erreur JSON-RPC avec le code -32600 (Invalid Request) *(nouveau)*
5. FOR ALL requêtes JSON-RPC valides (jsonrpc="2.0", method=chaîne, params=dict|list|absent, id=chaîne|entier|null), THE Base_MCP_Server SHALL dispatcher la requête au handler approprié sans erreur de validation

### Exigence 13 : Ajout des en-têtes Referrer-Policy et Permissions-Policy

**User Story :** En tant que responsable sécurité, je veux que le middleware de sécurité injecte les en-têtes `Referrer-Policy` et `Permissions-Policy`, afin de renforcer la défense en profondeur de l'application médicale.

#### Critères d'acceptation

1. THE Security_Headers_Middleware SHALL ajouter un en-tête `Referrer-Policy` avec la valeur `strict-origin-when-cross-origin`
2. THE Security_Headers_Middleware SHALL ajouter un en-tête `Permissions-Policy` désactivant les fonctionnalités non utilisées : `camera=(), microphone=(), geolocation=(), payment=()`
3. THE Security_Headers_Middleware SHALL appliquer ces en-têtes dans tous les environnements (développement, staging, production)

### Exigence 14 : Mise à jour de la documentation

**User Story :** En tant que développeur ou administrateur système, je veux que la documentation reflète tous les changements de durcissement, afin de pouvoir configurer et déployer l'application correctement.

#### Critères d'acceptation

1. THE fichier `docs/configuration.md` SHALL documenter les nouvelles variables d'environnement (`MONGO_USERNAME`, `MONGO_PASSWORD`, `REDIS_PASSWORD`, `CSP_POLICY`) et mettre à jour les valeurs par défaut modifiées (`ALLOWED_ORIGINS`, `REDIS_URL`)
2. THE fichier `docs/deployment.md` SHALL refléter la suppression des ports MCP agents, l'authentification MongoDB/Redis, et inclure une section de migration pour les environnements existants
3. THE fichier `docs/hipaa-compliance.md` SHALL documenter la migration de Fernet vers AES-256-GCM, le nouveau format de clé, le format ciphertext, et le fallback Fernet
4. THE fichier `README.md` SHALL mettre à jour les exemples de configuration avec les identifiants MongoDB/Redis et supprimer les ports MCP agents du tableau des services
5. THE fichier `docs/developer-guide.md` SHALL documenter les en-têtes de sécurité ajoutés (CSP, Referrer-Policy, Permissions-Policy) et la validation JSON-RPC renforcée
