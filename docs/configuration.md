# Référence de configuration — Diagno-Pilot

Tous les paramètres sont centralisés dans la classe `Settings` (`backend/core/config.py`) et configurables via variables d'environnement ou fichier `.env`.

## Table des matières

- [Model\_Container](#model_container)
- [LlamaIndex Pipeline](#llamaindex-pipeline)
- [Serveurs MCP Agents](#serveurs-mcp-agents)
- [HIPAA Compliance](#hipaa-compliance)
- [LLM (hérité)](#llm-hérité)
- [Authentification](#authentification)
- [Base de données](#base-de-données)
- [AWS / S3](#aws--s3)
- [Cache / Redis](#cache--redis)
- [Application](#application)
- [Validations en production](#validations-en-production)

---

## Model\_Container

Configuration du serveur llama.cpp local.

| Variable | Type | Défaut | Requis en prod | Description |
|---|---|---|---|---|
| `MODEL_CONTAINER_URL` | `str` | `http://model:8080/v1` | Non | URL de l'API du Model\_Container |
| `MODEL_CONTAINER_API_KEY` | `str` | `""` | Non | Clé API du Model\_Container |
| `MODEL_GPU_LAYERS` | `int` | `99` | Non | Nombre de couches GPU (`99` = toutes) |
| `MODEL_CONTEXT_SIZE` | `int` | `4096` | Non | Taille de la fenêtre de contexte (tokens) |
| `MODEL_THREADS` | `int` | `4` | Non | Nombre de threads CPU |

## LlamaIndex Pipeline

Configuration du pipeline RAG LlamaIndex.

| Variable | Type | Défaut | Requis en prod | Description |
|---|---|---|---|---|
| `LLAMAINDEX_CHUNK_SIZE` | `int` | `512` | Non | Taille maximale des chunks (tokens) |
| `LLAMAINDEX_CHUNK_OVERLAP_TOKENS` | `int` | `50` | Non | Chevauchement entre chunks (tokens) |
| `LLAMAINDEX_SIMILARITY_THRESHOLD` | `float` | `0.75` | Non | Seuil de similarité pour le filtrage des résultats. Utilisé par le pipeline RAG et par chaque serveur MCP agent pour déterminer si des données pertinentes existent dans sa collection de documents. |

## Serveurs MCP Agents

Configuration des URLs des serveurs MCP spécialistes. Chaque serveur est un service Docker indépendant communiquant via JSON-RPC 2.0 sur HTTP+SSE.

| Variable | Type | Défaut | Requis en prod | Description |
|---|---|---|---|---|
| `AGENT_EPIDEMIOLOGY_URL` | `str` | `http://agent-epidemiology:8001` | Non | URL du serveur MCP Épidémiologie |
| `AGENT_SYMPTOMATOLOGY_URL` | `str` | `http://agent-symptomatology:8002` | Non | URL du serveur MCP Symptomatologie |
| `AGENT_LAB_URL` | `str` | `http://agent-lab:8003` | Non | URL du serveur MCP Laboratoire |
| `AGENT_TREATMENT_URL` | `str` | `http://agent-treatment:8004` | Non | URL du serveur MCP Traitement |

Les valeurs par défaut correspondent aux hostnames Docker internes. Pour le développement local (hors Docker), surcharger avec `http://localhost:800X`.

> **Note :** Les serveurs MCP agents utilisent également `LLAMAINDEX_SIMILARITY_THRESHOLD` (défaut `0.75`) pour filtrer les chunks non pertinents lors de la recherche vectorielle. Ce seuil est lu depuis la configuration partagée.

## HIPAA Compliance

Configuration des contrôles de conformité HIPAA.

| Variable | Type | Défaut | Requis en prod | Description |
|---|---|---|---|---|
| `HIPAA_ENCRYPTION_KEY_ID` | `str` | `""` | **Oui** | Clé de chiffrement AES-256-GCM : 32 octets encodés en base64 URL-safe. |
| `HIPAA_AUDIT_HASH_CHAIN_ENABLED` | `bool` | `true` | Non | Active la chaîne de hachage dans les logs d'audit HIPAA |
| `HIPAA_PHI_STRIP_ON_FALLBACK` | `bool` | `true` | **Oui** | Active le stripping PHI avant les appels LLM externes. Doit être `true` en production. |

**Génération d'une clé AES-256-GCM :**

```bash
python -c "import os, base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
```

> **Note :** Les anciennes clés Fernet ne sont pas compatibles avec AES-256-GCM. Le service de chiffrement conserve un fallback Fernet pour déchiffrer les données existantes pendant la migration.

## LLM (hérité)

Paramètres LLM existants maintenus pour compatibilité ascendante. Le `MODEL_CONTAINER_URL` est prioritaire sur `LLM_PRIMARY_URL` pour le routage primaire.

| Variable | Type | Défaut | Requis en prod | Description |
|---|---|---|---|---|
| `LLM_PRIMARY_URL` | `str \| None` | `None` | Non | URL du LLM primaire (remplacé par `MODEL_CONTAINER_URL`) |
| `LLM_PRIMARY_API_KEY` | `str \| None` | `None` | Non | Clé API du LLM primaire |
| `LLM_FALLBACK_URL` | `str \| None` | `None` | Non | URL du LLM de fallback (GPT-5) |
| `LLM_FALLBACK_API_KEY` | `str \| None` | `None` | Non | Clé API du LLM de fallback |
| `EMBED_MODEL` | `str` | `text-embedding-ada-002` | Non | Nom du modèle d'embedding |
| `LLM_TIMEOUT` | `int` | `60` | Non | Timeout des requêtes LLM (secondes) |
| `LLM_RETRY_MAX` | `int` | `3` | Non | Nombre maximum de tentatives |
| `LLM_RETRY_BASE_DELAY` | `float` | `1.0` | Non | Délai de base pour le backoff exponentiel (secondes) |
| `LLM_RETRY_MAX_DELAY` | `float` | `30.0` | Non | Délai maximum de backoff (secondes) |

## Authentification

| Variable | Type | Défaut | Requis en prod | Description |
|---|---|---|---|---|
| `JWT_SECRET` | `str` | `change_me_...` | **Oui** | Secret JWT (≥ 32 caractères). Générer avec `openssl rand -hex 32` |
| `JWT_ALGORITHM` | `str` | `HS256` | Non | Algorithme JWT |
| `JWT_EXPIRE_MINUTES` | `int` | `15` | Non | Durée de validité du token d'accès (minutes) |
| `JWT_REFRESH_EXPIRE_DAYS` | `int` | `7` | Non | Durée de validité du refresh token (jours) |

## Base de données

| Variable | Type | Défaut | Requis en prod | Description |
|---|---|---|---|---|
| `MONGODB_URI` | `str` | `mongodb://localhost:27017/diagno_pilot` | Non | URI de connexion MongoDB (format authentifié : `mongodb://user:pass@host:27017/diagno_pilot?authSource=admin`) |
| `MONGO_USERNAME` | `str` | `diagno_dev` | **Oui** | Utilisateur root MongoDB (utilisé dans `docker-compose.yml`) |
| `MONGO_PASSWORD` | `str` | `diagno_dev_pass` | **Oui** | Mot de passe root MongoDB (utilisé dans `docker-compose.yml`) |

## AWS / S3

| Variable | Type | Défaut | Requis en prod | Description |
|---|---|---|---|---|
| `AWS_ENDPOINT_URL` | `str \| None` | `None` | Non | URL de l'endpoint AWS (LocalStack en dev) |
| `AWS_ACCESS_KEY_ID` | `str \| None` | `None` | Non | Clé d'accès AWS |
| `AWS_SECRET_ACCESS_KEY` | `str \| None` | `None` | Non | Clé secrète AWS |
| `AWS_DEFAULT_REGION` | `str` | `us-east-1` | Non | Région AWS |
| `S3_BUCKET` | `str` | `diagno-pilot-files` | Non | Nom du bucket S3 |

## Cache / Redis

| Variable | Type | Défaut | Requis en prod | Description |
|---|---|---|---|---|
| `REDIS_URL` | `str` | `redis://:diagno_redis_dev@localhost:6379/0` | Non | URL de connexion Redis (format authentifié : `redis://:password@host:6379/0`) |
| `REDIS_PASSWORD` | `str` | `diagno_redis_dev` | **Oui** | Mot de passe Redis (utilisé dans `docker-compose.yml`) |
| `CACHE_TTL_PROTOCOLS` | `int` | `3600` | Non | TTL du cache protocoles (secondes) |
| `CACHE_TTL_INTERACTIONS` | `int` | `3600` | Non | TTL du cache interactions (secondes) |
| `CACHE_TTL_EMBEDDINGS` | `int` | `86400` | Non | TTL du cache embeddings (24h) |
| `CACHE_TTL_RAG` | `int` | `300` | Non | TTL du cache réponses RAG (5 min) |
| `CACHE_KEY_VERSION` | `str` | `v1` | Non | Version du préfixe des clés de cache |

## Application

| Variable | Type | Défaut | Requis en prod | Description |
|---|---|---|---|---|
| `ENV` | `str` | `development` | Non | Environnement (`development`, `staging`, `production`) |
| `ALLOWED_ORIGINS` | `str` | `http://localhost:3000` | **Oui** | Origines CORS autorisées (liste séparée par virgules). Ne peut pas être `*` en production. |
| `CSP_POLICY` | `str` | `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'` | Non | Valeur de l'en-tête Content-Security-Policy pour les réponses API backend |
| `LOG_LEVEL` | `str` | `INFO` | Non | Niveau de log (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `LOG_FORMAT` | `str` | `json` | Non | Format de log (`json` ou `text`) |
| `METRICS_AUTH` | `str` | `""` | Non | Authentification Basic Auth pour `/metrics` (format `user:password`) |
| `RATE_LIMIT_STORAGE_URI` | `str` | `memory://` | Non | URI de stockage pour le rate limiting (auto-migré vers Redis si `REDIS_URL` est défini) |

---

## Validations en production

Lorsque `ENV=production`, les validations suivantes sont appliquées au démarrage :

| Validation | Erreur si non respecté |
|---|---|
| `JWT_SECRET` ≥ 32 caractères et non valeur par défaut | `JWT_SECRET must be a strong random secret (≥32 chars) in production` |
| `ALLOWED_ORIGINS` ≠ `*` et non vide | `ALLOWED_ORIGINS must be an explicit list in production` |
| `HIPAA_ENCRYPTION_KEY_ID` non vide | `HIPAA_ENCRYPTION_KEY_ID must be set in production` |
| `HIPAA_PHI_STRIP_ON_FALLBACK` = `true` | `HIPAA_PHI_STRIP_ON_FALLBACK must be enabled in production` |
