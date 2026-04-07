# Plan d'implémentation : Durcissement des bonnes pratiques

## Vue d'ensemble

Renforcement sécurité et bonnes pratiques de Diagno-Pilot en 13 axes : isolation Docker (non-root, multi-stage, suppression --reload, ports MCP), authentification infrastructure (MongoDB, Redis, Grafana), en-têtes HTTP (CSP, Referrer-Policy, Permissions-Policy), et code applicatif (AES-256-GCM, connection pooling HTTP, validation JSON-RPC). Les tâches sont ordonnées par dépendance : infrastructure Docker d'abord, puis configuration applicative, puis code métier, puis tests.

## Tâches

- [x] 1. Durcir les Dockerfiles backend et frontend
  - [x] 1.1 Modifier `backend/Dockerfile` pour exécution non-root et suppression de --reload
    - Créer un utilisateur système `appuser` (UID 1001, sans shell) avec `adduser`
    - Ajouter `USER appuser` après le COPY du code source
    - Remplacer le CMD par `["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]` (sans `--reload`)
    - _Exigences : 1.1, 1.2, 1.3, 2.1, 2.3_

  - [x] 1.2 Réécrire `apps/web/Dockerfile` en build multi-étapes avec utilisateur non-root
    - Ajouter `output: 'standalone'` dans `apps/web/next.config.ts` (dans l'objet `nextConfig`) pour que `npm run build` produise `.next/standalone`
    - Étape `deps` : copier les manifests et exécuter `npm ci`
    - Étape `builder` : copier les sources et exécuter `npm run build`
    - Étape `runner` : copier `.next/standalone`, `.next/static`, `public` ; créer `nextuser` (UID 1001) ; CMD `["node", "server.js"]`
    - _Exigences : 3.1, 3.2, 3.3, 3.5_

  - [x] 1.3 Mettre à jour `docker-compose.yml` pour surcharger les CMD en développement
    - Ajouter `command: uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload --reload-include *.py` au service backend
    - Ajouter `command: npm run dev` au service frontend avec les volumes de sources existants
    - _Exigences : 2.2, 3.3_

- [x] 2. Configurer l'authentification infrastructure dans Docker Compose
  - [x] 2.1 Ajouter l'authentification MongoDB
    - Ajouter `MONGO_INITDB_ROOT_USERNAME` et `MONGO_INITDB_ROOT_PASSWORD` au service `mongo` avec valeurs par défaut dev
    - Mettre à jour `MONGODB_URI` dans les services `backend`, `seed`, et les 4 agents pour inclure les identifiants (`mongodb://user:pass@mongo:27017/diagno_pilot?authSource=admin`)
    - Ajouter un commentaire dans `docker-compose.yml` indiquant que les volumes existants doivent être supprimés (`docker compose down -v`) avant le premier démarrage avec auth
    - _Exigences : 4.1, 4.2, 4.4, 4.5_

  - [x] 2.2 Ajouter l'authentification Redis
    - Ajouter `command: redis-server --requirepass ${REDIS_PASSWORD:-diagno_redis_dev}` au service Redis
    - Mettre à jour `REDIS_URL` du service backend pour inclure le mot de passe (`redis://:password@redis:6379/0`)
    - Mettre à jour le healthcheck Redis avec `REDISCLI_AUTH`
    - _Exigences : 5.1, 5.2, 5.4_

  - [x] 2.3 Restreindre Grafana et supprimer les ports MCP agents
    - Changer `GF_AUTH_ANONYMOUS_ORG_ROLE` de `Admin` à `Viewer`
    - Ajouter un commentaire pour désactiver l'accès anonyme en production
    - Supprimer les directives `ports` des 4 services agents MCP
    - Conserver les healthchecks internes des agents
    - _Exigences : 6.1, 6.2, 7.1, 7.2, 7.3_

  - [x] 2.4 Mettre à jour `.env.example` avec les nouvelles variables
    - Ajouter `MONGO_USERNAME`, `MONGO_PASSWORD`, `REDIS_PASSWORD` avec valeurs par défaut dev
    - Mettre à jour `MONGODB_URI` pour inclure les identifiants (`mongodb://diagno_dev:diagno_dev_pass@mongo:27017/diagno_pilot?authSource=admin`)
    - Ajouter `REDIS_URL` avec le format authentifié (`redis://:diagno_redis_dev@redis:6379/0`)
    - Mettre à jour `ALLOWED_ORIGINS` à `http://localhost:3000`
    - Ajouter `CSP_POLICY` avec la politique par défaut
    - Ajouter un commentaire sur la migration des volumes MongoDB existants
    - Ajouter la commande de génération de clé AES-256-GCM dans la section HIPAA
    - _Exigences : 4.3, 4.5, 5.3, 8.3, 10.7_

- [x] 3. Point de contrôle — Vérifier la configuration Docker
  - Vérifier que les Dockerfiles et docker-compose.yml sont syntaxiquement corrects. Demander à l'utilisateur si des questions se posent.

- [x] 4. Renforcer la configuration applicative et les en-têtes HTTP
  - [x] 4.1 Modifier `backend/core/config.py` pour ALLOWED_ORIGINS, CSP_POLICY et REDIS_URL
    - Changer la valeur par défaut de `ALLOWED_ORIGINS` de `"*"` à `"http://localhost:3000"`
    - Ajouter le champ `CSP_POLICY: str` avec la politique CSP par défaut
    - Mettre à jour la valeur par défaut de `REDIS_URL` de `"redis://localhost:6379/0"` à `"redis://:diagno_redis_dev@localhost:6379/0"`
    - _Exigences : 5.5, 8.1, 8.2, 9.2_

  - [x] 4.2 Ajouter CSP, Referrer-Policy et Permissions-Policy dans `backend/core/security_headers.py`
    - Ajouter l'en-tête `Content-Security-Policy` avec la valeur de `settings.CSP_POLICY` (s'applique aux réponses API uniquement — le frontend Next.js a sa propre CSP dans `next.config.ts`)
    - Ajouter l'en-tête `Referrer-Policy: strict-origin-when-cross-origin`
    - Ajouter l'en-tête `Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=()`
    - Ces en-têtes doivent être appliqués dans tous les environnements
    - _Exigences : 9.1, 9.3, 9.4, 13.1, 13.2, 13.3_

  - [x] 4.3 Écrire les tests property-based pour les en-têtes de sécurité
    - **Propriété 1 : Complétude des en-têtes de sécurité**
    - Utiliser `hypothesis.strategies.text()` pour générer des chemins de requête
    - Vérifier que chaque réponse contient `Content-Security-Policy`, `Referrer-Policy`, et `Permissions-Policy` avec les valeurs attendues
    - **Valide : Exigences 9.1, 13.1, 13.2**

  - [x] 4.4 Écrire les tests unitaires pour ALLOWED_ORIGINS et CSP configurable
    - Vérifier que la valeur par défaut de `ALLOWED_ORIGINS` est `http://localhost:3000`
    - Vérifier que la validation production rejette toujours `*`
    - Vérifier qu'une valeur custom de `CSP_POLICY` est utilisée dans l'en-tête
    - _Exigences : 8.1, 8.2, 9.2, 9.3_

