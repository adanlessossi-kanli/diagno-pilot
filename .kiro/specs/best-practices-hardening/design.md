# Document de conception — Durcissement des bonnes pratiques

## Vue d'ensemble

Ce document décrit la conception technique pour le durcissement sécurité et bonnes pratiques de Diagno-Pilot. Les 13 exigences couvrent quatre axes principaux :

1. **Isolation Docker** (Exigences 1–3, 7) : conteneurs non-root, suppression du hot-reload en production, build multi-étapes frontend, suppression des ports MCP exposés.
2. **Authentification infrastructure** (Exigences 4–6) : identifiants MongoDB et Redis, restriction Grafana.
3. **En-têtes et origines HTTP** (Exigences 8, 9, 13) : `ALLOWED_ORIGINS` restrictif, `Content-Security-Policy`, `Referrer-Policy`, `Permissions-Policy`.
4. **Code applicatif** (Exigences 10–12) : migration Fernet → AES-256-GCM, pooling HTTP dans `_LLMClient`, validation JSON-RPC stricte.

Toutes les modifications sont rétrocompatibles : les environnements de développement existants continuent de fonctionner via des valeurs par défaut et des surcharges Docker Compose.

## Architecture

Les changements ne modifient pas l'architecture globale de Diagno-Pilot. Ils renforcent les couches existantes :

```mermaid
graph TB
    subgraph Docker Compose
        FE[Frontend<br/>multi-stage build<br/>nextuser non-root]
        BE[Backend<br/>appuser non-root<br/>sans --reload]
        AG1[Agent Épidémiologie<br/>ports internes uniquement]
        AG2[Agent Symptomatologie<br/>ports internes uniquement]
        AG3[Agent Laboratoire<br/>ports internes uniquement]
        AG4[Agent Traitement<br/>ports internes uniquement]
        MG[(MongoDB<br/>auth activée)]
        RD[(Redis<br/>requirepass)]
        GF[Grafana<br/>Viewer anonyme]
    end

    subgraph Backend Application
        SH[SecurityHeadersMiddleware<br/>CSP + Referrer + Permissions]
        CFG[Config Module<br/>ALLOWED_ORIGINS restrictif<br/>CSP_POLICY]
        ENC[EncryptionService<br/>AES-256-GCM + fallback Fernet]
        LLM[_LLMClient<br/>httpx.AsyncClient partagé]
        MCP[BaseMCPServer<br/>validation JSON-RPC stricte]
    end

    BE --> SH
    BE --> CFG
    BE --> ENC
    BE --> LLM
    BE --> MCP
    BE --> MG
    BE --> RD
    BE --> AG1 & AG2 & AG3 & AG4
```

## Composants et interfaces

### 1. Backend Dockerfile (Exigences 1, 2)

**Modifications :**
- Ajout d'un utilisateur système `appuser` (UID 1001, sans shell)
- Directive `USER appuser` après `COPY`
- CMD sans `--reload` : `["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]`
- Docker Compose surcharge le CMD en dev avec `command: uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload --reload-include *.py`

### 2. Frontend Dockerfile (Exigence 3)

**Prérequis :** Ajouter `output: 'standalone'` dans `apps/web/next.config.ts` pour que `npm run build` produise un dossier `.next/standalone` autonome.

**Build multi-étapes :**
- Étape `deps` : installe les dépendances npm
- Étape `builder` : copie les sources et exécute `npm run build` (produit `.next/standalone` grâce à `output: 'standalone'`)
- Étape finale `runner` : copie `.next/standalone`, `.next/static`, `public` ; crée `nextuser` (UID 1001) ; CMD `["node", "server.js"]`
- Docker Compose surcharge en dev avec `command: npm run dev` et les volumes de sources

### 3. Docker Compose — Authentification MongoDB (Exigence 4)

**Modifications :**
- Variables `MONGO_INITDB_ROOT_USERNAME` et `MONGO_INITDB_ROOT_PASSWORD` sur le service `mongo`
- URI mise à jour : `mongodb://${MONGO_USERNAME:-diagno_dev}:${MONGO_PASSWORD:-diagno_dev_pass}@mongo:27017/diagno_pilot?authSource=admin`
- Propagation aux services `backend`, `seed`, et agents

