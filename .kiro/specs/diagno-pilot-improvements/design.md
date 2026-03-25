# Design Document — Diagno-Pilot Improvements

## Overview

Ce document décrit l'architecture technique et les décisions de conception pour les 18 améliorations de Diagno-Pilot. Les changements couvrent cinq axes : Sécurité (REQ 1–4), Robustesse backend (REQ 5–6), UX/Frontend (REQ 7–10), Données médicales (REQ 11–13), Logging/UI/Observabilité (REQ 14–18).

La stack reste inchangée : **FastAPI** (Python 3.12) + **MongoDB** (Motor async) + **Next.js 15 App Router** (TypeScript) + **React Native Expo** + **Tailwind CSS**.

Chaque amélioration est conçue pour être rétrocompatible et déployable indépendamment.

---

## Architecture

```mermaid
graph TD
    subgraph Clients
        WEB[Next.js 15 Web]
        MOB[React Native Expo]
    end

    subgraph API["FastAPI /api/v1"]
        MW_CORS[CORS Middleware]
        MW_RATE[RateLimiter Middleware]
        MW_LOG[StructuredLogger Middleware]
        MW_METRICS[Prometheus Middleware]

        R_AUTH[/auth]
        R_DIAG[/diagnose]
        R_CHAT[/chat]
        R_PAT[/patients]
        R_ADMIN[/admin/protocols\n/admin/drug-interactions]
        R_FILES[/files]
        R_METRICS[/metrics]
    end

    subgraph Services
        SVC_DIAG[DiagnosticService singleton]
        SVC_PRESC[PrescriptionService]
        SVC_ALERT[AlertService]
        SVC_LLM[LLMRouter + CircuitBreaker]
        SVC_RAG[RAGService]
    end

    subgraph Storage
        MONGO[(MongoDB)]
        COL_PROTO[antibiotic_protocols]
        COL_INTER[drug_interactions]
        COL_REFRESH[refresh_tokens]
        COL_PAT[patients]
        COL_CONS[consultations]
    end

    WEB --> MW_CORS --> MW_RATE --> MW_LOG --> MW_METRICS
    MOB --> MW_CORS

    MW_METRICS --> R_AUTH & R_DIAG & R_CHAT & R_PAT & R_ADMIN & R_FILES
    R_DIAG --> SVC_DIAG --> SVC_LLM --> SVC_RAG
    R_DIAG --> SVC_PRESC --> COL_PROTO
    R_DIAG --> SVC_ALERT --> COL_INTER
    R_AUTH --> COL_REFRESH
    R_PAT --> COL_PAT & COL_CONS
    R_ADMIN --> COL_PROTO & COL_INTER
    R_METRICS --> MONGO
```

---

## Components and Interfaces

### REQ 1 — Restriction CORS en production

**Décision** : Valider `ALLOWED_ORIGINS` au démarrage via un validateur Pydantic dans `Settings`. Si `ENV=production` et `ALLOWED_ORIGINS="*"`, lever une `ValueError` avant que l'app ne démarre.

```python
# backend/core/config.py (ajout)
class Settings(BaseSettings):
    ENV: str = "development"
    ALLOWED_ORIGINS: str = "*"

    @model_validator(mode="after")
    def validate_cors_in_production(self) -> "Settings":
        if self.ENV == "production" and self.ALLOWED_ORIGINS.strip() in ("*", ""):
            raise ValueError(
                "ALLOWED_ORIGINS must be an explicit list in production (ENV=production). "
                "Set ALLOWED_ORIGINS=https://app.example.com,https://api.example.com"
            )
        return self
```

### REQ 2 — Rate Limiting

**Décision** : Utiliser `slowapi` (wrapper `limits` pour FastAPI). Stockage en mémoire par défaut, Redis optionnel via `RATE_LIMIT_STORAGE_URI`. En cas d'indisponibilité du backend de stockage, le middleware laisse passer les requêtes (`swallow_errors=True`).

