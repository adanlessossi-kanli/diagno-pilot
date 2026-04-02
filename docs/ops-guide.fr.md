# Diagno-Pilot — Guide d'exploitation en production

> **Public cible :** Ingénieurs DevOps déployant Diagno-Pilot dans des environnements cliniques au Togo et au Bénin.
> **Dernière mise à jour :** 2025

---

## Table des matières

1. [Référence des variables d'environnement](#1-référence-des-variables-denvironnement)
2. [Gestion des secrets](#2-gestion-des-secrets)
3. [Sécurité du point de terminaison des métriques](#3-sécurité-du-point-de-terminaison-des-métriques)
4. [Surcharge Docker Compose pour la production](#4-surcharge-docker-compose-pour-la-production)
5. [Mise à l'échelle horizontale](#5-mise-à-léchelle-horizontale)
6. [Optimisation de la bande passante (déploiements en Afrique de l'Ouest)](#6-optimisation-de-la-bande-passante-déploiements-en-afrique-de-louest)
7. [Point de terminaison de vérification de l'état](#7-point-de-terminaison-de-vérification-de-létat)
8. [Rotation du secret JWT](#8-rotation-du-secret-jwt)

---

## 1. Référence des variables d'environnement

Toutes les variables sont lues par `backend/core/config.py` au démarrage via `pydantic-settings`. Les variables marquées **Obligatoire en prod** entraîneront le refus de démarrage du backend si elles sont absentes ou définies avec une valeur par défaut faible lorsque `ENV=production`.

### Authentification

| Variable | Type | Défaut | Obligatoire en prod | Description |
|---|---|---|---|---|
| `JWT_SECRET` | `string` | `change_me_…` | **Oui** | Secret HMAC utilisé pour signer et vérifier les jetons d'accès et de rafraîchissement JWT. Doit comporter ≥ 32 caractères. Voir [Gestion des secrets](#2-gestion-des-secrets). |
| `JWT_ALGORITHM` | `string` | `HS256` | Non | Algorithme de signature JWT. |
| `JWT_EXPIRE_MINUTES` | `integer` | `15` | Non | Durée de vie du jeton d'accès en minutes. |
| `JWT_REFRESH_EXPIRE_DAYS` | `integer` | `7` | Non | Durée de vie du jeton de rafraîchissement en jours. |

### Application

| Variable | Type | Défaut | Obligatoire en prod | Description |
|---|---|---|---|---|
| `ENV` | `string` | `development` | **Oui** | Environnement d'exécution. Définir à `production` pour activer la validation stricte des secrets et du CORS. |
| `ALLOWED_ORIGINS` | `string` | `*` | **Oui** | Liste des origines CORS autorisées, séparées par des virgules. Doit être explicite en production (ex. `https://app.example.com`). Le caractère générique `*` est rejeté lorsque `ENV=production`. |
| `LOG_LEVEL` | `string` | `INFO` | Non | Niveau de journalisation Python : `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. Définir à `WARNING` en production pour réduire le volume de journaux (voir [Optimisation de la bande passante](#6-optimisation-de-la-bande-passante-déploiements-en-afrique-de-louest)). |
| `LOG_FORMAT` | `string` | `json` | Non | Format de sortie des journaux : `json` (structuré, pour Promtail/Loki) ou `text` (lisible par l'humain). Conserver `json` en production. |
| `METRICS_AUTH` | `string` | `` (vide) | **Oui** | Identifiants Basic Auth pour le point de terminaison `/metrics` au format `utilisateur:motdepasse`. Laisser vide pour désactiver l'authentification (développement uniquement). Voir [Sécurité du point de terminaison des métriques](#3-sécurité-du-point-de-terminaison-des-métriques). |

### Base de données

| Variable | Type | Défaut | Obligatoire en prod | Description |
|---|---|---|---|---|
| `MONGODB_URI` | `string` | `mongodb://localhost:27017/diagno_pilot` | **Oui** | URI de connexion MongoDB. Utiliser un URI de jeu de réplicas ou une chaîne de connexion Atlas en production. |

### Cache / Redis

| Variable | Type | Défaut | Obligatoire en prod | Description |
|---|---|---|---|---|
| `REDIS_URL` | `string` | `redis://localhost:6379/0` | **Oui** | URL de connexion Redis. Doit pointer vers une instance Redis partagée lors de l'exécution de plusieurs réplicas du backend. |
| `RATE_LIMIT_STORAGE_URI` | `string` | `memory://` | **Oui** | Backend de stockage pour la limitation de débit. Automatiquement défini à `REDIS_URL` lorsque `REDIS_URL` est explicitement fourni. Doit être Redis en production pour une limitation de débit inter-réplicas. |
| `CACHE_TTL_PROTOCOLS` | `integer` | `3600` | Non | TTL en secondes pour les entrées du cache de protocoles. |
| `CACHE_TTL_INTERACTIONS` | `integer` | `3600` | Non | TTL en secondes pour les entrées du cache d'interactions. |
| `CACHE_TTL_EMBEDDINGS` | `integer` | `86400` | Non | TTL en secondes pour les entrées du cache d'embeddings. |
| `CACHE_TTL_RAG` | `integer` | `300` | Non | TTL en secondes pour les entrées du cache de résultats RAG. |
| `CACHE_KEY_VERSION` | `string` | `v1` | Non | Préfixe d'espace de noms pour les clés de cache. Incrémenter pour invalider toutes les entrées en cache lors d'un déploiement. |

### LLM / Embedding

| Variable | Type | Défaut | Obligatoire en prod | Description |
|---|---|---|---|---|
| `LLM_PRIMARY_URL` | `string` | `None` | **Oui** | URL de base du point de terminaison LLM principal (compatible OpenAI). Exemple : `http://ollama-host:11434/v1`. |
| `LLM_PRIMARY_API_KEY` | `string` | `None` | **Oui** | Clé API pour le LLM principal. |
| `LLM_FALLBACK_URL` | `string` | `None` | Non | URL de base du point de terminaison LLM de secours (ex. OpenAI). |
| `LLM_FALLBACK_API_KEY` | `string` | `None` | Non | Clé API pour le LLM de secours. |
| `EMBED_MODEL` | `string` | `text-embedding-ada-002` | Non | Nom du modèle d'embedding transmis à l'API d'embeddings. |
| `LLM_TIMEOUT` | `integer` | `60` | Non | Délai d'attente par requête en secondes pour les appels LLM. |
| `LLM_RETRY_MAX` | `integer` | `3` | Non | Nombre maximum de tentatives pour les appels LLM échoués. |
| `LLM_RETRY_BASE_DELAY` | `float` | `1.0` | Non | Délai de base en secondes pour le recul exponentiel entre les tentatives. |
| `LLM_RETRY_MAX_DELAY` | `float` | `30.0` | Non | Délai maximum en secondes entre les tentatives. |

### AWS / S3

| Variable | Type | Défaut | Obligatoire en prod | Description |
|---|---|---|---|---|
| `AWS_ENDPOINT_URL` | `string` | `None` | Non | URL de point de terminaison compatible S3 personnalisée. À définir uniquement lors de l'utilisation de LocalStack ou MinIO. Laisser non défini en production pour utiliser AWS réel. |
| `AWS_ACCESS_KEY_ID` | `string` | `None` | **Oui** | Identifiant de clé d'accès AWS. Utiliser un rôle IAM ou un profil d'instance lorsque c'est possible. |
| `AWS_SECRET_ACCESS_KEY` | `string` | `None` | **Oui** | Clé d'accès secrète AWS. Stocker dans un gestionnaire de secrets. |
| `AWS_DEFAULT_REGION` | `string` | `us-east-1` | Non | Région AWS pour les opérations S3. |
| `S3_BUCKET` | `string` | `diagno-pilot-files` | **Oui** | Nom du bucket S3 pour le stockage de fichiers. |

### Interne

| Variable | Type | Défaut | Obligatoire en prod | Description |
|---|---|---|---|---|
| `BACKEND_INTERNAL_URL` | `string` | `http://backend:8000` | Non | URL interne utilisée par le proxy d'authentification Next.js pour atteindre le backend. Définir au nom du service Docker dans les réseaux Docker. |

---

## 2. Gestion des secrets

### JWT_SECRET

`JWT_SECRET` est l'identifiant le plus sensible du système. Un secret compromis permet à un attaquant de forger des jetons d'authentification pour n'importe quel utilisateur.

**Génération :**

```bash
openssl rand -hex 32
```

Cette commande produit une chaîne hexadécimale de 64 caractères (256 bits d'entropie), ce qui constitue la force minimale acceptable.

**Règles de stockage :**

- Stocker la valeur générée dans un gestionnaire de secrets (AWS Secrets Manager, HashiCorp Vault ou équivalent).
- L'injecter dans le conteneur au moment de l'exécution via le mécanisme d'injection de variables d'environnement du gestionnaire de secrets.
- **Ne jamais** écrire la valeur de production dans un fichier `.env` commité dans le contrôle de version.
- Le fichier `.env.example` de ce dépôt ne contient qu'une valeur de substitution (`change_me_generate_with_openssl_rand_hex_32`). Cette valeur de substitution est intentionnellement rejetée par le backend lorsque `ENV=production`.

**Validation au démarrage :**

Lorsque `ENV=production`, le backend valide `JWT_SECRET` au démarrage et refusera de démarrer si :
- La valeur correspond à l'une des valeurs de substitution faibles connues.
- La valeur comporte moins de 32 caractères.

---

## 3. Sécurité du point de terminaison des métriques

Le point de terminaison `/metrics` expose la télémétrie interne de l'application (latence LLM, taux de succès du cache, durées des requêtes en base de données). Ces données ne doivent pas être accessibles aux clients non authentifiés en production.

**Exigence :** `METRICS_AUTH` **doit** être défini avec une valeur `utilisateur:motdepasse` non vide en production.

```bash
# Exemple — générer un mot de passe fort
METRICS_PASS=$(openssl rand -hex 16)
export METRICS_AUTH="prometheus:${METRICS_PASS}"
```

Stocker les mêmes identifiants dans la configuration de scraping Prometheus :

```yaml
# docker/prometheus/prometheus.yml (surcharge production)
scrape_configs:
  - job_name: diagno-pilot-backend
    static_configs:
      - targets: ["backend:8000"]
    metrics_path: /metrics
    basic_auth:
      username: prometheus
      password: <METRICS_PASS>
```

Laisser `METRICS_AUTH` vide désactive le Basic Auth et permet à tout client du réseau de lire le point de terminaison des métriques. Cela est acceptable dans un réseau de développement local de confiance, mais **n'est pas acceptable en production**.

---

## 4. Surcharge Docker Compose pour la production

Le fichier `docker-compose.yml` de base inclut des services réservés au développement (`localstack`, `seed`) qui ne doivent pas s'exécuter en production. Utiliser un fichier de surcharge Compose pour les supprimer et appliquer les paramètres de production.

Créer `docker-compose.prod.yml` à côté de `docker-compose.yml` :

```yaml
# docker-compose.prod.yml
# Utilisation : docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

services:
  backend:
    environment:
      - ENV=production
      - MONGODB_URI=${MONGODB_URI}
      - REDIS_URL=${REDIS_URL}
      - JWT_SECRET=${JWT_SECRET}
      - LLM_PRIMARY_URL=${LLM_PRIMARY_URL}
      - LLM_PRIMARY_API_KEY=${LLM_PRIMARY_API_KEY}
      - LLM_FALLBACK_URL=${LLM_FALLBACK_URL}
      - LLM_FALLBACK_API_KEY=${LLM_FALLBACK_API_KEY}
      - ALLOWED_ORIGINS=${ALLOWED_ORIGINS}
      - METRICS_AUTH=${METRICS_AUTH}
      - LOG_LEVEL=WARNING
      - LOG_FORMAT=json
      - AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}
      - AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}
      - AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION}
      - S3_BUCKET=${S3_BUCKET}
    # Supprimer la dépendance LocalStack en production
    depends_on:
      mongo:
        condition: service_healthy
      redis:
        condition: service_healthy

  prometheus:
    command:
      - --config.file=/etc/prometheus/prometheus.yml
      - --storage.tsdb.retention.time=30d

  # Désactiver les services réservés au développement
  localstack:
    profiles:
      - dev-only

  seed:
    profiles:
      - dev-only
```

**Commande de déploiement :**

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

Toutes les valeurs secrètes doivent être injectées via des variables d'environnement depuis votre gestionnaire de secrets, et non depuis un fichier `.env` sur le disque.

---

## 5. Mise à l'échelle horizontale

Le backend de Diagno-Pilot est sans état au niveau de la couche HTTP, mais repose sur deux services avec état partagés lors de l'exécution de plusieurs réplicas.

### Instance Redis partagée

La couche de cache (`backend/core/cache.py`) et le limiteur de débit utilisent tous deux Redis comme backend de stockage. Lors de l'exécution de plusieurs réplicas du backend :

- Tous les réplicas **doivent** se connecter à la **même** instance Redis.
- Définir `REDIS_URL` avec la chaîne de connexion Redis partagée sur chaque réplica.
- `RATE_LIMIT_STORAGE_URI` est automatiquement défini à `REDIS_URL` lorsque `REDIS_URL` est explicitement fourni, garantissant que les limites de débit sont appliquées sur tous les réplicas.
- Un seul nœud Redis est suffisant pour la plupart des déploiements. Pour une haute disponibilité, utiliser Redis Sentinel ou Redis Cluster.

### Jeu de réplicas MongoDB ou cluster Atlas

Le backend utilise `AsyncIOMotorClient` pour toutes les opérations en base de données. En production :

- Utiliser un **jeu de réplicas MongoDB** (minimum 3 nœuds : 1 primaire, 2 secondaires) ou un cluster **MongoDB Atlas**.
- Un jeu de réplicas assure le basculement automatique : si le nœud primaire tombe en panne, un secondaire est élu en quelques secondes sans intervention manuelle.
- Le `MONGODB_URI` doit inclure le nom du jeu de réplicas et les adresses de tous les membres :

```
mongodb://user:password@mongo1:27017,mongo2:27017,mongo3:27017/diagno_pilot?replicaSet=rs0&authSource=admin
```

- Pour Atlas, utiliser la chaîne de connexion SRV fournie dans la console Atlas :

```
mongodb+srv://user:password@cluster0.example.mongodb.net/diagno_pilot
```

- Ne pas utiliser un nœud MongoDB autonome en production — il ne dispose pas de basculement automatique et risque une perte de données en cas de défaillance du nœud.

### Équilibreur de charge

Placer un équilibreur de charge (ex. Nginx, HAProxy ou un ALB cloud) devant les réplicas du backend. Le configurer pour utiliser le point de terminaison `/health` pour les vérifications de l'état (voir [Section 7](#7-point-de-terminaison-de-vérification-de-létat)).

---

## 6. Optimisation de la bande passante (déploiements en Afrique de l'Ouest)

Les déploiements au Togo et au Bénin fonctionnent souvent sur des connexions internet limitées ou facturées à l'usage. Les paramètres suivants réduisent la consommation de bande passante sortante de la pile d'observabilité.

### Intervalle de scraping Prometheus

L'intervalle de scraping par défaut dans `docker/prometheus/prometheus.yml` est de 15 secondes, ce qui convient au développement local. En production, l'augmenter à **60 secondes ou plus** pour réduire le volume de données métriques transmises et stockées.

```yaml
# docker/prometheus/prometheus.yml (production)
global:
  scrape_interval: 60s
  evaluation_interval: 60s
```

Un intervalle de 60 secondes réduit le trafic d'ingestion Prometheus d'environ 75 % par rapport à 15 secondes, avec un impact minimal sur la réactivité des alertes pour les règles d'alerte définies dans `docker/prometheus/alerts.yml`.

### Réduction du volume de journaux Loki

Définir `LOG_LEVEL=WARNING` en production pour supprimer les lignes de journaux `INFO` et `DEBUG`. Cela est déjà inclus dans la surcharge de production de la [Section 4](#4-surcharge-docker-compose-pour-la-production).

Au niveau `WARNING`, seuls les avertissements, les erreurs et les messages critiques sont émis. Dans un déploiement stable, cela peut réduire le volume de journaux de 90 % ou plus par rapport au niveau `INFO`, réduisant considérablement les données transmises de Promtail vers Loki.

```bash
# Dans l'environnement backend de docker-compose.prod.yml
LOG_LEVEL=WARNING
```

### Export des tableaux de bord Grafana pour une utilisation hors ligne

Lorsque la connectivité internet est peu fiable, exporter les tableaux de bord Grafana sous forme de fichiers JSON afin qu'ils puissent être chargés dans une instance Grafana locale sans nécessiter de connexion active à un serveur Grafana distant.

**Exporter un tableau de bord :**

1. Ouvrir le tableau de bord dans Grafana.
2. Cliquer sur l'icône **Partager** (barre d'outils supérieure) → onglet **Exporter**.
3. Activer **Exporter pour partage externe** si le tableau de bord utilise des variables de source de données.
4. Cliquer sur **Enregistrer dans un fichier** — cela télécharge un fichier `.json`.

**Importer un tableau de bord hors ligne :**

1. Dans Grafana, aller dans **Tableaux de bord** → **Importer**.
2. Téléverser le fichier `.json` ou coller son contenu.
3. Associer les variables de source de données aux instances locales de Prometheus et Loki.

Le tableau de bord préconstruit est déjà provisionné dans `docker/grafana/dashboards/diagno-pilot.json` et est chargé automatiquement au démarrage de la pile. Conserver ce fichier dans le contrôle de version afin qu'il puisse être déployé sur n'importe quel site sans accès internet.

---

## 7. Point de terminaison de vérification de l'état

Le backend expose un point de terminaison `/health` qui sonde toutes les dépendances en aval et retourne un résumé de l'état du système.

**Point de terminaison :** `GET /health`

**Schéma de réponse :**

```json
{
  "status": "ok | degraded",
  "db": "ok | unreachable: <error message>",
  "redis": "ok | degraded",
  "llm_primary": "ok | unreachable: <error message>",
  "llm_fallback": "ok | unreachable: <error message>",
  "embedding": "ok | unreachable: <error message>"
}
```

| Champ | Type | Valeurs | Description |
|---|---|---|---|
| `status` | `string` | `ok`, `degraded` | État global. `ok` uniquement lorsque toutes les sondes réussissent. |
| `db` | `string` | `ok`, `unreachable: …` | Connectivité MongoDB. |
| `redis` | `string` | `ok`, `degraded` | Connectivité Redis. `degraded` signifie que le cache fonctionne en mode de secours. |
| `llm_primary` | `string` | `ok`, `unreachable: …` | Accessibilité du point de terminaison LLM principal. |
| `llm_fallback` | `string` | `ok`, `unreachable: …` | Accessibilité du point de terminaison LLM de secours. |
| `embedding` | `string` | `ok`, `unreachable: …` | Accessibilité de l'API d'embedding. |

**Codes de statut HTTP :**

- `200 OK` — retourné quelle que soit la valeur du champ `status`, afin que les équilibreurs de charge puissent distinguer un backend en cours d'exécution mais dégradé d'un backend complètement inaccessible.

**Configuration de la vérification de l'état de l'équilibreur de charge :**

La vérification de l'état d'un équilibreur de charge DEVRAIT interroger `GET /health` à un intervalle d'**au moins 10 secondes**. Interroger plus fréquemment que toutes les 10 secondes ajoute une charge inutile sans améliorer la vitesse de basculement.

Configuration recommandée :

| Paramètre | Valeur |
|---|---|
| Chemin | `/health` |
| Protocole | HTTP |
| Intervalle | 10–30 s |
| Délai d'attente | 5 s |
| Seuil sain | 2 succès consécutifs |
| Seuil défaillant | 3 échecs consécutifs |

Exemple de vérification de l'état d'un upstream Nginx (avec `nginx_upstream_check_module`) :

```nginx
upstream backend {
    server backend1:8000;
    server backend2:8000;
    check interval=10000 rise=2 fall=3 timeout=5000 type=http;
    check_http_send "GET /health HTTP/1.0\r\n\r\n";
    check_http_expect_alive http_2xx;
}
```

---

## 8. Rotation du secret JWT

La rotation de `JWT_SECRET` invalide tous les jetons existants signés avec l'ancien secret. Pour effectuer une rotation sans forcer immédiatement la déconnexion de tous les utilisateurs, suivre une rotation progressive en deux phases.

### Phase 1 — Introduire le nouveau secret aux côtés de l'ancien

1. Générer un nouveau secret :
   ```bash
   NEW_SECRET=$(openssl rand -hex 32)
   echo $NEW_SECRET
   ```

2. Stocker le nouveau secret dans votre gestionnaire de secrets sous une nouvelle version (ex. `jwt-secret-v2`).

3. Mettre à jour le backend pour **accepter les jetons signés avec l'ancien ou le nouveau secret**. Cela nécessite une modification temporaire du code de la logique de vérification JWT :

   ```python
   # backend/core/auth.py (temporaire, pendant la fenêtre de rotation)
   OLD_SECRET = os.environ["JWT_SECRET_OLD"]
   NEW_SECRET = os.environ["JWT_SECRET"]

   def verify_token(token: str) -> dict:
       for secret in [NEW_SECRET, OLD_SECRET]:
           try:
               return jwt.decode(token, secret, algorithms=[settings.JWT_ALGORITHM])
           except JWTError:
               continue
       raise HTTPException(status_code=401, detail="Invalid token")
   ```

4. Déployer cette version avec `JWT_SECRET` (nouveau) et `JWT_SECRET_OLD` (ancien) tous deux définis dans l'environnement.

5. Les nouveaux jetons émis après ce déploiement seront signés avec le nouveau secret. Les jetons existants signés avec l'ancien secret continuent de fonctionner jusqu'à leur expiration.

### Phase 2 — Supprimer l'ancien secret après l'expiration des jetons

1. Attendre que la durée de vie maximale des jetons soit écoulée. Le jeton à la durée de vie la plus longue est le jeton de rafraîchissement (`JWT_REFRESH_EXPIRE_DAYS`, 7 jours par défaut). Après 7 jours, tous les jetons signés avec l'ancien secret auront expiré naturellement.

2. Supprimer la logique de double vérification et la variable d'environnement `JWT_SECRET_OLD`.

3. Déployer la version nettoyée. Le système n'accepte désormais que les jetons signés avec le nouveau secret.

4. Supprimer l'ancienne version du secret de votre gestionnaire de secrets.

### Calendrier récapitulatif

```
Jour 0 :  Déployer la Phase 1 (double vérification des secrets, nouveau JWT_SECRET actif)
Jour 7+ : Déployer la Phase 2 (vérification à secret unique, ancien secret supprimé)
```

Cette procédure garantit zéro déconnexion forcée : les utilisateurs disposant de jetons de rafraîchissement valides se voient silencieusement réémettre de nouveaux jetons d'accès signés avec le nouveau secret pendant la fenêtre de rotation.

### Rotation d'urgence (invalidation immédiate)

Si l'ancien secret est suspecté d'être compromis, ignorer la Phase 1 et déployer directement la Phase 2 avec uniquement le nouveau secret. Cela invalidera toutes les sessions actives et obligera tous les utilisateurs à se reconnecter. Informer le personnel clinique avant d'effectuer une rotation d'urgence pendant les heures de travail.