- [x] 5. Migrer le chiffrement vers AES-256-GCM
  - [x] 5.1 Refactorer `backend/services/encryption_service.py` pour AES-256-GCM
    - Remplacer `cryptography.fernet.Fernet` par `cryptography.hazmat.primitives.ciphers.aead.AESGCM`
    - Accepter une clé de 32 octets encodée en base64 URL-safe (format différent des clés Fernet — voir commande de génération dans le design)
    - Générer un nonce aléatoire de 12 octets pour chaque chiffrement
    - Format ciphertext : `base64url(nonce[12] || ciphertext+tag)`
    - Conserver le fallback Fernet pour le déchiffrement des données existantes (les tokens Fernet commencent par `gAAAAA`)
    - Conserver le mécanisme de rotation de clés (stocker la clé précédente AESGCM + l'ancienne Fernet pour le déchiffrement)
    - Interface publique inchangée : `encrypt_field`, `decrypt_field`, `encrypt_phi_fields`, `decrypt_phi_fields`, `rotate_key`
    - Ajouter un docstring documentant la commande de génération de clé : `python -c "import os, base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"`
    - _Exigences : 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7_

  - [x] 5.2 Écrire le test property-based pour l'aller-retour AES-256-GCM
    - **Propriété 2 : Aller-retour du chiffrement AES-256-GCM**
    - Utiliser `hypothesis.strategies.text()` pour générer des plaintexts
    - Vérifier que `decrypt_field(encrypt_field(plaintext)) == plaintext`
    - **Valide : Exigence 10.6**

  - [x] 5.3 Écrire le test property-based pour l'unicité des nonces
    - **Propriété 3 : Unicité des nonces AES-256-GCM**
    - Utiliser `hypothesis.strategies.text()` pour générer des plaintexts
    - Vérifier que deux chiffrements successifs de la même chaîne produisent des ciphertexts différents
    - **Valide : Exigence 10.2**

  - [x] 5.4 Écrire le test property-based pour la rotation de clé
    - **Propriété 4 : Rotation de clé préserve le déchiffrement**
    - Utiliser `hypothesis.strategies.text()` pour générer des plaintexts
    - Chiffrer avec clé A, effectuer `rotate_key(clé B)`, vérifier que le déchiffrement réussit
    - **Valide : Exigence 10.5**

  - [x] 5.5 Écrire les tests unitaires pour la compatibilité Fernet et le format ciphertext
    - Chiffrer avec l'ancien Fernet, déchiffrer avec le nouveau service AES-GCM (fallback)
    - Vérifier le format du ciphertext (base64url, nonce de 12 octets préfixé)
    - Vérifier qu'une clé invalide (pas 32 octets) lève `ValueError`
    - _Exigences : 10.3, 10.4_

- [x] 6. Point de contrôle — Vérifier le chiffrement et les en-têtes
  - Exécuter tous les tests. Demander à l'utilisateur si des questions se posent.

- [x] 7. Implémenter le connection pooling HTTP dans _LLMClient
  - [x] 7.1 Refactorer `backend/services/llm_router.py` pour réutiliser httpx.AsyncClient
    - Créer `httpx.AsyncClient` dans `_LLMClient.__init__` avec timeout et limits configurés
    - Modifier `_do_request` pour utiliser `self._client` au lieu de `async with httpx.AsyncClient()`
    - Ajouter une méthode `async close()` pour fermer le client HTTP
    - _Exigences : 11.1, 11.2, 11.3_

  - [x] 7.2 Ajouter le hook de shutdown dans `backend/main.py`
    - Fermer les clients HTTP des deux `_LLMClient` (primary et fallback) dans le bloc `yield` du `lifespan()`
    - Ajouter une méthode `async close()` sur `LLMRouter` qui appelle `close()` sur les deux clients
    - _Exigences : 11.4_

  - [x] 7.3 Écrire les tests unitaires pour le connection pooling
    - Vérifier que `_LLMClient.__init__` crée un `httpx.AsyncClient`
    - Vérifier que `close()` ferme le client
    - Vérifier que `_do_request` utilise le client partagé
    - _Exigences : 11.1, 11.2, 11.3_

- [x] 8. Renforcer la validation JSON-RPC dans BaseMCPServer
  - [x] 8.1 Ajouter la validation stricte de l'enveloppe JSON-RPC dans `backend/agents/mcp_servers/base_server.py`
    - Le code existant valide déjà `jsonrpc != "2.0"` et `not method` — conserver ces checks
    - Renforcer le check `method` : ajouter `not isinstance(method, str)` pour rejeter les types non-chaîne (ex. `method=123` passerait le check `not method` existant)
    - Ajouter la validation de `params` (si présent) : doit être `dict` ou `list`, sinon retourner -32602 *(nouveau)*
    - Ajouter la validation de `id` (si présent) : doit être `str`, `int`, ou `None`, sinon retourner -32600 *(nouveau)*
    - _Exigences : 12.1, 12.2, 12.3, 12.4, 12.5_

  - [x] 8.2 Écrire le test property-based pour les enveloppes JSON-RPC invalides → -32600
    - **Propriété 5 : Enveloppe JSON-RPC invalide retourne -32600**
    - Générer des enveloppes avec `jsonrpc` ≠ `"2.0"`, `method` absent/non-chaîne, `id` de type invalide
    - Vérifier que le code d'erreur retourné est -32600
    - **Valide : Exigences 12.1, 12.2, 12.4**

  - [x] 8.3 Écrire le test property-based pour params JSON-RPC invalides → -32602
    - **Propriété 6 : Params JSON-RPC de type invalide retourne -32602**
    - Générer des requêtes avec `params` de type non-dict/non-list (int, str, bool, float)
    - Vérifier que le code d'erreur retourné est -32602
    - **Valide : Exigence 12.3**

  - [x] 8.4 Écrire le test property-based pour les enveloppes JSON-RPC valides → dispatch
    - **Propriété 7 : Enveloppe JSON-RPC valide est dispatchée sans erreur de validation**
    - Générer des requêtes valides (`jsonrpc="2.0"`, `method` = chaîne non vide parmi les méthodes connues, `params` = dict/list/absent, `id` = str/int/None/absent)
    - Vérifier que la réponse ne contient pas de code d'erreur -32600 ni -32602
    - **Valide : Exigence 12.5**

- [x] 9. Mettre à jour la documentation
  - [x] 9.1 Mettre à jour `docs/configuration.md`
    - Ajouter les variables `MONGO_USERNAME`, `MONGO_PASSWORD`, `REDIS_PASSWORD`, `CSP_POLICY` dans les sections appropriées
    - Mettre à jour la section « Cache / Redis » avec le format d'URI authentifié
    - Mettre à jour la section « Base de données » avec le format d'URI authentifié
    - Mettre à jour la valeur par défaut de `ALLOWED_ORIGINS` de `*` à `http://localhost:3000`
    - Mettre à jour la section « HIPAA Compliance » : remplacer la commande de génération de clé Fernet par la commande AES-256-GCM (`python -c "import os, base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"`) et mettre à jour la description de `HIPAA_ENCRYPTION_KEY_ID`

  - [x] 9.2 Mettre à jour `docs/deployment.md`
    - Mettre à jour le tableau des services : supprimer les ports 8001–8004 des agents MCP (internes uniquement)
    - Ajouter une section « Migration depuis une version sans authentification » expliquant la suppression du volume MongoDB (`docker compose down -v`)
    - Ajouter une note sur l'authentification Redis et MongoDB dans la section « Démarrage rapide »
    - Mettre à jour le rôle Grafana anonyme de `Admin` à `Viewer`

  - [x] 9.3 Mettre à jour `docs/hipaa-compliance.md`
    - Remplacer la section « Chiffrement AES-256 » : documenter la migration de Fernet vers AES-256-GCM
    - Mettre à jour l'algorithme : AES-256-GCM (AESGCM) avec nonce 12 octets au lieu de Fernet (AES-128-CBC)
    - Documenter le format ciphertext : `base64url(nonce[12] || ciphertext+tag)`
    - Documenter le fallback Fernet pour la compatibilité descendante
    - Mettre à jour les flux de chiffrement/déchiffrement
    - Mettre à jour la commande de génération de clé

  - [x] 9.4 Mettre à jour `README.md`
    - Mettre à jour la section « Configurer les variables d'environnement » avec `MONGO_USERNAME`, `MONGO_PASSWORD`, `REDIS_PASSWORD`
    - Mettre à jour l'exemple `MONGODB_URI` avec les identifiants
    - Supprimer les agents MCP du tableau « Accéder aux services » (ports internes uniquement)
    - Ajouter une note sur la migration des volumes MongoDB existants

  - [x] 9.5 Mettre à jour `docs/developer-guide.md`
    - Ajouter une note sur les en-têtes de sécurité (CSP, Referrer-Policy, Permissions-Policy) dans la section appropriée
    - Documenter que le backend CSP s'applique aux réponses API et que le frontend a sa propre CSP dans `next.config.ts`
    - Documenter la validation JSON-RPC renforcée dans `BaseMCPServer`

- [x] 10. Point de contrôle final — Exécuter tous les tests
  - Exécuter tous les tests (pytest + hypothesis). Demander à l'utilisateur si des questions se posent.

## Notes

- Les tâches marquées `*` sont optionnelles et peuvent être ignorées pour un MVP plus rapide
- Chaque tâche référence les exigences spécifiques pour la traçabilité
- Les points de contrôle assurent une validation incrémentale
- Les tests property-based valident les propriétés de correction universelles (Hypothesis, ≥100 itérations)
- Les tests unitaires valident des exemples spécifiques et des cas limites