```python
# backend/core/rate_limit.py
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=settings.RATE_LIMIT_STORAGE_URI,
    swallow_errors=True,
)
```

Limites appliquées via décorateurs sur les routes :
- `POST /diagnose/symptoms` → `"30/minute"` (par user_id)
- `POST /chat/message` → `"60/minute"` (par user_id)
- Endpoints publics → `"10/minute"` (par IP)

### REQ 3 — Validation des fichiers uploadés

**Décision** : Nouveau composant `FileValidator` dans `backend/core/file_validator.py`. Utilise `python-magic` pour la détection MIME réelle.

```python
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "text/csv",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024  # 20 Mo
```

Validation en 3 étapes : taille → magic bytes MIME → nom de fichier (regex `\.\.[/\\]`).

### REQ 4 — Refresh Token JWT

**Décision** : Nouveau endpoint `POST /api/v1/auth/refresh`. Les refresh tokens sont des UUID opaques stockés dans la collection MongoDB `refresh_tokens` avec TTL index (7 jours). Rotation systématique à chaque usage.

```python
# Collection refresh_tokens
{
  "_id": ObjectId,
  "token": str,          # UUID opaque, indexé unique
  "user_id": ObjectId,
  "expires_at": datetime, # TTL index MongoDB
  "revoked": bool
}
```

L'`AuthContext` web intercepte les 401 via un wrapper `fetchWithRefresh` qui tente le refresh silencieux avant de rediriger vers `/login`.

### REQ 5 — Circuit Breaker LLMRouter

**Décision** : Implémenter un `CircuitBreaker` simple dans `backend/core/circuit_breaker.py` sans dépendance externe. États : `CLOSED` → `OPEN` → `HALF_OPEN`.

```python
class CircuitBreaker:
    def __init__(self, failure_threshold=5, recovery_timeout=120): ...
    async def call(self, coro): ...  # lève CircuitOpenError si ouvert
```

`LLMRouter` enveloppe l'appel primaire dans le circuit breaker. Si `CircuitOpenError`, route directement vers le fallback.

### REQ 6 — Validation des réponses LLM + Singleton DiagnosticService

**Décision** : Ajouter une méthode `_validate_diagnoses()` dans `DiagnosticService` qui vérifie :
- 1 ≤ len(diagnoses) ≤ 10
- Chaque item a `condition` non vide et `probability` ∈ [0, 1]
- `icd_code` si présent correspond à `^[A-Z][0-9]{2}(\.[0-9]{1,4})?$`

En cas d'échec de validation → log de la réponse brute + `HTTPException(502, "llm_response_invalid")`.

**Singleton** : `DiagnosticService` instancié une fois dans `lifespan()` de `main.py` et injecté via `app.state.diagnostic_service`. La dépendance FastAPI lit depuis `request.app.state`.

### REQ 7 — Persistance session JWT (web + mobile)

**Web** : L'`AuthContext` appelle déjà `GET /api/v1/auth/me` au montage. Amélioration : maintenir `isLoading=true` jusqu'à résolution, et intercepter les 401 sur tous les appels API pour déclencher le refresh (REQ 4).

**Mobile** : `AuthContext` Expo utilise `expo-secure-store` pour persister le token. Au démarrage, lit le token depuis `SecureStore`, appelle `/auth/me`, restaure l'état.

```typescript
// apps/mobile/src/contexts/AuthContext.tsx
import * as SecureStore from 'expo-secure-store';
const TOKEN_KEY = 'diagno_access_token';
```

### REQ 8 — Pagination patients

**Backend** : Modifier `GET /api/v1/patients` pour accepter `page` et `page_size`. Retourner `PaginatedResponse[PatientProfile]`.

```python
class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
```

**Frontend** : Composant `Pagination` réutilisable dans `apps/web/src/components/Pagination.tsx`. La `PatientsPage` gère l'état `page` en query param URL (`?page=2`) pour la navigation browser.