**⚠️ Migration des environnements existants :**
MongoDB n'exécute `MONGO_INITDB_ROOT_USERNAME` que sur un volume vierge. Les développeurs avec un volume `mongo_data` existant doivent le supprimer avant le premier démarrage avec authentification :
```bash
docker compose down -v  # ou : docker volume rm diagno-pilot_mongo_data
```
Un commentaire dans `docker-compose.yml` et `.env.example` documentera cette contrainte.

### 4. Docker Compose — Authentification Redis (Exigence 5)

**Modifications :**
- `command: redis-server --requirepass ${REDIS_PASSWORD:-diagno_redis_dev}`
- URI mise à jour : `redis://:${REDIS_PASSWORD:-diagno_redis_dev}@redis:6379/0`
- Healthcheck mis à jour avec `REDISCLI_AUTH`
- Valeur par défaut de `REDIS_URL` dans `backend/core/config.py` mise à jour : `redis://:diagno_redis_dev@localhost:6379/0` (pour éviter les échecs de connexion silencieux quand Redis est protégé par mot de passe)

### 5. Docker Compose — Grafana (Exigence 6)

**Modifications :**
- `GF_AUTH_ANONYMOUS_ORG_ROLE=Viewer` (au lieu de `Admin`)
- Commentaire indiquant de désactiver `GF_AUTH_ANONYMOUS_ENABLED` en production

### 6. Docker Compose — Ports MCP agents (Exigence 7)

**Modifications :**
- Suppression des directives `ports` des 4 services agents
- Les healthchecks internes (`localhost`) restent inchangés

### 7. Config Module — ALLOWED_ORIGINS (Exigence 8)

**Modifications :**
- Valeur par défaut de `ALLOWED_ORIGINS` changée de `"*"` à `"http://localhost:3000"`
- La validation de production existante reste inchangée

### 8. Config Module — CSP_POLICY (Exigence 9)

**Ajout :**
- Nouveau champ `CSP_POLICY: str` avec valeur par défaut : `"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'"`

> **Note :** Cette CSP s'applique uniquement aux réponses API du backend (FastAPI). Le frontend Next.js injecte sa propre CSP via `next.config.ts` avec des directives adaptées (incluant `https://images.unsplash.com` pour les images et `'unsafe-eval'` en dev pour le HMR). Les deux politiques ne sont pas en conflit car elles s'appliquent à des réponses HTTP distinctes.

### 9. SecurityHeadersMiddleware (Exigences 9, 13)

