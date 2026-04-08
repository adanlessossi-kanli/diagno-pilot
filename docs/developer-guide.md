# Guide du développeur — Diagno-Pilot

## Table des matières

- [Vue d'ensemble de l'architecture](#vue-densemble-de-larchitecture)
- [Flux du pipeline d'agents](#flux-du-pipeline-dagents)
- [Flux de données PHI](#flux-de-données-phi)
- [Pipeline RAG LlamaIndex](#pipeline-rag-llamaindex)
- [Configuration du développement local](#configuration-du-développement-local)
- [Exécution des tests](#exécution-des-tests)
- [Ajout d'un nouvel agent](#ajout-dun-nouvel-agent-architecture-mcp)
- [Développement de serveurs MCP](#développement-de-serveurs-mcp)

---

## Vue d'ensemble de l'architecture

Diagno-Pilot est une application de diagnostic médical assisté par IA composée de :

- **Frontend** — Next.js 15 / React 19 avec Tailwind CSS et next-intl (i18n)
- **Backend** — FastAPI (Python 3.12) avec MongoDB Atlas, Redis, S3
- **Model\_Container** — Serveur llama.cpp servant MedicalQwen3-Reasoning-4B (GGUF)
- **Pipeline RAG** — LlamaIndex avec chunking sémantique, recherche hybride, re-ranking
- **Couche HIPAA** — Classification PHI, chiffrement AES-256-GCM (avec fallback Fernet), audit anti-falsification, contrôles BAA

### Diagramme d'architecture

```
┌──────────────┐     ┌──────────────────────────────────────────────┐
│   Frontend   │     │                  Backend                     │
│  Next.js     │────▶│  FastAPI :8000                               │
│  :3000       │     │                                              │
└──────────────┘     │  ┌────────────┐  ┌───────────────────────┐  │
                     │  │ LLM_Router │  │  LlamaIndex_Pipeline  │  │
                     │  │            │  │  ┌─────────────────┐  │  │
                     │  │ Primary:   │  │  │ Index_Manager   │  │  │
                     │  │  Model_    │  │  │ (MongoDB Atlas  │  │  │
                     │  │  Container │  │  │  Vector Search) │  │  │
                     │  │            │  │  └─────────────────┘  │  │
                     │  │ Fallback:  │  │  ┌─────────────────┐  │  │
                     │  │  GPT-5     │  │  │ Semantic_Chunker│  │  │
                     │  │  (via BAA) │  │  └─────────────────┘  │  │
                     │  └────────────┘  │  ┌─────────────────┐  │  │
                     │                  │  │ Source_Loaders   │  │  │
                     │  ┌────────────┐  │  └─────────────────┘  │  │
                     │  │ Agent_     │  └───────────────────────┘  │
                     │  │ Pipeline   │                              │
                     │  └────────────┘  ┌───────────────────────┐  │
                     │                  │  Couche HIPAA          │  │
                     │  ┌────────────┐  │  PHI_Classifier        │  │
                     │  │ Audit_     │  │  Encryption_Service    │  │
                     │  │ Logger     │  │  BAA_Controller        │  │
                     │  └────────────┘  └───────────────────────┘  │
                     └──────────────────────────────────────────────┘
                              │              │              │
                     ┌────────┘     ┌────────┘     ┌───────┘
                     ▼              ▼              ▼
              ┌───────────┐  ┌──────────┐  ┌────────────┐
              │ MongoDB   │  │  Redis   │  │ S3         │
              │ Atlas     │  │  :6379   │  │ (LocalStack│
              │ :27017    │  │          │  │  en dev)   │
              └───────────┘  └──────────┘  └────────────┘
```

### Collections MongoDB

| Collection | Description |
|---|---|
| `medical_documents` | Métadonnées des documents (titre, source, s3\_key, chunk\_count) |
| `document_chunks` | Nœuds LlamaIndex avec embeddings et métadonnées |
| `hipaa_audit_logs` | Journal d'audit HIPAA (append-only, chaîne de hachage) |
| `audit_logs` | Journal d'audit général (compatibilité ascendante) |
| `users` | Comptes utilisateurs |
| `diagnostic_audit` | Historique des sessions diagnostiques |

## Flux du pipeline d'agents

Le pipeline d'agents exécute 5 agents spécialisés en parallèle pour produire un diagnostic différentiel.

```
POST /api/v1/diagnose
        │
        ▼
┌─────────────────────────────────────────────────────┐
│                  AgentPipeline.run()                  │
│                                                       │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────┐ │
│  │Symptomatologie│  │Épidémiologie │  │Laboratoire │ │
│  │source_filter: │  │source_filter: │  │source_filter│
│  │ guideline     │  │ protocol,    │  │ CHU|MSF    │ │
│  │               │  │ guideline    │  │            │ │
│  └──────┬───────┘  └──────┬───────┘  └─────┬──────┘ │
│         │                  │                 │        │
│  ┌──────┴───────┐  ┌──────┴───────┐                  │
│  │  Synthèse    │  │ Traitement   │                  │
│  │source_filter: │  │source_filter: │                  │
│  │  (aucun)     │  │  protocol    │                  │
│  └──────┬───────┘  └──────┬───────┘                  │
│         │                  │                          │
│         └────────┬─────────┘                          │
│                  ▼                                    │
│         Agrégation des résultats                      │
│         - Confidence = moyenne arithmétique           │
│         - Diagnostics dédupliqués (prob. max)         │
│         - Avertissement si agents en erreur           │
└───────────────────────────────────────────────────────┘
        │
        ▼
  DiagnosticResponse
```

Chaque agent :
1. Formule une sous-question spécialisée à partir des symptômes
2. Interroge le pipeline LlamaIndex avec son `source_filter`
3. Reçoit une réponse RAG avec chunks et score de confiance
4. Extrait un différentiel partiel depuis la réponse LLM

## Flux de données PHI

```
┌─────────────────────────────────────────────────────────────┐
│                    ZONE PHI AUTORISÉE                        │
│                                                              │
│  PatientProfile ──▶ AgentPipeline ──▶ LlamaIndex_Pipeline   │
│  (PHI complet)      (contexte PHI)     (contexte PHI)       │
│                                              │               │
│                                              ▼               │
│                                        LLM_Router            │
│                                              │               │
│                              ┌───────────────┼────────────┐ │
│                              │               │            │ │
│                              ▼               ▼            │ │
│                     Model_Container    Circuit Breaker     │ │
│                     (PHI autorisé)     ouvert ?            │ │
│                              │               │            │ │
│                              │          OUI  │            │ │
└──────────────────────────────┼───────────────┼────────────┘ │
                               │               ▼              │
                               │    ┌──────────────────────┐  │
                               │    │  BAA_Controller      │  │
                               │    │  strip_phi()         │  │
                               │    │  verify_no_phi()     │  │
                               │    └──────────┬───────────┘  │
                               │               │              │
┌──────────────────────────────┼───────────────┼──────────────┘
│                    ZONE PHI INTERDIT          │
│                                               ▼
│                                          GPT-5 (externe)
│                                          (zéro PHI,
│                                           placeholders seuls)
└──────────────────────────────────────────────────────────────
```

### Règles de la frontière PHI

- **Model\_Container (local)** : PHI complet autorisé — les données ne quittent pas l'infrastructure
- **GPT-5 (externe)** : Zéro PHI — le `BAAController` remplace toutes les valeurs PHI par des placeholders
- **Logs d'audit** : Types de champs uniquement, jamais de valeurs PHI
- **Chiffrement au repos** : Tous les champs PHI sont chiffrés AES-256 avant stockage MongoDB

## Pipeline RAG LlamaIndex

### Flux d'ingestion de documents

```
Upload fichier
      │
      ▼
SourceLoaderService.load()
  - Dispatch par format (PDF, DOCX, CSV, TXT, HTML)
  - Extraction de métadonnées (page, section, heading)
  - Tags de maladies (DISEASE_KEYWORDS)
  - Inférence du type de document (protocol/guideline/other)
      │
      ▼
SemanticChunkerService.chunk()
  - Découpage sémantique par similarité d'embedding
  - Limite de tokens configurable (défaut: 512)
  - Préservation des tableaux et étapes numérotées
  - Métadonnées source attachées à chaque nœud
      │
      ▼
EncryptionService.encrypt_phi_fields()
  - Chiffrement AES-256 des champs PHI annotés
      │
      ▼
IndexManager.insert_nodes()
  - Insertion incrémentale dans MongoDB Atlas
  - Index vectoriel pour la recherche sémantique
```

### Flux de requête RAG

```
Question utilisateur
      │
      ▼
Cache Redis (TTL 5 min) ──▶ Hit ? → Retourner réponse cachée
      │
      ▼ Miss
EmbeddingModel.encode()
      │
      ▼
IndexManager.retrieve()
  ├── Recherche vectorielle (MongoDB Atlas $vectorSearch)
  ├── Recherche BM25 (MongoDB $text)
  ├── Fusion RRF (Reciprocal Rank Fusion)
  ├── Re-ranking cross-encoder (ms-marco-MiniLM-L-6-v2)
  └── Filtrage par seuil de similarité (0.75)
      │
      ▼
LLMRouter.generate()
  - Prompt de grounding (réponses basées uniquement sur les documents)
  - Primary: Model_Container → Fallback: GPT-5 (avec BAA stripping)
      │
      ▼
RAGResponse (answer, sources, confidence_score, llm_used)
      │
      ▼
Cache Redis (TTL 5 min)
```

## Configuration du développement local

### Prérequis

- Python 3.12+
- Node.js 20+
- Docker et Docker Compose v2
- (Optionnel) NVIDIA Container Toolkit pour le GPU

### Installation

```bash
# 1. Cloner le dépôt
git clone <repo-url>
cd diagno-pilot

# 2. Copier la configuration
cp .env.example .env

# 3. Placer le modèle GGUF
# Copier MedicalQwen3-Reasoning-4B.Q8_0.gguf dans model/

# 4. Lancer les services (CPU)
docker compose --profile cpu up -d

# 5. Installer les dépendances Python (pour les tests)
pip install -r backend/requirements.txt

# 6. Installer les dépendances frontend
cd apps/web && npm install
```

### Développement backend

Le backend utilise le hot reload via le montage de volume `./backend:/workspace/backend`.

```bash
# Logs du backend
docker compose logs backend -f

# Exécuter une commande dans le conteneur backend
docker compose exec backend python -c "from backend.core.config import settings; print(settings.ENV)"
```

### Développement frontend

```bash
# Le frontend est accessible sur http://localhost:3000
# Hot reload via les montages de volumes src/ et public/
docker compose logs frontend -f
```

## Exécution des tests

```bash
# Tests backend (tous)
python -m pytest backend/tests/ -v

# Tests de propriétés uniquement
python -m pytest backend/tests/ -v -k "property"

# Tests frontend
cd apps/web && npm test
```

### Tests de propriétés (PBT)

Les tests de propriétés valident les invariants du système :

| Propriété | Fichier | Valide |
|---|---|---|
| Round-trip chunking | `test_semantic_chunker_properties.py` | Req 2.7 |
| Limite de tokens | `test_semantic_chunker_properties.py` | Req 2.3 |
| Métadonnées chunks | `test_semantic_chunker_properties.py` | Req 2.2, 2.6 |
| Extraction métadonnées source | `test_source_loaders_properties.py` | Req 3.7, 3.8 |
| Erreur format non supporté | `test_source_loaders_properties.py` | Req 3.6 |
| Filtre de similarité | `test_index_manager_properties.py` | Req 4.4 |
| Filtre régional | `test_index_manager_properties.py` | Req 4.6 |
| Classification PHI | `test_phi_classifier_properties.py` | Req 6.1, 6.2, 6.5 |
| Round-trip chiffrement | `test_encryption_properties.py` | Req 7.1, 7.5 |
| Sécurité chiffrement | `test_encryption_properties.py` | Req 7.6 |
| Stripping BAA | `test_baa_controller_properties.py` | Req 5.4, 9.1, 9.2 |
| Complétude audit | `test_audit_properties.py` | Req 8.1 |
| Intégrité chaîne de hachage | `test_audit_properties.py` | Req 8.6 |
| Exclusion PHI audit | `test_audit_properties.py` | Req 8.2, 9.3 |
| Frontière PHI agents | `test_agent_pipeline_properties.py` | Req 10.2, 10.3 |
| Agrégation agents | `test_agent_pipeline_properties.py` | Req 10.6 |
| Round-trip sérialisation MCP | `test_mcp_serialization_properties.py` | Req 3.4 |
| Validité structurelle JSON-RPC 2.0 | `test_jsonrpc_validation_properties.py` | Req 2.4, 3.1 |
| Idempotence cache découverte | `test_mcp_host_properties.py` | Req 2.2, 2.3, 2.4 |
| Agents en erreur marqués omis | `test_mcp_host_properties.py` | Req 2.9, 3.6 |
| Invariant structurel AgentResult | `test_agent_result_properties.py` | Req 4.5, 4.6 |
| Déduplication probabilité max | `test_synthesis_properties.py` | Req 5.2 |
| Tri diagnostics décroissant | `test_synthesis_properties.py` | Req 5.3 |
| Minimum 3 diagnostics | `test_synthesis_properties.py` | Req 5.4 |
| Citations de preuves | `test_synthesis_properties.py` | Req 5.7 |
| Score confiance pondéré | `test_synthesis_properties.py` | Req 5.8 |
| Disclaimer fallback | `test_synthesis_properties.py` | Req 4.7, 6.2, 8.3 |
| warnings_present dérivé | `test_endpoint_properties.py` | Req 8.4 |
| Passthrough Locale | `test_mcp_host_properties.py` | Req 9.1, 9.4, 9.5 |
| Intégrité Consultations MCP | `test_consultation_properties.py` | Req 11.2, 11.5–11.8 |
| Historique trié par date | `test_consultation_properties.py` | Req 11.10 |
| Idempotence migration | `test_migration_properties.py` | Req 12.5, 12.6 |
| Exécution parallèle agents | `test_mcp_host_properties.py` | Req 15.3 |

## En-têtes de sécurité HTTP

Le middleware `SecurityHeadersMiddleware` (`backend/core/security_headers.py`) injecte les en-têtes de sécurité suivants sur toutes les réponses API backend :

| En-tête | Valeur | Description |
|---|---|---|
| `Content-Security-Policy` | Configurable via `CSP_POLICY` (défaut : `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'`) | Contrôle les sources de contenu autorisées |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | Contrôle les informations de referrer envoyées |
| `Permissions-Policy` | `camera=(), microphone=(), geolocation=(), payment=()` | Désactive les fonctionnalités non utilisées |

> **Backend vs Frontend :** La CSP backend s'applique uniquement aux réponses API directes (FastAPI). Le frontend Next.js injecte sa propre CSP via `next.config.ts` avec des directives adaptées (incluant `https://images.unsplash.com` pour les images et `'unsafe-eval'` en dev pour le HMR). Les deux politiques ne sont pas en conflit car elles s'appliquent à des réponses HTTP distinctes.

Ces en-têtes sont appliqués dans tous les environnements (développement, staging, production).

## Ajout d'un nouvel agent (Architecture MCP)

Depuis la migration vers l'architecture MCP, chaque agent spécialiste est un serveur MCP Docker indépendant. Pour ajouter un nouvel agent :

### 1. Créer le serveur MCP

Créer un fichier `backend/agents/mcp_servers/{name}_server.py` en héritant de `BaseMCPServer` :

```python
"""
Serveur MCP {Name} — Diagno-Pilot

Primitives exposées :
- Tool : `query_{name}` — Description du tool
- Resource : `{name}://documents` — Description de la resource
- Prompt : `{name}_query` — Template de requête
"""

from backend.agents.mcp_servers.base_server import BaseMCPServer

class MyNewMCPServer(BaseMCPServer):
    def __init__(self, port: int = 8005) -> None:
        super().__init__(server_name="my_new_agent", port=port)

        # Infrastructure isolée (MongoDB, EmbeddingModel, IndexManager, Pipeline)
        # ...

        # Enregistrer les primitives MCP
        self.register_tool(
            name="query_my_domain",
            description="Description du tool",
            input_schema=TOOL_INPUT_SCHEMA,  # Schéma commun
            handler=self._handle_query,
        )

        self.register_resource(
            uri="my_domain://documents",
            name="My Domain Documents",
            description="Description de la collection",
            mime_type="application/json",
        )

        self.register_prompt(
            name="my_domain_query",
            description="Template de requête pour le domaine",
            arguments=[
                {"name": "symptoms", "description": "Liste des symptômes", "required": True},
                {"name": "locale", "description": "Locale BCP-47", "required": True},
                {"name": "region", "description": "Code région", "required": False},
            ],
        )

    async def read_resource(self, uri: str) -> dict:
        if uri == "my_domain://documents":
            return {"text": "Description des données disponibles."}
        return {"text": ""}

    async def _handle_query(self, arguments: dict) -> dict:
        # Implémenter la logique de requête RAG
        # Retourner un dict au format AgentResult
        return {
            "agent_name": "my_new_agent",
            "sub_question": "...",
            "chunks": [],
            "confidence_score": 0.0,
            "partial_differential": [],
            "fallback_used": False,
        }

if __name__ == "__main__":
    server = MyNewMCPServer()
    server.run()
```

### 2. Configurer l'URL dans `backend/core/config.py`

```python
AGENT_MY_NEW_URL: str = "http://agent-my-new:8005"
```

### 3. Ajouter l'URL dans `backend/services/mcp_host.py`

```python
_AGENT_URLS["my_new_agent"] = settings.AGENT_MY_NEW_URL
```

### 4. Ajouter le service Docker dans `docker-compose.yml`

```yaml
agent-my-new:
  build:
    context: ./backend
    dockerfile: agents/mcp_servers/Dockerfile
  command: python -m backend.agents.mcp_servers.my_new_server
  ports:
    - "8005:8005"
  environment:
    - MONGODB_URI=mongodb://mongo:27017/diagno_pilot
    - SERVER_PORT=8005
  depends_on:
    mongo:
      condition: service_healthy
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8005/health"]
    interval: 10s
    timeout: 5s
    retries: 5
    start_period: 15s
```

### 5. Tester localement

```bash
# Lancer le serveur en local
python -m backend.agents.mcp_servers.my_new_server

# Tester le health check
curl http://localhost:8005/health

# Lister les tools
curl -X POST http://localhost:8005/rpc \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "method": "tools/list", "params": {}, "id": 1}'

# Invoquer le tool
curl -X POST http://localhost:8005/rpc \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "method": "tools/call", "params": {"name": "query_my_domain", "arguments": {"symptoms": [{"name": "fièvre"}], "locale": "fr-TG"}}, "id": 2}'
```

### 6. Ajouter des tests

- Tests unitaires pour le handler du tool
- Tests property-based pour les invariants (round-trip sérialisation, structure AgentResult)

---

## Développement de serveurs MCP

### Architecture des serveurs MCP

Tous les serveurs MCP héritent de `BaseMCPServer` (`backend/agents/mcp_servers/base_server.py`) qui fournit :

- Dispatch JSON-RPC 2.0 automatique pour les 6 méthodes MCP standard
- Validation stricte de l'enveloppe JSON-RPC 2.0 (voir ci-dessous)
- Réponses SSE (`text/event-stream`)
- Endpoint `GET /health` pour les health checks Docker
- Méthodes `register_tool()`, `register_resource()`, `register_prompt()`
- Gestion des erreurs JSON-RPC 2.0 (codes -32700 à -32603)

### Validation JSON-RPC renforcée

`BaseMCPServer._handle_request` valide rigoureusement l'enveloppe JSON-RPC 2.0 avant le dispatch :

| Validation | Code d'erreur | Description |
|---|---|---|
| `jsonrpc` ≠ `"2.0"` | -32600 | Invalid Request |
| `method` absent ou non-string | -32600 | Invalid Request |
| `id` de type invalide (ni string, ni int, ni null) | -32600 | Invalid Request |
| `params` présent mais ni dict ni list | -32602 | Invalid Params |
| Méthode inconnue | -32601 | Method not found |

Les requêtes valides (`jsonrpc="2.0"`, `method` = string non vide, `params` = dict/list/absent, `id` = string/int/null/absent) sont dispatchées au handler approprié.

### Serveurs existants

| Fichier | Classe | Port | Domaine |
|---|---|---|---|
| `epidemiology_server.py` | `EpidemiologyMCPServer` | 8001 | Données épidémiologiques régionales |
| `symptomatology_server.py` | `SymptomatologyMCPServer` | 8002 | Guidelines cliniques |
| `lab_server.py` | `LabMCPServer` | 8003 | Examens biologiques |
| `treatment_server.py` | `TreatmentMCPServer` | 8004 | Protocoles thérapeutiques |

### Isolation des processus

Chaque serveur MCP Docker instancie sa propre connexion MongoDB, `EmbeddingModel`, `IndexManager` et `LlamaIndexPipeline`. Aucune ressource du processus backend n'est partagée. La communication se fait via le réseau Docker interne.

### Tester un serveur MCP avec curl

```bash
# Health check
curl http://localhost:8001/health

# Découverte des primitives
curl -X POST http://localhost:8001/rpc \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "method": "tools/list", "params": {}, "id": 1}'

curl -X POST http://localhost:8001/rpc \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "method": "resources/list", "params": {}, "id": 2}'

curl -X POST http://localhost:8001/rpc \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "method": "prompts/list", "params": {}, "id": 3}'

# Invocation d'un tool
curl -X POST http://localhost:8001/rpc \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "method": "tools/call", "params": {"name": "query_epidemiology", "arguments": {"symptoms": [{"name": "fièvre"}, {"name": "céphalées"}], "locale": "fr-TG", "region": "TG"}}, "id": 4}'
```
