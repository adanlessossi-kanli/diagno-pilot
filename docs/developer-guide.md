# Guide du développeur — Diagno-Pilot

## Table des matières

- [Vue d'ensemble de l'architecture](#vue-densemble-de-larchitecture)
- [Flux du pipeline d'agents](#flux-du-pipeline-dagents)
- [Flux de données PHI](#flux-de-données-phi)
- [Pipeline RAG LlamaIndex](#pipeline-rag-llamaindex)
- [Configuration du développement local](#configuration-du-développement-local)
- [Exécution des tests](#exécution-des-tests)
- [Ajout d'un nouvel agent](#ajout-dun-nouvel-agent)

---

## Vue d'ensemble de l'architecture

Diagno-Pilot est une application de diagnostic médical assisté par IA composée de :

- **Frontend** — Next.js 15 / React 19 avec Tailwind CSS et next-intl (i18n)
- **Backend** — FastAPI (Python 3.12) avec MongoDB Atlas, Redis, S3
- **Model\_Container** — Serveur llama.cpp servant MedicalQwen3-Reasoning-4B (GGUF)
- **Pipeline RAG** — LlamaIndex avec chunking sémantique, recherche hybride, re-ranking
- **Couche HIPAA** — Classification PHI, chiffrement AES-256, audit anti-falsification, contrôles BAA

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

## Ajout d'un nouvel agent

Pour ajouter un agent au pipeline diagnostique :

1. Ajouter l'entrée dans `AgentPipeline.AGENTS` (`backend/services/agent_pipeline.py`) :

```python
AGENTS = {
    # ... agents existants ...
    "nouvel_agent": {
        "source_filter": {"metadata.document_type": "protocol"},
    },
}
```

2. Ajouter le template de sous-question dans `_SUB_QUESTIONS` :

```python
_SUB_QUESTIONS = {
    # ... questions existantes ...
    "nouvel_agent": (
        "Question spécialisée pour les symptômes : {symptoms}? "
        "Région : {region}."
    ),
}
```

3. Mettre à jour la documentation (ce fichier et `docs/api-reference.md`)
4. Ajouter des tests de propriétés pour le nouvel agent