**Ajout de 3 en-têtes :**
- `Content-Security-Policy` : valeur de `settings.CSP_POLICY`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=()`

### 10. EncryptionService — AES-256-GCM (Exigence 10)

**Refactoring majeur :**
- Remplacement de `cryptography.fernet.Fernet` par `cryptography.hazmat.primitives.ciphers.aead.AESGCM`
- Clé : 32 octets (256 bits) encodée en base64 URL-safe
- Nonce : 12 octets aléatoires générés via `os.urandom(12)` pour chaque chiffrement
- Format du ciphertext : `nonce (12 bytes) || ciphertext+tag` encodé en base64 URL-safe
- Fallback Fernet pour la compatibilité descendante lors du déchiffrement
- Rotation de clés : la clé précédente (AESGCM) et l'ancienne Fernet sont conservées pour le déchiffrement

**⚠️ Changement de format de clé :**
Les clés Fernet (44 caractères base64 standard) ne sont pas compatibles avec AES-256-GCM (32 octets base64url). Les environnements existants doivent générer une nouvelle clé :
```bash
python -c "import os, base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
```
Le fallback Fernet permet de déchiffrer les données existantes pendant la période de migration. La variable `HIPAA_ENCRYPTION_KEY_ID` dans `.env.example` sera documentée avec cette commande.

**Interface publique inchangée :**
- `encrypt_field(plaintext: str) -> str`
- `decrypt_field(ciphertext: str) -> str`
- `encrypt_phi_fields(data, classifier) -> dict`
- `decrypt_phi_fields(data, classifier) -> dict`
- `rotate_key(new_key: str) -> None`

### 11. _LLMClient — Connection Pooling (Exigence 11)

**Modifications :**
- `httpx.AsyncClient` créé dans `__init__` avec `timeout` et `limits` configurés
- `_do_request` utilise `self._client` au lieu de `async with httpx.AsyncClient()`
- Nouvelle méthode `async close()` pour fermer le client
- `LLMRouter` appelle `close()` sur les deux clients lors du shutdown de l'application
- Hook de shutdown ajouté dans `lifespan()` de `main.py`

### 12. BaseMCPServer — Validation JSON-RPC (Exigence 12)

**Renforcement de `_handle_request` :**

Le code existant valide déjà `jsonrpc != "2.0"` et `not method` (couvre `None` et chaîne vide). Les validations à ajouter sont :
- Validation du type de `method` : doit être `str` *(nouveau — un entier non-zéro passerait le check `not method` existant)*
- Validation du type de `params` : doit être `dict`, `list`, ou absent *(nouveau)*
- Validation du type de `id` : doit être `str`, `int`, `None`, ou absent *(nouveau)*
- Codes d'erreur JSON-RPC appropriés : -32600 (Invalid Request), -32602 (Invalid Params)

## Modèles de données

### Format ciphertext AES-256-GCM

```
Base64URL( nonce[12 bytes] || AESGCM.encrypt(nonce, plaintext_utf8, aad=None) )
```

- Le nonce de 12 octets est préfixé au ciphertext+tag (16 octets de tag GCM)
- Le tout est encodé en base64 URL-safe pour stockage en MongoDB (champ string)
- Distinction avec Fernet : les tokens Fernet commencent par `gAAAAA` (base64 standard), les tokens AES-GCM utilisent base64 URL-safe

### Variables d'environnement ajoutées

| Variable | Défaut (dev) | Description |
|---|---|---|
| `MONGO_USERNAME` | `diagno_dev` | Utilisateur root MongoDB |
| `MONGO_PASSWORD` | `diagno_dev_pass` | Mot de passe root MongoDB |
| `REDIS_PASSWORD` | `diagno_redis_dev` | Mot de passe Redis |
| `CSP_POLICY` | *(politique par défaut)* | Valeur de l'en-tête Content-Security-Policy |

### Variables d'environnement modifiées

| Variable | Ancienne valeur | Nouvelle valeur | Raison |
|---|---|---|---|
| `MONGODB_URI` (docker-compose) | `mongodb://mongo:27017/diagno_pilot` | `mongodb://diagno_dev:diagno_dev_pass@mongo:27017/diagno_pilot?authSource=admin` | Authentification MongoDB |
| `REDIS_URL` (docker-compose) | `redis://redis:6379/0` | `redis://:diagno_redis_dev@redis:6379/0` | Authentification Redis |
| `REDIS_URL` (config.py défaut) | `redis://localhost:6379/0` | `redis://:diagno_redis_dev@localhost:6379/0` | Cohérence avec Redis authentifié |
| `ALLOWED_ORIGINS` (config.py défaut) | `*` | `http://localhost:3000` | Restriction par défaut |

### Schéma de validation JSON-RPC (logique dans `_handle_request`)

```python
# Pseudo-validation
assert isinstance(request, dict)
assert request.get("jsonrpc") == "2.0"
assert isinstance(request.get("method"), str) and request["method"]
assert "params" not in request or isinstance(request.get("params"), (dict, list))
assert "id" not in request or isinstance(request.get("id"), (str, int, type(None)))
```


## Propriétés de correction

*Une propriété est une caractéristique ou un comportement qui doit rester vrai pour toutes les exécutions valides d'un système — essentiellement, une déclaration formelle sur ce que le système doit faire. Les propriétés servent de pont entre les spécifications lisibles par l'humain et les garanties de correction vérifiables par la machine.*

### Propriété 1 : Complétude des en-têtes de sécurité

*Pour toute* requête HTTP envoyée à l'application, la réponse DOIT contenir les en-têtes `Content-Security-Policy` (avec au minimum `default-src 'self'`), `Referrer-Policy` (valeur `strict-origin-when-cross-origin`), et `Permissions-Policy` (valeur `camera=(), microphone=(), geolocation=(), payment=()`).

