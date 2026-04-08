# Diagno-Pilot — Production Operations Guide

> **Target audience:** DevOps engineers deploying Diagno-Pilot in clinical environments in Togo and Bénin.
> **Last updated:** 2025

---

## Table of Contents

1. [Environment Variables Reference](#1-environment-variables-reference)
2. [Secrets Management](#2-secrets-management)
3. [Metrics Endpoint Security](#3-metrics-endpoint-security)
4. [Docker Compose Production Override](#4-docker-compose-production-override)
5. [Horizontal Scaling](#5-horizontal-scaling)
6. [Bandwidth Optimisation (West African Deployments)](#6-bandwidth-optimisation-west-african-deployments)
7. [Chat Session TTL and Backfill Migration](#7-chat-session-ttl-and-backfill-migration)
8. [Health Check Endpoint](#8-health-check-endpoint)
9. [JWT Secret Rotation](#9-jwt-secret-rotation)

---

## 1. Environment Variables Reference

All variables are read by `backend/core/config.py` at startup via `pydantic-settings`. Variables marked **Required in prod** will cause the backend to refuse to start if absent or set to a weak default when `ENV=production`.

### Authentication

| Variable | Type | Default | Required in prod | Description |
|---|---|---|---|---|
| `JWT_SECRET` | `string` | `change_me_…` | **Yes** | HMAC secret used to sign and verify JWT access and refresh tokens. Must be ≥ 32 characters. See [Secrets Management](#2-secrets-management). |
| `JWT_ALGORITHM` | `string` | `HS256` | No | JWT signing algorithm. |
| `JWT_EXPIRE_MINUTES` | `integer` | `15` | No | Access token lifetime in minutes. |
| `JWT_REFRESH_EXPIRE_DAYS` | `integer` | `7` | No | Refresh token lifetime in days. |

### Application

| Variable | Type | Default | Required in prod | Description |
|---|---|---|---|---|
| `ENV` | `string` | `development` | **Yes** | Runtime environment. Set to `production` to enable strict validation of secrets and CORS. |
| `ALLOWED_ORIGINS` | `string` | `*` | **Yes** | Comma-separated list of allowed CORS origins. Must be explicit in production (e.g. `https://app.example.com`). Wildcard `*` is rejected when `ENV=production`. |
| `LOG_LEVEL` | `string` | `INFO` | No | Python log level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. Set to `WARNING` in production to reduce log volume (see [Bandwidth Optimisation](#6-bandwidth-optimisation-west-african-deployments)). |
| `LOG_FORMAT` | `string` | `json` | No | Log output format: `json` (structured, for Promtail/Loki) or `text` (human-readable). Keep `json` in production. |
| `METRICS_AUTH` | `string` | `` (empty) | **Yes** | Basic Auth credentials for the `/metrics` endpoint in `user:password` format. Leave empty to disable auth (development only). See [Metrics Endpoint Security](#3-metrics-endpoint-security). |

### Database

| Variable | Type | Default | Required in prod | Description |
|---|---|---|---|---|
| `MONGODB_URI` | `string` | `mongodb://localhost:27017/diagno_pilot` | **Yes** | MongoDB connection URI. Use a replica set URI or Atlas connection string in production. |

### Cache / Redis

| Variable | Type | Default | Required in prod | Description |
|---|---|---|---|---|
| `REDIS_URL` | `string` | `redis://localhost:6379/0` | **Yes** | Redis connection URL. Must point to a shared Redis instance when running multiple backend replicas. |
| `RATE_LIMIT_STORAGE_URI` | `string` | `memory://` | **Yes** | Storage backend for rate limiting. Automatically set to `REDIS_URL` when `REDIS_URL` is explicitly provided. Must be Redis in production for cross-replica rate limiting. |
| `CACHE_TTL_PROTOCOLS` | `integer` | `3600` | No | TTL in seconds for protocol cache entries. |
| `CACHE_TTL_INTERACTIONS` | `integer` | `3600` | No | TTL in seconds for interaction cache entries. |
| `CACHE_TTL_EMBEDDINGS` | `integer` | `86400` | No | TTL in seconds for embedding cache entries. |
| `CACHE_TTL_RAG` | `integer` | `300` | No | TTL in seconds for RAG result cache entries. |
| `SOURCE_RELEVANCE_THRESHOLD` | `float` | `0.3` | No | Minimum similarity score for a retrieved chunk to be included in the response `sources` list. Chunks below this threshold are filtered out. Must be ≥ `LLAMAINDEX_SIMILARITY_THRESHOLD`. |
| `CACHE_KEY_VERSION` | `string` | `v1` | No | Cache key namespace prefix. Increment to invalidate all cached entries during a deployment. |

### LLM / Embedding

| Variable | Type | Default | Required in prod | Description |
|---|---|---|---|---|
| `LLM_PRIMARY_URL` | `string` | `None` | **Yes** | Base URL of the primary LLM endpoint (OpenAI-compatible). Example: `http://ollama-host:11434/v1`. |
| `LLM_PRIMARY_API_KEY` | `string` | `None` | **Yes** | API key for the primary LLM. |
| `LLM_FALLBACK_URL` | `string` | `None` | No | Base URL of the fallback LLM endpoint (e.g. OpenAI). |
| `LLM_FALLBACK_API_KEY` | `string` | `None` | No | API key for the fallback LLM. |
| `EMBED_MODEL` | `string` | `text-embedding-ada-002` | No | Embedding model name passed to the embeddings API. |
| `LLM_TIMEOUT` | `integer` | `60` | No | Per-request timeout in seconds for LLM calls. |
| `LLM_RETRY_MAX` | `integer` | `3` | No | Maximum number of retry attempts for failed LLM calls. |
| `LLM_RETRY_BASE_DELAY` | `float` | `1.0` | No | Base delay in seconds for exponential backoff between retries. |
| `LLM_RETRY_MAX_DELAY` | `float` | `30.0` | No | Maximum delay in seconds between retries. |

### AWS / S3

| Variable | Type | Default | Required in prod | Description |
|---|---|---|---|---|
| `AWS_ENDPOINT_URL` | `string` | `None` | No | Custom S3-compatible endpoint URL. Set only when using LocalStack or MinIO. Leave unset in production to use real AWS. |
| `AWS_ACCESS_KEY_ID` | `string` | `None` | **Yes** | AWS access key ID. Use an IAM role or instance profile where possible. |
| `AWS_SECRET_ACCESS_KEY` | `string` | `None` | **Yes** | AWS secret access key. Store in a secrets manager. |
| `AWS_DEFAULT_REGION` | `string` | `us-east-1` | No | AWS region for S3 operations. |
| `S3_BUCKET` | `string` | `diagno-pilot-files` | **Yes** | S3 bucket name for file storage. |

### Internal

| Variable | Type | Default | Required in prod | Description |
|---|---|---|---|---|
| `BACKEND_INTERNAL_URL` | `string` | `http://backend:8000` | No | Internal URL used by the Next.js auth proxy to reach the backend. Set to the Docker service name inside Docker networks. |

---

## 2. Secrets Management

### JWT_SECRET

`JWT_SECRET` is the most sensitive credential in the system. A compromised secret allows an attacker to forge authentication tokens for any user.

**Generation:**

```bash
openssl rand -hex 32
```

This produces a 64-character hexadecimal string (256 bits of entropy), which is the minimum acceptable strength.

**Storage rules:**

- Store the generated value in a secrets manager (AWS Secrets Manager, HashiCorp Vault, or equivalent).
- Inject it into the container at runtime via the secrets manager's environment variable injection mechanism.
- **Never** write the production value into a `.env` file that is committed to version control.
- The `.env.example` file in this repository contains only a placeholder value (`change_me_generate_with_openssl_rand_hex_32`). This placeholder is intentionally rejected by the backend when `ENV=production`.

**Validation at startup:**

When `ENV=production`, the backend validates `JWT_SECRET` on startup and will refuse to start if:
- The value matches any known weak placeholder.
- The value is shorter than 32 characters.

---

## 3. Metrics Endpoint Security

The `/metrics` endpoint exposes internal application telemetry (LLM latency, cache hit rates, DB query durations). This data must not be accessible to unauthenticated clients in production.

**Requirement:** `METRICS_AUTH` **must** be set to a non-empty `user:password` value in production.

```bash
# Example — generate a strong password
METRICS_PASS=$(openssl rand -hex 16)
export METRICS_AUTH="prometheus:${METRICS_PASS}"
```

Store the same credentials in your Prometheus scrape configuration:

```yaml
# docker/prometheus/prometheus.yml (production override)
scrape_configs:
  - job_name: diagno-pilot-backend
    static_configs:
      - targets: ["backend:8000"]
    metrics_path: /metrics
    basic_auth:
      username: prometheus
      password: <METRICS_PASS>
```

Leaving `METRICS_AUTH` empty disables Basic Auth and allows any client on the network to read the metrics endpoint. This is acceptable in a trusted local development network but is **not acceptable in production**.

---

## 4. Docker Compose Production Override

The base `docker-compose.yml` includes development-only services (`localstack`, `seed`) that must not run in production. Use a Compose override file to remove them and apply production settings.

Create `docker-compose.prod.yml` alongside `docker-compose.yml`:

```yaml
# docker-compose.prod.yml
# Usage: docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

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
    # Remove LocalStack dependency in production
    depends_on:
      mongo:
        condition: service_healthy
      redis:
        condition: service_healthy

  prometheus:
    command:
      - --config.file=/etc/prometheus/prometheus.yml
      - --storage.tsdb.retention.time=30d

  # Disable development-only services
  localstack:
    profiles:
      - dev-only

  seed:
    profiles:
      - dev-only
```

**Deploy command:**

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

All secret values should be injected via environment variables from your secrets manager, not from a `.env` file on disk.

---

## 5. Horizontal Scaling

Diagno-Pilot's backend is stateless at the HTTP layer but relies on two shared stateful services when running multiple replicas.

### Shared Redis Instance

The caching layer (`backend/core/cache.py`) and the rate limiter both use Redis as their storage backend. When running more than one backend replica:

- All replicas **must** connect to the **same** Redis instance.
- Set `REDIS_URL` to the shared Redis connection string on every replica.
- `RATE_LIMIT_STORAGE_URI` is automatically set to `REDIS_URL` when `REDIS_URL` is explicitly provided, ensuring rate limits are enforced across all replicas.
- A single Redis node is sufficient for most deployments. For high availability, use Redis Sentinel or Redis Cluster.

### MongoDB Replica Set or Atlas Cluster

The backend uses `AsyncIOMotorClient` for all database operations. In production:

- Use a **MongoDB replica set** (minimum 3 nodes: 1 primary, 2 secondaries) or a **MongoDB Atlas** cluster.
- A replica set provides automatic failover: if the primary node fails, a secondary is elected within seconds without manual intervention.
- The `MONGODB_URI` must include the replica set name and all member addresses:

```
mongodb://user:password@mongo1:27017,mongo2:27017,mongo3:27017/diagno_pilot?replicaSet=rs0&authSource=admin
```

- For Atlas, use the SRV connection string provided in the Atlas console:

```
mongodb+srv://user:password@cluster0.example.mongodb.net/diagno_pilot
```

- Do not use a standalone MongoDB node in production — it has no automatic failover and risks data loss on node failure.

### Load Balancer

Place a load balancer (e.g. Nginx, HAProxy, or a cloud ALB) in front of the backend replicas. Configure it to use the `/health` endpoint for health checks (see [Section 7](#7-health-check-endpoint)).

---

## 6. Bandwidth Optimisation (West African Deployments)

Deployments in Togo and Bénin often operate on constrained or metered internet connections. The following settings reduce outbound bandwidth consumption from the observability stack.

### Prometheus Scrape Interval

The default scrape interval in `docker/prometheus/prometheus.yml` is 15 seconds, which is appropriate for local development. In production, increase it to **60 seconds or more** to reduce the volume of metric data transmitted and stored.

```yaml
# docker/prometheus/prometheus.yml (production)
global:
  scrape_interval: 60s
  evaluation_interval: 60s
```

A 60-second interval reduces Prometheus ingestion traffic by approximately 75% compared to 15 seconds, with minimal impact on alert responsiveness for the alert rules defined in `docker/prometheus/alerts.yml`.

### Loki Log Volume Reduction

Set `LOG_LEVEL=WARNING` in production to suppress `INFO` and `DEBUG` log lines. This is already included in the production override in [Section 4](#4-docker-compose-production-override).

At `WARNING` level, only warnings, errors, and critical messages are emitted. In a stable deployment, this can reduce log volume by 90% or more compared to `INFO` level, significantly reducing the data pushed from Promtail to Loki.

```bash
# In docker-compose.prod.yml backend environment
LOG_LEVEL=WARNING
```

### Grafana Dashboard Export for Offline Use

When internet connectivity is unreliable, export Grafana dashboards as JSON files so they can be loaded into a local Grafana instance without requiring a live connection to a remote Grafana server.

**Export a dashboard:**

1. Open the dashboard in Grafana.
2. Click the **Share** icon (top toolbar) → **Export** tab.
3. Enable **Export for sharing externally** if the dashboard uses datasource variables.
4. Click **Save to file** — this downloads a `.json` file.

**Import a dashboard offline:**

1. In Grafana, go to **Dashboards** → **Import**.
2. Upload the `.json` file or paste its contents.
3. Map the datasource variables to the local Prometheus and Loki instances.

The pre-built dashboard is already provisioned at `docker/grafana/dashboards/diagno-pilot.json` and is loaded automatically when the stack starts. Keep this file in version control so it can be deployed to any site without internet access.

---

## 7. Chat Session TTL and Backfill Migration

### TTL Index on `chat_sessions.updated_at`

At application startup, a MongoDB TTL index is created on `chat_sessions.updated_at` with an expiry of **90 days** (7,776,000 seconds). This ensures stale chat sessions containing PHI are automatically purged.

```
Collection: chat_sessions
Field: updated_at
expireAfterSeconds: 7776000  (90 × 24 × 3600)
background: true
```

The index is created idempotently — if it already exists, MongoDB skips creation.

### `updated_at` Backfill Migration

Before the TTL index is created, a one-time idempotent migration runs at startup to backfill the `updated_at` field on existing `chat_sessions` documents that lack it:

- Documents without `updated_at` receive the value of their `created_at` field.
- If `created_at` is also missing, the current timestamp is used.
- The migration logs the number of documents updated.
- Running the migration multiple times has no effect on documents that already have `updated_at`.

This migration must complete before the TTL index is created to ensure all documents are eligible for expiry.

### Idempotency Key Index on `consultations`

A unique sparse index is created on `consultations.idempotency_key` at startup. This prevents duplicate consultation creation when clients retry diagnosis requests with the same idempotency key.

```
Collection: consultations
Field: idempotency_key
unique: true
sparse: true  (allows null values)
background: true
```

---

## 8. Health Check Endpoint

The backend exposes a `/health` endpoint that probes all downstream dependencies and returns a summary of system health.

**Endpoint:** `GET /health`

**Response schema:**

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

| Field | Type | Values | Description |
|---|---|---|---|
| `status` | `string` | `ok`, `degraded` | Overall health. `ok` only when all probes pass. |
| `db` | `string` | `ok`, `unreachable: …` | MongoDB connectivity. |
| `redis` | `string` | `ok`, `degraded` | Redis connectivity. `degraded` means the cache is operating in fallback mode. |
| `llm_primary` | `string` | `ok`, `unreachable: …` | Primary LLM endpoint reachability. |
| `llm_fallback` | `string` | `ok`, `unreachable: …` | Fallback LLM endpoint reachability. |
| `embedding` | `string` | `ok`, `unreachable: …` | Embedding API reachability. |

**HTTP status codes:**

- `200 OK` — returned regardless of the `status` field value, so that load balancers can distinguish between a running-but-degraded backend and a completely unreachable one.

**Load balancer health check configuration:**

A load balancer health check SHOULD poll `GET /health` at an interval of **no less than 10 seconds**. Polling more frequently than every 10 seconds adds unnecessary load without improving failover speed.

Recommended configuration:

| Parameter | Value |
|---|---|
| Path | `/health` |
| Protocol | HTTP |
| Interval | 10–30 s |
| Timeout | 5 s |
| Healthy threshold | 2 consecutive successes |
| Unhealthy threshold | 3 consecutive failures |

Example Nginx upstream health check (using `nginx_upstream_check_module`):

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

## 9. JWT Secret Rotation

Rotating `JWT_SECRET` invalidates all existing tokens signed with the old secret. To rotate without forcing all users to log out immediately, follow a two-phase rolling rotation.

### Phase 1 — Introduce the new secret alongside the old one

1. Generate a new secret:
   ```bash
   NEW_SECRET=$(openssl rand -hex 32)
   echo $NEW_SECRET
   ```

2. Store the new secret in your secrets manager under a new version (e.g. `jwt-secret-v2`).

3. Update the backend to **accept tokens signed with either the old or the new secret**. This requires a temporary code change to the JWT verification logic:

   ```python
   # backend/core/auth.py (temporary, during rotation window)
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

4. Deploy this version with both `JWT_SECRET` (new) and `JWT_SECRET_OLD` (old) set in the environment.

5. New tokens issued after this deployment will be signed with the new secret. Existing tokens signed with the old secret continue to work until they expire.

### Phase 2 — Remove the old secret after token expiry

1. Wait for the maximum token lifetime to pass. The longest-lived token is the refresh token (`JWT_REFRESH_EXPIRE_DAYS`, default 7 days). After 7 days, all tokens signed with the old secret will have expired naturally.

2. Remove the dual-verification logic and the `JWT_SECRET_OLD` environment variable.

3. Deploy the cleaned-up version. The system now only accepts tokens signed with the new secret.

4. Remove the old secret version from your secrets manager.

### Summary timeline

```
Day 0:  Deploy Phase 1 (dual-secret verification, new JWT_SECRET active)
Day 7+: Deploy Phase 2 (single-secret verification, old secret removed)
```

This procedure ensures zero forced logouts: users with valid refresh tokens are silently re-issued new access tokens signed with the new secret during the rotation window.

### Emergency rotation (immediate invalidation)

If the old secret is believed to be compromised, skip Phase 1 and deploy Phase 2 immediately with only the new secret. This will invalidate all active sessions and require all users to log in again. Notify clinical staff before performing an emergency rotation during working hours.