### REQ 9 — Feedback formulaires temps réel

**Décision** : Validation inline via `react-hook-form` + `zod` sur les formulaires web. Schémas de validation :
- `DiagnosePage` : symptôme texte libre ≥ 3 caractères
- `CreatePatientModal` : `full_name` non vide, `weight_kg` > 0 si renseigné

Toast de confirmation via un composant `Toast` positionné en haut à droite (REQ 17).

### REQ 10 — Tests composants mobiles

**Décision** : Utiliser `@testing-library/react-native` + `jest` (déjà configuré via Expo). Tests à créer dans `apps/mobile/src/components/__tests__/` et `apps/mobile/src/contexts/__tests__/`.

### REQ 11 — Protocoles antibiotiques configurables

**Décision** : Nouvelle collection MongoDB `antibiotic_protocols`. `PrescriptionService` charge les protocoles depuis MongoDB au démarrage (cache en mémoire) et recharge à chaque PUT/POST admin. Fallback sur `ANTIBIOTIC_PROTOCOLS` dict si collection vide.

Nouveaux endpoints dans `backend/routers/admin.py` :
- `GET /api/v1/admin/protocols`
- `POST /api/v1/admin/protocols`
- `PUT /api/v1/admin/protocols/{name}`

### REQ 12 — Interactions médicamenteuses en DB

**Décision** : Nouvelle collection MongoDB `drug_interactions`. `AlertService` charge les interactions au démarrage. Nouveau endpoint `POST /api/v1/admin/drug-interactions`. Rechargement à chaud via méthode `reload_interactions()`.

### REQ 13 — Calcul automatique age_group

**Décision** : Ajouter un `@model_validator(mode="after")` dans `PatientProfile` et `PatientCreate`. Si `date_of_birth` est présent, calculer `age_group` et ignorer la valeur fournie explicitement.

```python
@model_validator(mode="after")
def compute_age_group(self) -> "PatientProfile":
    if self.date_of_birth:
        self.age_group = _compute_age_group(self.date_of_birth)
    return self
```

### REQ 14 — Logging structuré JSON

**Décision** : Remplacer `logging.basicConfig` par un handler `python-json-logger` (`pythonjsonlogger`). Configurable via `LOG_LEVEL` et `LOG_FORMAT`. Le middleware HTTP existant est enrichi avec `request_id` (UUID par requête), `method`, `path`, `status_code`, `duration_ms`.

### REQ 15 — Navigation persistante

**Web** : `NavBar` déjà existant. Améliorations :
- Indicateur de page active via `usePathname()` de Next.js
- Menu hamburger responsive (drawer latéral sur mobile web) via état `isOpen`
- Affichage nom + rôle utilisateur

**Mobile** : Ajouter l'onglet `Profil` dans `apps/mobile/app/(tabs)/_layout.tsx`.

### REQ 16 — Images libres de droits

**Décision** : URLs Unsplash statiques avec `next/image` (optimisation automatique). Toutes les URLs documentées dans un fichier `apps/web/src/lib/images.ts`.

```typescript
// apps/web/src/lib/images.ts
export const IMAGES = {
  heroHome: "https://images.unsplash.com/photo-1576091160550-2173dba999ef?w=1200&q=80",
  // Médecin africain en consultation — Unsplash (licence libre)
  loginSide: "https://images.unsplash.com/photo-1559757148-5c350d0d3c56?w=800&q=80",
  // Stéthoscope sur bureau médical — Unsplash (licence libre)
  diagnoseHeader: "https://images.unsplash.com/photo-1584820927498-cfe5211fd8bf?w=600&q=80",
  // Consultation médicale — Unsplash (licence libre)
  patientsEmpty: "https://images.unsplash.com/photo-1631217868264-e5b90bb7e133?w=400&q=80",
  // Dossier médical vide — Unsplash (licence libre)
} as const;
```