**Valide : Exigences 9.1, 13.1, 13.2**

### Propriété 2 : Aller-retour du chiffrement AES-256-GCM

*Pour toute* chaîne de texte UTF-8 valide, le chiffrement suivi du déchiffrement avec la même clé DOIT produire la chaîne originale.

**Valide : Exigence 10.6**

### Propriété 3 : Unicité des nonces AES-256-GCM

*Pour toute* chaîne de texte, deux chiffrements successifs de la même chaîne avec la même clé DOIVENT produire des ciphertexts différents (car les nonces sont générés aléatoirement).

> **Note :** Cette propriété est probabiliste — la collision de deux nonces de 12 octets aléatoires est astronomiquement improbable (1/2⁹⁶) mais pas mathématiquement impossible. Avec 100 itérations Hypothesis, le risque de faux positif est négligeable.

**Valide : Exigence 10.2**

### Propriété 4 : Rotation de clé préserve le déchiffrement

*Pour toute* chaîne de texte chiffrée avec une clé A, après rotation vers une clé B, le déchiffrement DOIT toujours réussir et produire la chaîne originale.

**Valide : Exigence 10.5**

### Propriété 5 : Enveloppe JSON-RPC invalide retourne -32600

*Pour toute* requête JSON-RPC dont l'enveloppe est invalide (champ `jsonrpc` ≠ `"2.0"`, ou `method` absent/non-chaîne, ou `id` de type non valide), le serveur DOIT retourner une erreur JSON-RPC avec le code -32600 (Invalid Request).

**Valide : Exigences 12.1, 12.2, 12.4**

### Propriété 6 : Params JSON-RPC de type invalide retourne -32602

*Pour toute* requête JSON-RPC dont le champ `params` est présent mais n'est ni un `dict` ni une `list`, le serveur DOIT retourner une erreur JSON-RPC avec le code -32602 (Invalid Params).

**Valide : Exigence 12.3**

### Propriété 7 : Enveloppe JSON-RPC valide est dispatchée sans erreur de validation

*Pour toute* requête JSON-RPC valide (`jsonrpc="2.0"`, `method` = chaîne non vide, `params` = dict/list/absent, `id` = chaîne/entier/null/absent), le serveur DOIT dispatcher la requête au handler approprié sans retourner d'erreur de validation d'enveloppe.

**Valide : Exigence 12.5**

## Documentation (Exigence 14)

Les fichiers de documentation suivants doivent être mis à jour pour refléter les changements de durcissement :

| Fichier | Changements |
|---|---|
| `docs/configuration.md` | Nouvelles variables (`MONGO_USERNAME`, `MONGO_PASSWORD`, `REDIS_PASSWORD`, `CSP_POLICY`), valeurs par défaut modifiées (`ALLOWED_ORIGINS`, `REDIS_URL`), commande de génération de clé AES-256-GCM |
| `docs/deployment.md` | Ports MCP agents supprimés du tableau, section migration volumes MongoDB, auth MongoDB/Redis, rôle Grafana `Viewer` |
| `docs/hipaa-compliance.md` | Migration Fernet → AES-256-GCM, nouveau format de clé (32 octets base64url), format ciphertext (`nonce || ciphertext+tag`), fallback Fernet, nouvelle commande de génération |
| `README.md` | Exemples de configuration avec identifiants, suppression des ports MCP agents du tableau des services, note de migration |
| `docs/developer-guide.md` | En-têtes de sécurité (CSP, Referrer-Policy, Permissions-Policy), distinction CSP backend/frontend, validation JSON-RPC renforcée |

## Gestion des erreurs

### Chiffrement (Exigence 10)

| Scénario | Comportement |
|---|---|
| Clé invalide (pas 32 octets) | `ValueError` levée dans le constructeur |
| Déchiffrement AES-GCM échoue | Tentative de fallback Fernet |
| Déchiffrement Fernet échoue aussi | `EncryptionError` levée, audit log enregistré |
| Nonce corrompu | `EncryptionError` (le tag GCM détecte la corruption) |

### Validation JSON-RPC (Exigence 12)

