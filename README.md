# Diagno-Pilot

Application web et mobile d'aide au diagnostic des maladies infectieuses et à la prescription antibiotique, destinée aux professionnels de santé en Afrique de l'Ouest (Togo, Bénin). Couvre la pédiatrie et la médecine adulte. Disponible en français et en anglais.

---

## Fonctionnalités

- **Mode guidé** — saisie des symptômes, diagnostic différentiel (≥3 diagnostics avec score de probabilité et code CIM-10), prescription antibiotique adaptée au profil patient
- **Calcul pédiatrique** — dose au poids (mg/kg), plafonnement à la dose adulte, ajustements rénaux/hépatiques
- **Alertes de sécurité** — allergies, interactions médicamenteuses, contre-indications par âge ; alertes critiques bloquantes avec alternative thérapeutique
- **Chat Q&A médical** — assistant conversationnel multi-tours alimenté exclusivement par le LLM médical (pas de RAG, pas de citations de sources), avec Topic Guard restreignant les réponses aux maladies tropicales, infectieuses, médecine clinique, nutrition, santé mentale et éthique médicale. Mécanisme de feedback intégré pour signaler les refus erronés.
- **Chat Documents RAG** — chat contextuel sur la page Documents utilisant le pipeline RAG LlamaIndex pour interroger les documents médicaux indexés, avec citations cliquables renvoyant au passage source dans le PDF (surbrillance bbox). Historique des sessions, gestion multi-tours, et barre latérale pour l'upload/liste/téléchargement des documents.
- **Dossier patient** — profils persistés, historique des consultations, upload de fichiers cliniques (labo, imagerie, PDF, CSV) vers S3
- **Administration** — indexation de documents médicaux, gestion des utilisateurs
- **Audit & traçabilité** — journal d'audit complet pour toutes les actions sensibles
- **i18n** — interface en français et en anglais, détection automatique de la langue

---

## Stack technique

| Couche | Technologie |
|---|---|
| Frontend web | Next.js (App Router) + TypeScript |
| Mobile | React Native (Expo) |
| Backend | Python 3.12 + FastAPI |
| Base de données | MongoDB Atlas (données + Vector Search) |
| LLM principal | MedicalQwen3-Reasoning-14B |
| LLM fallback | GPT-5 |
| Pipeline MCP | JSON-RPC 2.0 sur HTTP+SSE (4 serveurs agents Docker) |
| Stockage fichiers | AWS S3 (LocalStack en local) |
| Tests backend | pytest + Hypothesis (property-based testing) |
| Tests frontend | Vitest + React Testing Library |

---

## Structure du projet

```
diagno-pilot/
├── apps/
│   ├── web/          # Next.js App Router
│   └── mobile/       # React Native (Expo)
├── packages/
│   ├── ui/           # Composants React partagés web/mobile
│   ├── api-client/   # Client HTTP partagé
│   ├── types/        # Types TypeScript partagés
│   └── i18n/         # Traductions FR/EN
├── backend/          # FastAPI + services + modèles
│   └── agents/mcp_servers/  # Serveurs MCP spécialistes (Épidémiologie, Symptomatologie, Laboratoire, Traitement)
├── scripts/          # Scripts d'initialisation (LocalStack)
├── docker-compose.yml
├── start.sh / start.bat
└── stop.sh / stop.bat
```

---

## Prérequis

