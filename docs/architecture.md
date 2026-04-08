# Architecture — Diagno-Pilot Improvements

Ce document décrit l'architecture technique complète des six axes d'amélioration de Diagno-Pilot : ancrage strict dans les documents, système multi-agents via MCP, pipeline RAG amélioré, sécurité et audit, popup de citation PDF, et intégrité des données.

**Stack** : FastAPI (Python 3.12) + MongoDB (Motor async) + Next.js 15 App Router (TypeScript) + React Native Expo + Tailwind CSS

---

## Table des matières

1. [Pipeline d'ingestion de documents](#1-pipeline-dingestion-de-documents)
2. [Pipeline de requête RAG](#2-pipeline-de-requête-rag)
3. [Flux diagnostique multi-agents](#3-flux-diagnostique-multi-agents)
4. [Flux du popup de citation PDF](#4-flux-du-popup-de-citation-pdf)
5. [Schéma des collections MongoDB](#5-schéma-des-collections-mongodb)
6. [Nouveaux endpoints API](#6-nouveaux-endpoints-api)

---

## 1. Pipeline d'ingestion de documents

Ce diagramme décrit le flux complet depuis le téléversement d'un fichier jusqu'au stockage des chunks dans MongoDB.

```mermaid
flowchart TD
    A([Téléversement fichier\nPDF / DOCX / TXT / CSV]) --> B[Extraction du texte\npypdf · python-docx · csv]
    B --> C{Fichier PDF ?}
    C -- Oui --> D[Extraction BBox et offsets\nbbox · page_char_start · page_char_end]
    C -- Non --> E[Chunking sémantique\nChunker — max 800 car.]
    D --> E
    E --> F[Enrichissement des métadonnées\ndisease_tags · document_type · evidence_level\nsection · region]
    F --> G[Génération des embeddings\nEmbeddingService]
    G --> H[Upload S3\nstockage de l'objet source]
    H --> I[(MongoDB\nmedical_documents)]
    G --> J[(MongoDB\ndocument_chunks)]
    I --> K([Ingestion terminée])
    J --> K
```

### Détails des étapes

| Étape | Composant | Description |
|-------|-----------|-------------|
| Extraction du texte | `DocumentService._extract_text_*` | pypdf pour PDF, python-docx pour DOCX, lecture directe pour TXT/CSV |
| Extraction BBox | `DocumentService._extract_text_pdf()` | Coordonnées `[x0, y0, x1, y1]` et offsets de caractères par chunk, PDF uniquement |
| Chunking sémantique | `Chunker.chunk()` | Détection d'en-têtes (`^(\d+\.|\#{1,3}|\*{1,2})`), étapes numérotées, lignes de tableau ; max 800 caractères |
| Enrichissement métadonnées | `DocumentService._index_chunks()` | `disease_tags` via liste de mots-clés ; `document_type` et `evidence_level` depuis le champ `source` |
| Embeddings | `EmbeddingService` | Vecteurs denses pour la recherche sémantique |
| Upload S3 | `DocumentService` | Stockage de l'objet source pour les URLs présignées |
| Stockage MongoDB | Motor async | `medical_documents` (métadonnées doc) + `document_chunks` (chunks + embeddings) |

---

## 2. Pipeline de requête RAG

Ce diagramme décrit le flux de traitement d'une requête utilisateur, depuis la vérification du cache jusqu'à la réponse finale.

```mermaid
flowchart TD
    A([Requête utilisateur\n+ historique 5 messages\n+ region]) --> B{Cache Redis\nhit ?}
    B -- Hit --> C([Réponse depuis le cache])
    B -- Miss --> D[Embedding de la requête\nEmbeddingService]
    D --> E[Recherche vectorielle\nMongoDB Atlas Vector Search]
    D --> F[Recherche BM25\nBM25_Retriever]
    E --> G[Reciprocal Rank Fusion\nk = 60]
    F --> G
    G --> H[Re-ranking CrossEncoder\ncross-encoder/ms-marco-MiniLM-L-6-v2]
    H --> I{Filtre\nSIMILARITY_THRESHOLD\n≥ 0.75 ?}
    I -- Aucun chunk retenu --> J([Réponse de refus\nNO_CONTEXT_MESSAGE\nsources = vide])
    I -- Chunks retenus --> K[Calcul ConfidenceScore\nmoyenne arithmétique des scores]
    K --> L[Construction du contexte LLM\nGROUNDING_SYSTEM_PROMPT\n+ passages retenus]
    L --> M[Génération LLM\nLLMRouter\nMedicalQwen3-14B → GPT-5 fallback]
    M --> N[Mise en cache Redis\nRAGResponse]
    N --> O([RAGResponse\nanswer · sources · confidence_score\ngrounding_warning si dégradé])
```

### Filtrage de pertinence des sources

Après la récupération et le re-ranking des chunks, le pipeline applique un second seuil de pertinence (`SOURCE_RELEVANCE_THRESHOLD`, défaut `0.3`) pour filtrer les sources incluses dans la réponse. Ce seuil opère au niveau de la réponse et est supérieur ou égal au seuil de récupération (`SIMILARITY_THRESHOLD`), garantissant que seuls les chunks les plus pertinents sont présentés au clinicien.

- Les chunks dont le score est inférieur à `SOURCE_RELEVANCE_THRESHOLD` sont exclus de la liste `sources` dans la `RAGResponse`.
- Lorsqu'aucun chunk ne dépasse le seuil, la liste `sources` est vide (le LLM peut toujours générer une réponse à partir de ses connaissances).
- Le frontend masque le panneau « Sources » lorsque la liste est vide.

### Constantes clés

| Constante | Valeur |
|-----------|--------|
| `SIMILARITY_THRESHOLD` | `0.75` |
| `SOURCE_RELEVANCE_THRESHOLD` | `0.3` |
| `NO_CONTEXT_MESSAGE` | `"Information non disponible dans la base de connaissances."` |
| Modèle CrossEncoder | `cross-encoder/ms-marco-MiniLM-L-6-v2` |
| Historique de session | 20 derniers messages (user + assistant) |
| RRF k | `60` |

---

## 3. Flux diagnostique multi-agents (MCP HTTP+SSE)

Le pipeline de diagnostic multi-agent utilise le protocole MCP (Model Context Protocol) standard. Chaque agent spécialiste est un serveur MCP Docker indépendant exposant trois primitives (Tools, Resources, Prompts) via JSON-RPC 2.0 sur HTTP+SSE. Le MCP_Host orchestre les quatre serveurs en parallèle via `httpx.AsyncClient`.

### Diagramme de composants MCP

```mermaid
graph TB
    subgraph "API Layer"
        R[diagnose.py Router]
        RC[consultations.py Router — /me]
    end

    subgraph "Service Layer"
        DO[DiagnosticOrchestrator]
        MH["MCP_Host (httpx.AsyncClient)"]
        SA[Synthesis_Agent]
        CS[ConsultationService]
    end

    subgraph "MCP Servers — Services Docker"
        ME["epidemiology_server.py (FastAPI :8001)"]
        MS["symptomatology_server.py (FastAPI :8002)"]
        ML["lab_server.py (FastAPI :8003)"]
        MT["treatment_server.py (FastAPI :8004)"]
    end

    subgraph "Data Layer"
        DB[(MongoDB Atlas)]
        LIP[LlamaIndexPipeline — RAG]
    end

    R --> DO
    RC --> CS
    DO --> MH
    DO --> SA
    DO --> CS
    MH -->|"HTTP POST /rpc + SSE"| ME
    MH -->|"HTTP POST /rpc + SSE"| MS
    MH -->|"HTTP POST /rpc + SSE"| ML
    MH -->|"HTTP POST /rpc + SSE"| MT
    ME --> LIP
    MS --> LIP
    ML --> LIP
    MT --> LIP
    LIP --> DB
    CS --> DB
    DO --> DB
```

### Diagramme de séquence du pipeline MCP

```mermaid
sequenceDiagram
    actor Clinicien
    participant API as POST /diagnose/symptoms
    participant DO as DiagnosticOrchestrator
    participant MH as MCP_Host (httpx.AsyncClient)
    participant E as MCP Server Épidémiologie (Docker :8001)
    participant S as MCP Server Symptomatologie (Docker :8002)
    participant L as MCP Server Laboratoire (Docker :8003)
    participant T as MCP Server Traitement (Docker :8004)
    participant SA as Synthesis_Agent
    participant DB as MongoDB

    Clinicien->>API: symptoms, patient_profile, locale, region
    API->>DO: get_differential_diagnosis()
    DO->>MH: run_diagnostic()

    par Requêtes HTTP parallèles (asyncio.gather, timeout 30s/agent)
        MH->>E: GET /health
        MH->>E: POST /rpc {tools/list} → cache
        MH->>E: POST /rpc {tools/call query_epidemiology}
        E-->>MH: SSE → AgentResult (chunks, confidence, partial_differential)
    and
        MH->>S: GET /health
        MH->>S: POST /rpc {tools/list} → cache
        MH->>S: POST /rpc {tools/call query_symptomatology}
        S-->>MH: SSE → AgentResult
    and
        MH->>L: GET /health
        MH->>L: POST /rpc {tools/list} → cache
        MH->>L: POST /rpc {tools/call query_lab}
        L-->>MH: SSE → AgentResult
    and
        MH->>T: GET /health
        MH->>T: POST /rpc {tools/list} → cache
        MH->>T: POST /rpc {tools/call query_treatment}
        T-->>MH: SSE → AgentResult
    end

    MH-->>DO: [AgentResult x4], DiagnosticAuditData
    DO->>SA: synthesize(agent_results)
    SA-->>DO: DiagnosticResult (diagnoses, citations, confidence)
    DO->>DB: insert DiagnosticAudit
    DO->>DB: insert Consultation (mcp_session_id, agent_contributions, evidence_citations)
    DO-->>API: DiagnosticResult
    API-->>Clinicien: DiagnoseResponse (session_id, diagnoses, warnings)
```

### Serveurs MCP spécialistes

Chaque serveur hérite de `BaseMCPServer` (`backend/agents/mcp_servers/base_server.py`) et expose ses primitives via `POST /rpc` (JSON-RPC 2.0) et `GET /health`.

| Serveur | Port Docker | Tool | Resource URI | Prompt | Source Filter |
|---|---|---|---|---|---|
| Épidémiologie | `:8001` | `query_epidemiology` | `epidemiology://documents` | `epidemiology_query` | `document_type = epidemiology` |
| Symptomatologie | `:8002` | `query_symptomatology` | `guidelines://documents` | `symptomatology_query` | `document_type = guideline` |
| Laboratoire | `:8003` | `query_lab` | `laboratory://documents` | `lab_query` | `document_type = laboratory` |
| Traitement | `:8004` | `query_treatment` | `protocols://documents` | `treatment_query` | `document_type in [protocol, guideline]` |

### MCP_Host — Flux de communication

Pour chaque agent, le MCP_Host suit cette séquence (timeout global de 30s par agent) :

1. **Health check** — `GET /health` pour vérifier la disponibilité
2. **Découverte** (si pas en cache) — `tools/list`, `resources/list`, `prompts/list` via `POST /rpc`
3. **Invocation** — `tools/call` via `POST /rpc` avec les arguments structurés
4. **Réception** — Parse de la réponse SSE, extraction de l'`AgentResult`

Le cache des primitives est invalidé quand un serveur est injoignable. Le pool de connexions HTTP (`httpx.AsyncClient`) est maintenu entre les sessions pour réduire la latence.

### Synthesis_Agent — Pipeline de fusion

Le `Synthesis_Agent` fusionne les résultats des agents actifs :

1. Filtrage des agents sans chunks (marqués comme dégradés)
2. Déduplication des diagnostics par probabilité maximale (comparaison insensible à la casse)
3. Tri par probabilité décroissante
4. Padding à minimum 3 diagnostics si nécessaire
5. Construction des citations de preuves (`EvidenceCitation`) par diagnostic
6. Calcul du score de confiance pondéré : `sum(score_i × len(chunks_i)) / sum(len(chunks_i))`
7. Construction des contributions agents (`AgentContribution`)

### Notes sur le transport MCP

- Chaque agent spécialiste est un service Docker FastAPI autonome (`backend/agents/mcp_servers/{name}_server.py`) communiquant via **HTTP POST + SSE** (JSON-RPC 2.0).
- `MCP_Host` utilise `asyncio.gather` avec `httpx.AsyncClient` et un timeout de **30 secondes** par agent.
- En cas de timeout ou d'erreur HTTP, l'agent est marqué comme omis dans le `DiagnosticAudit` et un `degraded_warning` est ajouté.
- Le `patient_profile_hash` est calculé en SHA-256 sur les champs `age`, `weight`, `sex`, `comorbidities` uniquement (sans PII).
- Chaque session MCP génère un `mcp_session_id` (UUID) persisté dans la `Consultation` et le `DiagnosticAudit`.

---

## 4. Flux du popup de citation PDF

Ce diagramme décrit l'interaction frontend depuis l'affichage de la réponse jusqu'au surlignage du passage dans le PDF source.

```mermaid
sequenceDiagram
    actor Clinicien
    participant UI as Interface (Next.js)
    participant Chip as CitationChip [N]
    participant Popup as CitationPopup
    participant API as GET /api/v1/documents/{id}/view
    participant S3 as Amazon S3
    participant PDF as react-pdf

    UI->>UI: Rendu de la réponse\navec CitationChips inline [1] [2] ...
    Clinicien->>Chip: Clic sur [N]
    Chip->>Popup: Ouvre le popup\n(drawer ou modal)
    Popup->>API: GET /api/v1/documents/{id}/view\n(Authorization: Bearer token)
    API-->>Popup: URL présignée S3 (valide 15 min)
    Popup->>S3: Téléchargement du PDF
    S3-->>Popup: Flux PDF

    alt highlight disponible (document PDF)
        Popup->>PDF: Rendu de la page sources[N].page
        PDF-->>Popup: Page rendue
        Popup->>Popup: Superposition rectangle jaune\naux coordonnées highlight.bbox [x0, y0, x1, y1]
    else pas de highlight (non-PDF)
        Popup->>Popup: Affichage de l'excerpt uniquement
    end

    Clinicien->>Popup: Fermeture (Escape ou clic extérieur)
    Popup->>UI: Ferme le popup
```

---

## 5. Schéma des collections MongoDB

### `document_chunks`

Stocke les passages indexés avec leurs embeddings et métadonnées enrichies.

| Champ | Type | Description |
|-------|------|-------------|
| `_id` | ObjectId | Identifiant unique du chunk |
| `document_id` | ObjectId | Référence vers `medical_documents._id` |
| `content` | string | Texte du passage |
| `embedding` | float[] | Vecteur dense pour la recherche sémantique |
| `metadata.source` | string | Organisation source (ex. PNLP, CHU Lomé, MSF) |
| `metadata.title` | string | Titre du document parent |
| `metadata.page` | int \| null | Numéro de page dans le document source |
| `metadata.section` | string \| null | En-tête de section ou légende de tableau |
| `metadata.region` | string | Zone géographique : `TG`, `BJ`, ou `ALL` |
| `metadata.disease_tags` | string[] | Maladies détectées (ex. `["paludisme", "dengue"]`) |
| `metadata.document_type` | string | `protocol` \| `guideline` \| `laboratory` \| `epidemiology` \| `other` |
| `metadata.evidence_level` | string | Niveau de preuve, miroir du `document_type` |
| `metadata.bbox` | float[][] \| null | Coordonnées `[x0, y0, x1, y1]` — PDF uniquement |
| `metadata.page_char_start` | int \| null | Offset de début du chunk dans la page — PDF uniquement |
| `metadata.page_char_end` | int \| null | Offset de fin du chunk dans la page — PDF uniquement |

---

### `medical_documents`

Stocke les métadonnées des documents ingérés.

| Champ | Type | Description |
|-------|------|-------------|
| `_id` | ObjectId | Identifiant unique du document |
| `filename` | string | Nom du fichier original |
| `source` | string | Organisation source (ex. `"PNLP"`, `"CHU Lomé"`) |
| `title` | string | Titre du document |
| `s3_key` | string | Clé S3 de l'objet stocké |
| `chunk_count` | int | Nombre de chunks produits lors de la dernière ingestion |
| `uploaded_at` | ISODate | Horodatage du téléversement |
| `uploaded_by` | ObjectId | Référence vers l'utilisateur ayant téléversé le document |

---

### `chat_sessions`

Stocke les sessions de conversation des cliniciens.

| Champ | Type | Description |
|-------|------|-------------|
| `_id` | ObjectId | Identifiant unique de la session |
| `user_id` | ObjectId | Référence vers l'utilisateur |
| `messages` | object[] | Liste des messages de la session |
| `messages[].role` | string | `user` \| `assistant` |
| `messages[].content` | string | Contenu du message |
| `messages[].sources` | DocumentSource[] \| null | Sources citées (messages assistant uniquement) |
| `messages[].timestamp` | ISODate | Horodatage du message |
| `created_at` | ISODate | Horodatage de création de la session |
| `updated_at` | ISODate | Horodatage de la dernière mise à jour |

---

### `consultations`

Stocke les sessions diagnostiques persistées, liées à un praticien et optionnellement à un patient.

| Champ | Type | Description |
|-------|------|-------------|
| `_id` | ObjectId | Identifiant unique de la consultation |
| `user_id` | ObjectId | Référence vers le praticien |
| `patient_id` | ObjectId \| null | Référence vers le patient (null si `is_one_shot`) |
| `symptoms` | object[] | Liste des symptômes soumis |
| `diagnoses` | object[] | Diagnostics différentiels produits |
| `prescription` | object \| null | Prescription générée |
| `alerts` | string[] | Alertes de sécurité |
| `llm_used` | string \| null | Modèle LLM utilisé |
| `is_one_shot` | boolean | `true` si consultation sans patient associé |
| `created_at` | ISODate | Horodatage de création |
| `mcp_session_id` | string \| null | Identifiant de session MCP (UUID) — index sparse |
| `agent_contributions` | AgentContribution[] | Contributions des agents spécialistes MCP |
| `agent_contributions[].agent_name` | string | Nom de l'agent (ex. `epidemiology`) |
| `agent_contributions[].confidence_score` | float | Score de confiance de l'agent [0.0, 1.0] |
| `agent_contributions[].partial_differential` | object[] | Diagnostics partiels de l'agent |
| `evidence_citations` | EvidenceCitation[] | Citations de preuves documentaires |
| `evidence_citations[].document_id` | string | ID du document source |
| `evidence_citations[].title` | string | Titre du document |
| `evidence_citations[].source` | string | Organisation source |
| `evidence_citations[].excerpt` | string | Extrait du passage |
| `evidence_citations[].page` | int \| null | Numéro de page |

**Index :**
- `mcp_session_id` (sparse)
- `{ user_id: 1, created_at: -1 }` (historique praticien)
- `idempotency_key` (unique, sparse) — pour la déduplication des requêtes diagnostiques

### Idempotence des requêtes diagnostiques

Le modèle `DiagnoseRequest` accepte un champ optionnel `idempotency_key` (généré côté client). Lorsqu'une clé est fournie :

1. Le routeur vérifie si une consultation avec la même `idempotency_key` existe déjà dans MongoDB.
2. Si oui, la réponse existante est retournée avec HTTP 200 — aucune nouvelle consultation n'est créée.
3. Si non, la consultation est créée normalement et la clé est stockée dans le document.

Un index unique sparse sur `idempotency_key` garantit l'unicité tout en permettant les valeurs nulles (requêtes sans clé d'idempotence).

### Persistance unique des consultations (chemin MCP)

Sur le chemin MCP, la consultation est persistée une seule fois par `DiagnosticOrchestrator._create_mcp_consultation`. Le `DiagnosticResult` inclut un flag `consultation_persisted` :

- `True` lorsque le chemin MCP a déjà écrit la consultation → le routeur saute son propre `insert_one`.
- `False` (défaut) pour les chemins RAG et AgentPipeline → le routeur effectue l'écriture comme avant.

Cela évite les doublons de consultations sur le chemin MCP.

---

### `diagnostic_audit`

Enregistre chaque requête diagnostique pour l'audit clinique. Index TTL de **2555 jours** (7 ans) sur le champ `timestamp`.

| Champ | Type | Description |
|-------|------|-------------|
| `_id` | ObjectId | Identifiant unique de l'enregistrement |
| `timestamp` | ISODate | Horodatage de la requête — **index TTL : 2555 jours** |
| `symptoms` | object[] | Liste des symptômes soumis |
| `patient_profile_hash` | string | SHA-256 sur `age`, `weight`, `sex`, `comorbidities` uniquement (sans PII) |
| `locale` | string | Locale résolue par `LocaleMiddleware` (ex. `fr-TG`) |
| `region` | string \| null | Région géographique (`TG`, `BJ`, ou null) |
| `confidence_score` | float | Score de confiance global [0.0, 1.0] |
| `diagnoses` | object[] | Liste des diagnostics différentiels produits |
| `fallback_used` | boolean | Indique si le LLM de secours a été utilisé |
| `degraded_warning` | string \| null | Message d'avertissement si mode dégradé actif |
| `agent_results` | AgentAuditResult[] | Résultats détaillés par agent spécialiste |
| `agent_results[].agent_name` | string | Nom de l'agent (ex. `Epidemiology_Agent`) |
| `agent_results[].sub_question` | string | Sous-question soumise à l'agent |
| `agent_results[].chunk_ids` | string[] | IDs des chunks récupérés par l'agent |
| `agent_results[].confidence_score` | float | Score de confiance de l'agent [0.0, 1.0] |
| `agent_results[].partial_differential` | object[] | Diagnostics partiels produits par l'agent |

> **Accès** : lecture réservée au rôle `admin`. Les rôles `medecin` et `infirmière` n'ont pas accès aux enregistrements d'audit.

---

### `retrieval_feedback`

Stocke les évaluations des sources récupérées soumises par les cliniciens.

| Champ | Type | Description |
|-------|------|-------------|
| `_id` | ObjectId | Identifiant unique du feedback |
| `session_id` | string | Identifiant de la session de chat |
| `user_id` | ObjectId | Référence vers l'utilisateur ayant soumis le feedback |
| `document_id` | string | Identifiant du document évalué |
| `chunk_id` | string | Identifiant du chunk évalué |
| `rating` | int | Évaluation : `1` (pertinent) ou `-1` (non pertinent) |
| `timestamp` | ISODate | Horodatage de la soumission |

---

## 6. Nouveaux endpoints API

### `GET /api/v1/documents/{id}/view`

Retourne une URL présignée S3 pour consulter le document source dans le popup de citation.

| Attribut | Valeur |
|----------|--------|
| Méthode | `GET` |
| Chemin | `/api/v1/documents/{id}/view` |
| Rôles requis | `admin`, `medecin`, `infirmière` |
| Corps de la requête | — |

**Réponse 200 OK**
```json
{
  "url": "https://s3.amazonaws.com/bucket/key?X-Amz-Signature=...&X-Amz-Expires=900",
  "expires_in": 900
}
```

**Réponse 404 Not Found** — document inexistant
```json
{
  "detail": "Document not found"
}
```

> L'URL présignée est valide **15 minutes** (900 secondes).

---

### `POST /api/v1/feedback/retrieval`

Enregistre l'évaluation d'une source récupérée par un clinicien.

| Attribut | Valeur |
|----------|--------|
| Méthode | `POST` |
| Chemin | `/api/v1/feedback/retrieval` |
| Rôles requis | `admin`, `medecin`, `infirmière` |

**Corps de la requête**
```json
{
  "session_id": "string",
  "document_id": "string",
  "chunk_id": "string",
  "rating": 1
}
```

> `rating` accepte uniquement les valeurs `1` (pertinent) ou `-1` (non pertinent).

**Réponse 201 Created**
```json
{
  "status": "created",
  "feedback_id": "ObjectId"
}
```

---

### `POST /api/v1/admin/migrate-chunks`

Déclenche la ré-enrichissement en arrière-plan de tous les chunks `document_chunks` ne possédant pas encore les champs `metadata.disease_tags`, `metadata.document_type`, ou `metadata.evidence_level`.

| Attribut | Valeur |
|----------|--------|
| Méthode | `POST` |
| Chemin | `/api/v1/admin/migrate-chunks` |
| Rôles requis | `admin` |
| Corps de la requête | — |

**Réponse 202 Accepted**
```json
{
  "status": "background_task_started",
  "unmigrated_chunks": 1234
}
```

> Le traitement s'effectue par **lots de 100 chunks**. La tâche s'exécute en arrière-plan ; la réponse est retournée immédiatement avec le nombre de chunks à migrer.

---

### `POST /api/v1/admin/reindex-document/{id}`

Réingère un document depuis son objet S3 en utilisant le nouveau `Chunker` sémantique et l'extraction BBox pypdf. Supprime les chunks existants et insère les nouveaux.

| Attribut | Valeur |
|----------|--------|
| Méthode | `POST` |
| Chemin | `/api/v1/admin/reindex-document/{id}` |
| Rôles requis | `admin` |
| Corps de la requête | — |

**Réponse 200 OK**
```json
{
  "document_id": "ObjectId",
  "new_chunk_count": 42
}
```

**Réponse 404 Not Found** — document inexistant
```json
{
  "detail": "Document not found"
}
```

> Pour les documents **PDF** : extraction BBox et offsets de caractères incluse.
> Pour les documents **non-PDF** (DOCX, TXT, CSV) : chunking sémantique et enrichissement des métadonnées uniquement, sans extraction BBox.

---

*Document généré dans le cadre des améliorations Diagno-Pilot — Exigences 7.1 à 7.7*