| Scénario | Code d'erreur | Message |
|---|---|---|
| Corps non-JSON | -32700 | Parse error |
| Corps non-dict | -32600 | Invalid Request |
| `jsonrpc` ≠ `"2.0"` | -32600 | Invalid Request |
| `method` absent ou non-string | -32600 | Invalid Request |
| `id` de type invalide | -32600 | Invalid Request |
| `params` de type invalide | -32602 | Invalid Params |
| Méthode inconnue | -32601 | Method not found |

### Client HTTP LLM (Exigence 11)

| Scénario | Comportement |
|---|---|
| Client non initialisé | `RuntimeError` si `close()` appelé avant `__init__` |
| Connexion perdue | `httpx` lève une exception, gérée par `RetryPolicy` existant |
| Shutdown de l'application | `lifespan()` appelle `close()` sur les deux clients |

### Docker / Infrastructure (Exigences 1–7)

| Scénario | Comportement |
|---|---|
| `MONGO_USERNAME`/`MONGO_PASSWORD` absents | Valeurs par défaut dev utilisées |
| `REDIS_PASSWORD` absent | Valeur par défaut dev utilisée |
| Conteneur backend compromis | Impact limité : processus non-root, pas d'accès root au FS |

## Stratégie de tests

### Tests property-based (Hypothesis, ≥100 itérations)

Les propriétés de correction 1–7 seront implémentées comme des tests property-based avec la bibliothèque **Hypothesis** (déjà présente dans le projet via le dossier `.hypothesis/`).

Chaque test sera taggé avec un commentaire référençant la propriété :
```python
# Feature: best-practices-hardening, Property 2: AES-256-GCM round-trip
```

Configuration minimale : `@settings(max_examples=100)`

| Propriété | Module testé | Stratégie Hypothesis |
|---|---|---|
| 1 — En-têtes de sécurité | `SecurityHeadersMiddleware` | `st.text()` pour les chemins de requête, TestClient FastAPI |
| 2 — Chiffrement aller-retour | `EncryptionService` | `st.text()` pour les plaintexts |
| 3 — Unicité des nonces | `EncryptionService` | `st.text()` pour les plaintexts |
| 4 — Rotation de clé | `EncryptionService` | `st.text()` pour les plaintexts, deux clés générées |
| 5 — JSON-RPC invalide → -32600 | `BaseMCPServer._handle_request` | Stratégies custom pour enveloppes invalides |
| 6 — JSON-RPC params invalide → -32602 | `BaseMCPServer._handle_request` | Stratégies custom pour params non-dict/list |
| 7 — JSON-RPC valide → dispatch | `BaseMCPServer._handle_request` | Stratégies custom pour enveloppes valides |

### Tests unitaires (exemple-based)

| Exigence | Tests |
|---|---|
| 8 — ALLOWED_ORIGINS | Vérifier la valeur par défaut `http://localhost:3000` ; vérifier que la validation production rejette toujours `*` |
| 9 — CSP configurable | Vérifier qu'une valeur custom de `CSP_POLICY` est utilisée dans l'en-tête |
| 10 — Compatibilité Fernet | Chiffrer avec Fernet, déchiffrer avec le nouveau service ; vérifier le format du ciphertext |
| 11 — Connection pooling | Vérifier que `_LLMClient` crée un `httpx.AsyncClient` dans `__init__` ; vérifier que `close()` ferme le client |

### Tests smoke / infrastructure

| Exigence | Vérification |
|---|---|
| 1 — Non-root backend | Inspecter le Dockerfile pour `USER appuser` |
| 2 — Sans --reload | Inspecter le Dockerfile CMD |
| 3 — Multi-stage frontend | Inspecter le Dockerfile pour les étapes `builder` et `runner` |
| 4 — Auth MongoDB | Inspecter docker-compose.yml pour les variables d'auth |
| 5 — Auth Redis | Inspecter docker-compose.yml pour `--requirepass` |
| 6 — Grafana Viewer | Inspecter docker-compose.yml pour `GF_AUTH_ANONYMOUS_ORG_ROLE=Viewer` |
| 7 — Ports MCP supprimés | Inspecter docker-compose.yml pour l'absence de `ports` sur les agents |