- [Docker](https://docs.docker.com/get-docker/) et Docker Compose
- Node.js ≥ 22 (pour le développement local hors Docker)
- Python 3.12 (pour le développement local hors Docker)

---

## Démarrage rapide

### 1. Configurer les variables d'environnement

Copier et adapter le fichier `.env` à la racine :

```env
LLM_PRIMARY_URL=http://localhost:11434/v1   # URL de MedicalQwen3 (ex. Ollama)
LLM_PRIMARY_API_KEY=your_key
LLM_FALLBACK_URL=https://api.openai.com/v1  # GPT-5
LLM_FALLBACK_API_KEY=your_openai_key
EMBED_MODEL=text-embedding-ada-002
JWT_SECRET=change_this_to_a_strong_secret_32chars
MONGODB_URI=mongodb://diagno_dev:diagno_dev_pass@mongo:27017/diagno_pilot?authSource=admin
MONGO_USERNAME=diagno_dev
MONGO_PASSWORD=diagno_dev_pass
REDIS_PASSWORD=diagno_redis_dev
```

### 2. Démarrer l'application

**Linux / macOS**
```bash
chmod +x start.sh stop.sh   # une seule fois
./start.sh
```

**Windows**
```bat
start.bat
```

### 3. Accéder aux services

| Service | URL |
|---|---|
| Frontend web | http://localhost:3000 |
| API backend | http://localhost:8000 |
| Docs API (Swagger) | http://localhost:8000/docs |
| MongoDB | mongodb://localhost:27017 |
| LocalStack (S3) | http://localhost:4566 |

> **Note :** Les serveurs MCP agents (Épidémiologie, Symptomatologie, Laboratoire, Traitement) communiquent uniquement via le réseau Docker interne et ne sont pas exposés sur l'hôte.

### 4. Comptes par défaut

| Email | Mot de passe | Rôle |
|---|---|---|
| admin@diagno-pilot.com | Admin1234! | admin |
| medecin@diagno-pilot.com | Medecin1234! | medecin |

> Le script de seed crée ces comptes automatiquement au premier démarrage. Relancer manuellement : `python scripts/seed.py`

### 5. Exécuter la migration MCP (si mise à jour)

```bash
python -m backend.scripts.migrate_consultations_add_mcp_fields
```

> Ce script ajoute les champs MCP (`mcp_session_id`, `agent_contributions`, `evidence_citations`) aux consultations existantes et crée les index nécessaires. Idempotent — peut être relancé sans risque.

### 6. Migration de la refonte Assistant Q&A et Documents

```bash
python -m backend.scripts.migrate_redesign
```

> **⚠ Attention : cette migration supprime définitivement toutes les sessions de chat Q&A existantes.** Les sessions ne peuvent pas être restaurées. Elle crée également les index pour les collections `document_chat_sessions` et `topic_guard_feedback`. Idempotent — peut être relancée sans risque.

### 7. Migration des volumes MongoDB existants

Si vous mettez à jour depuis une version sans authentification MongoDB, supprimez le volume existant avant le premier démarrage :

```bash
docker compose down -v
```

> **Attention :** `MONGODB_INITDB_ROOT_USERNAME` n'est exécuté que sur un volume vierge. Sans cette étape, MongoDB démarrera sans authentification et les services ne pourront pas se connecter.

### 8. Arrêter l'application

```bash
./stop.sh        # Linux/macOS
stop.bat         # Windows
```

---

## Configuration de l'environnement

### Authentification MongoDB

Le backend se connecte à MongoDB via `MONGODB_URI`. En environnement Docker, cette URI doit inclure les identifiants correspondant à la configuration Docker Compose :

```env
MONGODB_URI=mongodb://diagno_dev:diagno_dev_pass@mongo:27017/diagno_pilot?authSource=admin
MONGO_USERNAME=diagno_dev
MONGO_PASSWORD=diagno_dev_pass
```

> **Note :** `MONGODB_INITDB_ROOT_USERNAME` n'est exécuté que sur un volume vierge. Si vous migrez depuis une version sans authentification, supprimez le volume avec `docker compose down -v` avant le premier démarrage.

### Authentification Redis

Redis utilise un mot de passe configuré via `REDIS_URL` :

```env
REDIS_URL=redis://:diagno_redis_dev@redis:6379/0
REDIS_PASSWORD=diagno_redis_dev
```

Si Redis est inaccessible ou si l'authentification échoue, l'application continue en mode dégradé (cache désactivé) avec un avertissement dans les logs.

### Configuration des endpoints LLM

Le `LLMRouter` sélectionne le LLM principal selon cet ordre de priorité :

1. `MODEL_CONTAINER_URL` — utilisé si non vide (ex. `http://model:8080/v1` pour un conteneur Docker local)
2. `LLM_PRIMARY_URL` — utilisé si `MODEL_CONTAINER_URL` est vide (valeur par défaut)

```env
MODEL_CONTAINER_URL=              # Vide par défaut — mettre l'URL du conteneur modèle si applicable
LLM_PRIMARY_URL=http://localhost:11434/v1   # URL Ollama / MedicalQwen3
LLM_FALLBACK_URL=https://api.openai.com/v1  # GPT-5 (fallback)
LLM_FALLBACK_API_KEY=your_openai_api_key_here
```

### Mode de diagnostic

Le mode de diagnostic est contrôlé par `DIAGNOSIS_MODE` :

| Valeur | Description |
|---|---|
| `rag` (défaut) | Pipeline RAG via LlamaIndex |
| `mcp` | Multi-agent MCP via JSON-RPC 2.0 |
| `agent` | AgentPipeline avec agents spécialistes in-process |

Si le mode sélectionné (`mcp` ou `agent`) n'est pas configuré, le système bascule automatiquement sur le mode `rag` avec un avertissement.

### ⚠ Avertissement de sécurité — Clé API compromise

La clé `LLM_FALLBACK_API_KEY` a été précédemment commitée dans le dépôt Git. Cette clé doit être considérée comme **compromise** et doit être **révoquée immédiatement** dans le tableau de bord OpenAI, puis remplacée par une nouvelle clé dans votre fichier `.env`.

Ne commitez jamais de clés API dans le dépôt. Le fichier `.env` est exclu du suivi Git via `.gitignore`.

---

## Développement local (hors Docker)

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows : .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### Frontend web

```bash
cd apps/web
npm install
npm run dev
```

### Mobile

```bash
cd apps/mobile
npm install
npx expo start
```

---

## Tests

### Backend (pytest + Hypothesis)

```bash
cd backend
pytest
```

### Frontend (Vitest)

```bash
cd apps/web
npx vitest --run
```

---

## API — Endpoints principaux

```
POST   /api/v1/auth/login
POST   /api/v1/auth/logout
GET    /api/v1/auth/me

POST   /api/v1/chat/message          → SSE stream (text/event-stream)
GET    /api/v1/chat/history/{session_id}
GET    /api/v1/chat/sessions
DELETE /api/v1/chat/sessions/{session_id}

POST   /api/v1/diagnose/symptoms
POST   /api/v1/diagnose/prescription
GET    /api/v1/diagnose/session/{session_id}
GET    /api/v1/consultations/me

GET    /api/v1/patients
POST   /api/v1/patients
GET    /api/v1/patients/{id}
PUT    /api/v1/patients/{id}
GET    /api/v1/patients/{id}/consultations
POST   /api/v1/patients/{id}/consultations

POST   /api/v1/documents/upload
GET    /api/v1/documents
DELETE /api/v1/documents/{id}

POST   /api/v1/documents/chat            → SSE stream (text/event-stream) — Chat Documents RAG
GET    /api/v1/documents/chat/sessions
GET    /api/v1/documents/chat/history/{id}
DELETE /api/v1/documents/chat/sessions/{id}
GET    /api/v1/documents/{id}/download

POST   /api/v1/chat/feedback              → Feedback Topic Guard

POST   /api/v1/files/upload
GET    /api/v1/files/{file_id}

GET    /api/v1/alerts/check
```

La documentation interactive complète est disponible sur http://localhost:8000/docs après démarrage.

---

## Rôles utilisateurs

| Rôle | Accès |
|---|---|
| `medecin` | Mode guidé, chat Q&A, chat documents, dossiers patients |
| `infirmière` | Mode guidé, chat Q&A, chat documents, historique des diagnostics |
| `pharmacien` | Chat Q&A, consultation des prescriptions |
| `admin` | Tout + gestion documents, chat documents et utilisateurs |

---

## Licence

Voir [LICENSE](./LICENSE).