### REQ 17 — Design system

**Décision** : Étendre `tailwind.config.ts` avec la palette médicale. Composants partagés à créer :
- `SkeletonLoader` — skeleton screens pour listes async
- `EmptyState` — état vide illustré avec CTA
- `Toast` — notifications non-bloquantes (haut droite)

### REQ 18 — Métriques Prometheus

**Décision** : Utiliser `prometheus-fastapi-instrumentator` pour les métriques HTTP. Métriques LLM custom via `prometheus_client` (Counter + Histogram). Endpoint `/metrics` protégé par HTTP Basic Auth via variable `METRICS_AUTH` (`user:password`).

---

## Data Models

### MongoDB — Nouvelles collections

#### `refresh_tokens`
```json
{
  "_id": "ObjectId",
  "token": "string (UUID, unique index)",
  "user_id": "ObjectId (ref: users)",
  "expires_at": "ISODate (TTL index: 7 jours)",
  "revoked": "boolean"
}
```

#### `antibiotic_protocols`
```json
{
  "_id": "ObjectId",
  "name": "string (unique index, lowercase)",
  "paediatric_dose_per_kg": "float",
  "adult_max_dose_mg": "float",
  "frequency": "string",
  "duration_days": "int",
  "route": "string",
  "renal_adjustment_factor": "float (0-1)",
  "hepatic_adjustment_factor": "float (0-1)",
  "contraindicated_age_groups": ["string"],
  "alternative": "string | null",
  "updated_by": "string",
  "updated_at": "ISODate"
}
```

#### `drug_interactions`
```json
{
  "_id": "ObjectId",
  "drug_a": "string (lowercase)",
  "drug_b": "string (lowercase)",
  "level": "critical | warning",
  "message": "string",
  "created_by": "string",
  "created_at": "ISODate"
}
```

### Pydantic — Modèles modifiés

#### `PatientProfile` (ajout du validateur age_group)
```python
class PatientProfile(BaseModel):
    # ... champs existants ...
    age_group: AgeGroup | None = None  # calculé automatiquement si date_of_birth présent

    @model_validator(mode="after")
    def compute_age_group(self) -> "PatientProfile":
        if self.date_of_birth is not None:
            self.age_group = _compute_age_group(self.date_of_birth)
        return self
```

#### `PaginatedResponse[T]` (nouveau)
```python
from typing import Generic, TypeVar
T = TypeVar("T")

class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
```

#### `Settings` (ajouts)
```python
class Settings(BaseSettings):
    ENV: str = "development"
    RATE_LIMIT_STORAGE_URI: str = "memory://"
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"  # "json" | "text"
    METRICS_AUTH: str = ""    # "user:password" pour /metrics
    JWT_REFRESH_EXPIRE_DAYS: int = 7
    JWT_EXPIRE_MINUTES: int = 15  # réduit de 60 à 15
```

### TypeScript — Interfaces modifiées

#### `PaginatedResponse<T>`
```typescript
interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}
```

#### `AuthContextValue` (ajout refresh)
```typescript
interface AuthContextValue {
  user: AuthUser | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  // refresh géré en interne, pas exposé
}
```

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1 : Configuration CORS invalide en production lève une erreur

*Pour toute* combinaison de variables d'environnement où `ENV=production` et `ALLOWED_ORIGINS` est vide, absent, ou égal à `"*"`, l'instanciation de `Settings` doit lever une `ValueError` avec un message explicite.

**Validates: Requirements 1.1, 1.4**

---

### Property 2 : Round-trip parsing des origines CORS

*Pour toute* liste non vide d'URLs d'origines valides, joindre la liste par virgule puis la passer à `Settings.ALLOWED_ORIGINS` doit produire exactement la même liste après parsing (ordre préservé, espaces ignorés).

**Validates: Requirements 1.2**

---

### Property 3 : Rate limiter retourne 429 avec Retry-After au dépassement

