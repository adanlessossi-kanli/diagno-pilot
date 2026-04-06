# Guide de déploiement — Diagno-Pilot

## Table des matières

- [Prérequis](#prérequis)
- [Structure Docker Compose](#structure-docker-compose)
- [Démarrage rapide](#démarrage-rapide)
- [Model\_Container — Configuration GPU](#model_container--configuration-gpu)
- [Model\_Container — Fallback CPU](#model_container--fallback-cpu)
- [Volumes et montages](#volumes-et-montages)
- [Services de support](#services-de-support)
- [Vérification du déploiement](#vérification-du-déploiement)

---

## Prérequis

- Docker Engine ≥ 24.0 et Docker Compose v2
- NVIDIA Container Toolkit (pour le profil GPU)
- Fichier modèle `model/MedicalQwen3-Reasoning-4B.Q8_0.gguf` dans le répertoire racine du projet
- Fichier `.env` configuré (copier depuis `.env.example`)

## Structure Docker Compose

Le fichier `docker-compose.yml` définit les services suivants :

| Service | Image | Port | Description |
|---|---|---|---|
| `frontend` | Build local (`apps/web/Dockerfile`) | 3000 | Application Next.js |
| `backend` | Build local (`./backend`) | 8000 | API FastAPI |
| `model` | `ghcr.io/ggerganov/llama.cpp:server` | 8080 | LLM local (profil GPU) |
| `model-cpu` | `ghcr.io/ggerganov/llama.cpp:server` | 8080 | LLM local (profil CPU) |
| `mongo` | `mongodb/mongodb-atlas-local:8.0` | 27017 | MongoDB Atlas Local |
| `redis` | `redis:7-alpine` | 6379 | Cache Redis |
| `localstack` | `localstack/localstack:3` | 4566 | S3 local (dev) |
| `prometheus` | `prom/prometheus:v2.51.2` | 9090 | Métriques |
| `grafana` | `grafana/grafana:10.4.2` | 3001 | Tableaux de bord |
| `loki` | `grafana/loki:2.9.4` | — | Agrégation de logs |

## Démarrage rapide

### 1. Copier la configuration

```bash
cp .env.example .env
```

### 2. Placer le modèle

Placer le fichier GGUF dans le répertoire `model/` :

```
model/MedicalQwen3-Reasoning-4B.Q8_0.gguf
```

### 3. Lancer avec GPU

```bash
docker compose --profile gpu up -d
```

### 4. Lancer sans GPU (CPU uniquement)

```bash
docker compose --profile cpu up -d
```

### 5. Lancer sans Model\_Container (fallback GPT-5 uniquement)

```bash
docker compose up -d
```

Sans profil `gpu` ni `cpu`, le Model\_Container n'est pas démarré. Le LLM\_Router utilisera directement le fallback GPT-5 (nécessite `LLM_FALLBACK_URL` et `LLM_FALLBACK_API_KEY` dans `.env`).

## Model\_Container — Configuration GPU

Le service `model` utilise le runtime NVIDIA pour le passthrough GPU :

```yaml
model:
  image: ghcr.io/ggerganov/llama.cpp:server
  ports:
    - "8080:8080"
  volumes:
    - ./model:/models:ro
  environment:
    - LLAMA_ARG_MODEL=/models/MedicalQwen3-Reasoning-4B.Q8_0.gguf
    - LLAMA_ARG_CTX_SIZE=${MODEL_CONTEXT_SIZE:-4096}
    - LLAMA_ARG_N_GPU_LAYERS=${MODEL_GPU_LAYERS:-99}
    - LLAMA_ARG_THREADS=${MODEL_THREADS:-4}
    - LLAMA_ARG_HOST=0.0.0.0
    - LLAMA_ARG_PORT=8080
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: all
            capabilities: [gpu]
  profiles:
    - gpu
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
    interval: 10s
    timeout: 5s
    retries: 5
    start_period: 30s
```

**Variables d'environnement :**

| Variable | Défaut | Description |
|---|---|---|
| `LLAMA_ARG_MODEL` | — | Chemin du modèle GGUF dans le conteneur |
| `LLAMA_ARG_CTX_SIZE` | `4096` | Taille de la fenêtre de contexte (tokens) |
| `LLAMA_ARG_N_GPU_LAYERS` | `99` | Nombre de couches déchargées sur GPU (`99` = toutes) |
| `LLAMA_ARG_THREADS` | `4` | Nombre de threads CPU |
| `LLAMA_ARG_HOST` | `0.0.0.0` | Adresse d'écoute |
| `LLAMA_ARG_PORT` | `8080` | Port d'écoute |

**Prérequis GPU :**
- NVIDIA Container Toolkit installé
- Driver NVIDIA compatible avec le GPU
- `nvidia-smi` fonctionnel sur l'hôte

## Model\_Container — Fallback CPU

Le service `model-cpu` est identique mais sans accélération GPU :

```yaml
model-cpu:
  image: ghcr.io/ggerganov/llama.cpp:server
  environment:
    - LLAMA_ARG_N_GPU_LAYERS=0    # Pas de GPU
    - LLAMA_ARG_THREADS=${MODEL_THREADS:-4}
  profiles:
    - cpu
  healthcheck:
    start_period: 60s             # Démarrage plus lent sans GPU
```

Le `start_period` est augmenté à 60 secondes pour tenir compte du temps de chargement du modèle en CPU.

## Volumes et montages

| Volume / Montage | Type | Description |
|---|---|---|
| `./model:/models:ro` | Bind mount (lecture seule) | Fichier modèle GGUF |
| `./backend:/workspace/backend` | Bind mount | Code source backend (hot reload en dev) |
| `mongo_data` | Volume nommé | Données MongoDB persistantes |
| `redis_data` | Volume nommé | Données Redis persistantes |
| `localstack_data` | Volume nommé | Données S3 LocalStack |
| `prometheus_data` | Volume nommé | Métriques Prometheus (rétention 7 jours) |
| `grafana_data` | Volume nommé | Configuration Grafana |

## Services de support

### MongoDB Atlas Local

```bash
# Vérifier l'état du replica set
docker compose exec mongo mongosh --eval "rs.status()"
```

MongoDB est configuré avec `MONGODB_INIT_REPLICA_SET=true` pour supporter les transactions et le change stream.

### Redis

```bash
# Vérifier la connexion
docker compose exec redis redis-cli ping
```

### Monitoring (Grafana + Prometheus + Loki)

- Grafana : http://localhost:3001 (accès anonyme admin activé en dev)
- Prometheus : http://localhost:9090
- Les métriques backend sont exposées sur `/metrics` (authentification Basic Auth configurable via `METRICS_AUTH`)

## Vérification du déploiement

```bash
# Vérifier l'état de tous les services
docker compose ps

# Vérifier le health check du backend
curl http://localhost:8000/health

# Vérifier le health check du Model_Container
curl http://localhost:8080/health

# Vérifier le frontend
curl http://localhost:3000
```

### Logs

```bash
# Logs du Model_Container
docker compose logs model -f

# Logs du backend
docker compose logs backend -f

# Tous les logs
docker compose logs -f
```