*Pour tout* utilisateur authentifié qui émet plus de N requêtes par minute sur un endpoint limité (N = 30 pour `/diagnose/symptoms`, N = 60 pour `/chat/message`), la réponse à la (N+1)ème requête doit avoir le statut HTTP 429 et contenir l'en-tête `Retry-After`.

**Validates: Requirements 2.1, 2.2, 2.3**

---

### Property 4 : FileValidator rejette tout fichier dépassant 20 Mo

*Pour tout* fichier dont la taille en octets est strictement supérieure à 20 971 520 (20 × 1024²), `FileValidator.validate()` doit lever une exception correspondant à HTTP 413, quelle que soit la nature du contenu.

**Validates: Requirements 3.1**

---

### Property 5 : FileValidator rejette les MIME types non autorisés

*Pour tout* fichier dont le MIME type réel (détecté par magic bytes) n'appartient pas à l'ensemble `{application/pdf, image/jpeg, image/png, text/csv, application/vnd.openxmlformats-officedocument.spreadsheetml.sheet}`, `FileValidator.validate()` doit rejeter le fichier.

**Validates: Requirements 3.2, 3.3**

---

### Property 6 : FileValidator rejette les noms de fichier avec traversée de répertoire

*Pour tout* nom de fichier contenant la sous-chaîne `../` ou `..\`, `FileValidator.validate_filename()` doit retourner `False` (rejet), quelle que soit la position de la séquence dans le nom.

**Validates: Requirements 3.5**

---

### Property 7 : Rotation des refresh tokens — l'ancien token est invalidé après usage

*Pour tout* refresh token valide `T`, après un appel réussi à `POST /auth/refresh` avec `T`, une seconde utilisation de `T` doit retourner HTTP 401 avec le message `"refresh_token_invalid"`.

**Validates: Requirements 4.3, 4.4**

---

### Property 8 : Circuit breaker s'ouvre après N échecs consécutifs

*Pour tout* nombre d'échecs consécutifs ≥ 5 sur le LLM primaire dans une fenêtre de 60 secondes, le `CircuitBreaker` doit passer à l'état `OPEN` et toute requête suivante doit être routée vers le LLM fallback sans tenter le primaire.

**Validates: Requirements 5.1, 5.2**

---

### Property 9 : Circuit breaker passe en half-open après la période de récupération

*Pour tout* circuit en état `OPEN`, après un délai simulé de 120 secondes, le circuit doit passer à l'état `HALF_OPEN` et laisser passer exactement une requête de test vers le LLM primaire.

**Validates: Requirements 5.3**

---

### Property 10 : Invariants structurels des diagnostics LLM

*Pour toute* réponse LLM parsée avec succès par `DiagnosticService._validate_diagnoses()`, la liste résultante doit satisfaire simultanément : (a) 1 ≤ len(diagnoses) ≤ 10, (b) chaque `condition` est une chaîne non vide, (c) chaque `probability` ∈ [0.0, 1.0], (d) chaque `icd_code` présent correspond au regex `^[A-Z][0-9]{2}(\.[0-9]{1,4})?$`.

**Validates: Requirements 6.1, 6.3, 6.4**

---

### Property 11 : Pagination — cohérence des métadonnées de réponse

*Pour tout* appel à `GET /api/v1/patients?page=P&page_size=S` avec P ≥ 1 et 1 ≤ S ≤ 100, la réponse doit satisfaire : `len(items) ≤ S`, `page == P`, `page_size == S`, et si `P * S > total` alors `len(items) == 0`.

**Validates: Requirements 8.1, 8.2, 8.3**

---

### Property 12 : Validation formulaire — texte libre de symptômes

*Pour toute* chaîne de caractères de longueur strictement inférieure à 3 (après trim), le bouton de soumission de `DiagnosePage` doit être désactivé (`disabled=true`).

**Validates: Requirements 9.1**

---

### Property 13 : Validation formulaire — weight_kg doit être positif

*Pour toute* valeur `weight_kg` ≤ 0 soumise dans `CreatePatientModal`, la validation doit échouer et afficher un message d'erreur inline, sans effacer les autres champs du formulaire.

**Validates: Requirements 9.2**

---

### Property 14 : PrescriptionService utilise la version DB en priorité sur le dict codé en dur

*Pour tout* protocole antibiotique présent dans la collection MongoDB `antibiotic_protocols`, `PrescriptionService.calculate_prescription()` doit utiliser les valeurs de la DB plutôt que celles du dict `ANTIBIOTIC_PROTOCOLS`, même si les deux existent.

**Validates: Requirements 11.4**

---

### Property 15 : Symétrie des interactions médicamenteuses

*Pour toute* paire de médicaments (A, B) présente dans la collection `drug_interactions`, `AlertService._check_interactions()` doit générer la même alerte que la paire soit présentée dans l'ordre (A prescrit, B en médication courante) ou (B prescrit, A en médication courante).

**Validates: Requirements 12.4**

---

### Property 16 : Calcul automatique de age_group depuis date_of_birth

*Pour toute* date de naissance valide `dob`, la création d'un `PatientProfile` avec `date_of_birth=dob` doit produire un `age_group` correspondant exactement aux règles : 0–28 jours → `neonatal`, 29 jours–23 mois → `infant`, 2–17 ans → `child`, 18 ans et plus → `adult`.

**Validates: Requirements 13.1**

---

### Property 17 : Idempotence du calcul de age_group

*Pour toute* date de naissance valide `dob`, calculer `age_group` depuis `dob` puis recalculer depuis la même `dob` doit produire le même résultat (f(dob) == f(f_inverse(f(dob)))).

**Validates: Requirements 13.5**

---

### Property 18 : Structure JSON des entrées de log

*Pour tout* événement de log émis par `StructuredLogger`, la sortie doit être un objet JSON valide sur une seule ligne contenant au minimum les champs `timestamp` (ISO 8601), `level`, `message`, `service`, et `request_id`.

**Validates: Requirements 14.1, 14.2**

---

### Property 19 : Compteur de métriques LLM s'incrémente à chaque échec

*Pour tout* appel au LLM primaire qui lève une `LLMUnavailableError`, le compteur Prometheus `diagno_pilot_llm_requests_total{model="qwen3", status="error"}` doit s'incrémenter exactement de 1.

**Validates: Requirements 18.2**

---

### Property 20 : Attribut alt présent sur toutes les images

*Pour tout* composant React qui rend un élément `<Image>` ou `<img>`, l'attribut `alt` doit être une chaîne non vide.

**Validates: Requirements 16.6**

---

## Error Handling

### Erreurs de configuration au démarrage
- `Settings` lève `ValueError` si la configuration est invalide en production → l'app ne démarre pas, le message est loggé en CRITICAL.

### Erreurs LLM
- `LLMUnavailableError` sur le primaire → circuit breaker incrémente le compteur d'échecs, route vers fallback.
- Les deux LLM indisponibles → HTTP 503 `"llm_unavailable"`.
- Réponse LLM non parseable → HTTP 502 `"llm_response_invalid"` + log de la réponse brute.

### Erreurs d'authentification
- JWT expiré → HTTP 401 ; l'`AuthContext` tente le refresh silencieux.
- Refresh token révoqué/expiré → HTTP 401 `"refresh_token_invalid"` → redirect login.

### Erreurs de validation fichier
- Taille > 20 Mo → HTTP 413.
- MIME type non autorisé ou discordant → HTTP 415.
- Nom de fichier avec traversée → HTTP 400.
- Tous les rejets sont loggés avec IP, nom de fichier, raison.

### Erreurs de rate limiting
- Dépassement de limite → HTTP 429 + `Retry-After`.
- Backend de stockage indisponible → log WARNING + laisser passer (fail-open).

### Erreurs de pagination
- `page` < 1 ou `page_size` hors [1, 100] → HTTP 422 avec détail de validation Pydantic.

---

## Testing Strategy

### Approche duale

Les tests sont organisés en deux couches complémentaires :

**Tests unitaires** — exemples spécifiques, cas limites, intégrations :
- Comportement au démarrage (REQ 1 : configuration CORS invalide)
- Login retourne access + refresh token (REQ 4)
- Singleton `DiagnosticService` (REQ 6.5)
- Restauration de session au montage de `AuthContext` (REQ 7)
- Fallback interactions codées en dur si collection vide (REQ 12.5)
- Endpoint `/metrics` retourne les compteurs attendus (REQ 18)

**Tests property-based** — propriétés universelles sur des entrées générées :
- Bibliothèque Python : **Hypothesis** (déjà utilisé dans le projet, voir `.hypothesis/`)
- Bibliothèque TypeScript/React : **fast-check**
- Minimum **100 itérations** par propriété (paramètre `max_examples=100` pour Hypothesis, `numRuns: 100` pour fast-check)

### Mapping propriétés → tests

Chaque propriété du design doit être implémentée par **un seul test property-based** annoté avec :

```
# Feature: diagno-pilot-improvements, Property N: <texte de la propriété>
```

| Propriété | Fichier de test | Bibliothèque |
|-----------|----------------|--------------|
| P1 — CORS config invalide | `backend/tests/test_config.py` | Hypothesis |
| P2 — Round-trip CORS parsing | `backend/tests/test_config.py` | Hypothesis |
| P3 — Rate limiter 429 + Retry-After | `backend/tests/test_rate_limit.py` | Hypothesis |
| P4 — FileValidator taille > 20 Mo | `backend/tests/test_file_validator.py` | Hypothesis |
| P5 — FileValidator MIME non autorisé | `backend/tests/test_file_validator.py` | Hypothesis |
| P6 — FileValidator traversée répertoire | `backend/tests/test_file_validator.py` | Hypothesis |
| P7 — Rotation refresh token | `backend/tests/test_auth.py` | Hypothesis |
| P8 — Circuit breaker ouverture | `backend/tests/test_circuit_breaker.py` | Hypothesis |
| P9 — Circuit breaker half-open | `backend/tests/test_circuit_breaker.py` | Hypothesis |
| P10 — Invariants diagnostics LLM | `backend/tests/test_diagnostic_service.py` | Hypothesis |
| P11 — Pagination cohérence | `backend/tests/test_patients_router.py` | Hypothesis |
| P12 — Validation texte symptômes | `apps/web/src/app/[locale]/diagnose/__tests__/DiagnosePage.test.tsx` | fast-check |
| P13 — Validation weight_kg | `apps/web/src/components/__tests__/CreatePatientModal.test.tsx` | fast-check |
| P14 — PrescriptionService priorité DB | `backend/tests/test_prescription_service.py` | Hypothesis |
| P15 — Symétrie interactions | `backend/tests/test_alert_service.py` | Hypothesis |
| P16 — Calcul age_group | `backend/tests/test_patient_model.py` | Hypothesis |
| P17 — Idempotence age_group | `backend/tests/test_patient_model.py` | Hypothesis |
| P18 — Structure JSON logs | `backend/tests/test_structured_logger.py` | Hypothesis |
| P19 — Compteur métriques LLM | `backend/tests/test_metrics.py` | Hypothesis |
| P20 — Attribut alt images | `apps/web/src/lib/__tests__/images.test.ts` | fast-check |

### Configuration Hypothesis

```python
from hypothesis import settings, HealthCheck

settings.register_profile("ci", max_examples=100, suppress_health_check=[HealthCheck.too_slow])
settings.load_profile("ci")
```

### Configuration fast-check

```typescript
import fc from 'fast-check';
fc.configureGlobal({ numRuns: 100 });
```
