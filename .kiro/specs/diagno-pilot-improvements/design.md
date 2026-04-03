# Design Document — Diagno-Pilot Improvements

## Overview

Ce document décrit l'architecture technique pour les six axes d'amélioration de Diagno-Pilot :

1. **Strict Document Grounding** — ancrage strict dans les documents ingérés, refus de répondre hors contexte
2. **Multi-Agent Diagnostic via MCP** — orchestration de quatre agents spécialistes via Model Context Protocol
3. **RAG Pipeline amélioré** — chunking sémantique, métadonnées enrichies, récupération hybride (vecteur + BM25)
4. **Safety & Audit** — score de confiance, audit complet de chaque diagnostic, feedback de récupération
5. **PDF Citation Popup** — affichage de la page PDF source avec surlignage du passage cité
6. **Data Integrity & Migration** — gestion des chunks non migrés, réindexation à la demande, intégrité référentielle

La stack reste inchangée : **FastAPI** (Python 3.12) + **MongoDB** (Motor async) + **Next.js 15 App Router** (TypeScript) + **React Native Expo** + **Tailwind CSS**.

---

## Architecture

```mermaid
graph TD
    subgraph Clients
        WEB[Next.js 15 Web]
        MOB[React Native Expo]
    end

    subgraph API["FastAPI /api/v1"]
        MW_LOCALE[LocaleMiddleware]
        R_CHAT[/chat]
        R_DIAG[/diagnose]
        R_DOCS[/documents]
        R_FEED[/feedback/retrieval]
        R_ADMIN[/admin/migrate-chunks\n/admin/reindex-document]
    end

    subgraph Orchestration
        ORCH[DiagnosticOrchestrator]
        MCP[MCP_Host]
        EPI[Epidemiology_Agent]
        SYMP[Symptomatology_Agent]
        LAB[Lab_Agent]
        TREAT[Treatment_Agent]
        SYNTH[Synthesis_Agent]
    end

    subgraph RAG
        RAG_SVC[RAGService]
        EMBED[EmbeddingService]
        BM25[BM25_Retriever]
        CE[CrossEncoder]
        LLM[LLMRouter]
    end

    subgraph Storage
        MONGO[(MongoDB)]
        S3[(S3)]
        COL_CHUNKS[document_chunks]
        COL_DOCS[medical_documents]
        COL_AUDIT[diagnostic_audit]
        COL_FEED[retrieval_feedback]
        COL_CHAT[chat_sessions]
    end

    WEB --> MW_LOCALE --> R_CHAT & R_DIAG & R_DOCS & R_FEED & R_ADMIN
    MOB --> MW_LOCALE

    R_DIAG --> ORCH --> MCP
    MCP --> EPI & SYMP & LAB & TREAT
    EPI & SYMP & LAB & TREAT --> RAG_SVC
    MCP --> SYNTH --> ORCH
    ORCH --> COL_AUDIT

    R_CHAT --> RAG_SVC
    RAG_SVC --> EMBED --> COL_CHUNKS
    RAG_SVC --> BM25 --> COL_CHUNKS
    RAG_SVC --> CE
    RAG_SVC --> LLM

    R_DOCS --> COL_DOCS & COL_CHUNKS & S3
    R_FEED --> COL_FEED
```

---

## Components and Interfaces

### REQ 1 — Strict Document Grounding

**Décision** : Ajouter un `GROUNDING_SYSTEM_PROMPT` constant dans `RAGService`. Ce prompt est injecté comme premier message `system` dans chaque appel LLM. Quand le filtre `SIMILARITY_THRESHOLD` (0.75) élimine tous les chunks, `RAGService.query()` retourne immédiatement sans appeler le LLM.

```python
# backend/services/rag_service.py
SIMILARITY_THRESHOLD = 0.75
NO_CONTEXT_MESSAGE = "Information non disponible dans la base de connaissances."

GROUNDING_SYSTEM_PROMPT = (
    "Tu es un assistant médical. Réponds UNIQUEMENT en te basant sur les passages "
    "de documents fournis ci-dessous. Si aucun passage pertinent n'est disponible, "
    "réponds exactement : \"" + NO_CONTEXT_MESSAGE + "\". "
    "N'utilise jamais tes connaissances paramétriques."
)
```

Le `DocumentSource` est modifié pour distinguer `title` (titre du document) et `source` (organisation source), peuplés depuis `metadata.title` et `metadata.source` respectivement.

`RAGResponse` est étendu avec un champ `grounding_warning: str | None` — peuplé quand `degraded_warning` est actif.

### REQ 2 — Multi-Agent Diagnostic via MCP

**Décision** : Nouveau service `MCP_Host` dans `backend/services/mcp_host.py`. Chaque agent spécialiste est un processus Python séparé exposant des outils MCP via stdio. `MCP_Host` lance les quatre agents en parallèle via `asyncio.gather` avec un timeout de 30 secondes par agent.

```python
# backend/services/mcp_host.py
AGENT_TIMEOUT = 30  # secondes

SOURCE_FILTERS = {
    "epidemiology": {"metadata.document_type": "epidemiology"},
    "symptomatology": {"metadata.document_type": "guideline"},
    "lab": {"metadata.document_type": "laboratory"},
    "treatment": {"metadata.document_type": {"$in": ["protocol", "guideline"]}},
}

class MCP_Host:
    async def run_diagnostic(
        self,
        symptoms: list[Symptom],
        patient_profile: PatientProfile | None,
        locale: str,
        region: str | None,
    ) -> tuple[list[AgentResult], DiagnosticAuditData]: ...
```

`DiagnosticOrchestrator` délègue à `MCP_Host` et écrit le `DiagnosticAudit` après chaque appel. L'interface publique `get_differential_diagnosis` est préservée.

Chaque agent spécialiste est un script Python autonome (`backend/agents/{name}_agent.py`) qui :
1. Lit une requête MCP depuis stdin
2. Appelle `RAGService.query()` avec la sous-question et le `source_filter` approprié
3. Retourne le résultat sur stdout

`Synthesis_Agent` fusionne les résultats des quatre agents et garantit un minimum de 3 diagnostics différentiels (en ajoutant des entrées `confidence: low` si nécessaire).

### REQ 3 — RAG Pipeline amélioré

**Chunker sémantique** : Nouveau module `backend/services/chunker.py` remplaçant la fonction `chunk_text` actuelle.

```python
# backend/services/chunker.py
SECTION_HEADER_RE = re.compile(r'^(\d+\.|\#{1,3}|\*{1,2})[^\n]+', re.MULTILINE)
NUMBERED_STEP_RE = re.compile(r'^(\d+[\.\)])\s', re.MULTILINE)
MAX_CHUNK_CHARS = 800

class Chunker:
    def chunk(self, text: str) -> list[ChunkResult]:
        """Retourne une liste de ChunkResult avec content et section."""
        ...

@dataclass
class ChunkResult:
    content: str
    section: str | None  # en-tête de section ou légende de tableau
```

**Métadonnées enrichies** : `DocumentService._index_chunks()` est étendu pour calculer `disease_tags`, `document_type`, et `evidence_level` à partir du champ `source` du document.

```python
DISEASE_KEYWORDS = {
    "malaria", "paludisme", "typhoid", "typhoïde", "dengue",
    "cholera", "choléra", "tuberculosis", "tuberculose", "hiv", "vih",
    "schistosomiasis", "bilharziose", "trypanosomiasis", "trypanosomiase",
    "yellow fever", "fièvre jaune", "meningitis", "méningite",
}

def infer_document_type(source: str) -> str:
    s = source.upper()
    if "PNLP" in s or "MSF" in s: return "protocol"
    if "CHU" in s or "OMS" in s or "WHO" in s: return "guideline"
    return "other"
```

**Récupération hybride** : `RAGService.query()` est étendu pour combiner les résultats du vector search et du `BM25_Retriever` via Reciprocal Rank Fusion (RRF) avant de passer au `CrossEncoder`.

```python
def reciprocal_rank_fusion(
    ranked_lists: list[list[dict]], k: int = 60
) -> list[dict]:
    """Fusionne N listes classées via RRF. score = sum(1 / (k + rank))."""
    ...
```

`CrossEncoder` utilise le modèle `cross-encoder/ms-marco-MiniLM-L-6-v2` chargé au démarrage comme singleton dans `DocumentService`.

`ChatService.send_message()` est modifié pour inclure les 5 derniers messages de la session comme contexte additionnel dans `RAGService.query()`.

### REQ 4 — Safety & Audit

**ConfidenceScore** : `RAGService.query()` calcule la moyenne arithmétique des scores de similarité des chunks retenus et l'inclut dans `RAGResponse.confidence_score`.

**DiagnosticAudit** : Nouveau modèle `DiagnosticAudit` dans `backend/models/diagnostic_audit.py`. `DiagnosticOrchestrator` écrit un document dans la collection `diagnostic_audit` après chaque appel.

```python
class AgentAuditResult(BaseModel):
    agent_name: str
    sub_question: str
    chunk_ids: list[str]
    confidence_score: float
    partial_differential: list[dict]

class DiagnosticAudit(BaseModel):
    timestamp: datetime
    symptoms: list[dict]
    patient_profile_hash: str  # SHA-256 sur age, weight, sex, comorbidities
    locale: str
    region: str | None
    confidence_score: float
    diagnoses: list[dict]
    fallback_used: bool
    degraded_warning: str | None
    agent_results: list[AgentAuditResult]
```

Le hash du profil patient est calculé sur les champs `age`, `weight`, `sex`, `comorbidities` uniquement (pas de PII).

**Feedback de récupération** : Nouveau endpoint `POST /api/v1/feedback/retrieval` dans `backend/routers/feedback.py`, accessible aux rôles `admin`, `medecin`, `infirmière`.

### REQ 5 — PDF Citation Popup

**Backend** : `DocumentService._extract_text_pdf()` est étendu pour extraire les BBox et offsets de caractères via `pypdf`. Ces données sont stockées dans `metadata.bbox`, `metadata.page_char_start`, `metadata.page_char_end` sur chaque `DocumentChunk`.

`DocumentSource` est étendu avec un champ optionnel `highlight: HighlightInfo | None`.

```python
class HighlightInfo(BaseModel):
    bbox: list[float]  # [x0, y0, x1, y1]
    page: int

class DocumentSource(BaseModel):
    document_id: str
    title: str
    source: str
    section: str | None = None
    excerpt: str | None = None
    page: int | None = None
    highlight: HighlightInfo | None = None  # nouveau
    confidence_score: float | None = None   # nouveau
```

Nouveau endpoint `GET /api/v1/documents/{id}/view` retournant une URL S3 présignée valide 15 minutes, accessible aux rôles `admin`, `medecin`, `infirmière`.

**Frontend** : Composant `CitationChip` inline (`[N]`) dans le texte de réponse. Composant `CitationPopup` (drawer/modal) qui :
- Récupère l'URL présignée
- Rend la page PDF via `react-pdf`
- Superpose un rectangle jaune aux coordonnées `highlight.bbox`
- Affiche uniquement l'`excerpt` si `highlight` est absent
- Se ferme via Escape ou clic extérieur

### REQ 6 — Data Integrity & Migration

**Détection au démarrage** : `DocumentService` vérifie au démarrage les chunks sans `metadata.disease_tags`, `metadata.document_type`, ou `metadata.evidence_level` et log un warning avec le compte.

**Endpoints admin** :
- `POST /api/v1/admin/migrate-chunks` — ré-enrichit les chunks non migrés par lots de 100
- `POST /api/v1/admin/reindex-document/{id}` — réingère un document depuis S3 avec le nouveau Chunker et l'extraction BBox

**Intégrité référentielle** : La suppression d'un document (`DELETE /api/v1/documents/{id}`) ne supprime pas les enregistrements `diagnostic_audit` référençant ses chunks. Les `chunk_id` dans ces enregistrements deviennent des références tombstone.

---

## Data Models

### MongoDB — Collections modifiées/nouvelles

#### `document_chunks` (modifiée)
```json
{
  "_id": "ObjectId",
  "document_id": "ObjectId (ref: medical_documents)",
  "content": "string",
  "embedding": "[float]",
  "metadata": {
    "source": "string",
    "title": "string",
    "page": "int | null",
    "section": "string | null",
    "region": "string (TG | BJ | ALL)",
    "disease_tags": ["string"],
    "document_type": "string (protocol | guideline | laboratory | epidemiology | other)",
    "evidence_level": "string",
    "bbox": "[[float]] | null",
    "page_char_start": "int | null",
    "page_char_end": "int | null"
  }
}
```

#### `diagnostic_audit` (nouvelle)
```json
{
  "_id": "ObjectId",
  "timestamp": "ISODate (TTL index: 2555 jours)",
  "symptoms": "[object]",
  "patient_profile_hash": "string (SHA-256)",
  "locale": "string",
  "region": "string | null",
  "confidence_score": "float",
  "diagnoses": "[object]",
  "fallback_used": "boolean",
  "degraded_warning": "string | null",
  "agent_results": "[AgentAuditResult]"
}
```

#### `retrieval_feedback` (nouvelle)
```json
{
  "_id": "ObjectId",
  "session_id": "string",
  "user_id": "ObjectId",
  "document_id": "string",
  "chunk_id": "string",
  "rating": "int (1 | -1)",
  "timestamp": "ISODate"
}
```

### Pydantic — Modèles modifiés

#### `RAGResponse` (étendu)
```python
class RAGResponse(BaseModel):
    answer: str
    sources: list[DocumentSource]
    llm_used: str
    confidence_score: float | None = None  # nouveau
    fallback_used: bool = False
    degraded_warning: str | None = None
    grounding_warning: str | None = None   # nouveau
```

#### `DocumentSource` (étendu)
```python
class DocumentSource(BaseModel):
    document_id: str
    title: str        # depuis metadata.title (indépendant de source)
    source: str       # depuis metadata.source (organisation)
    section: str | None = None
    excerpt: str | None = None
    page: int | None = None
    highlight: HighlightInfo | None = None  # nouveau
    confidence_score: float | None = None   # nouveau
```

### TypeScript — Interfaces

```typescript
interface HighlightInfo {
  bbox: [number, number, number, number];
  page: number;
}

interface DocumentSource {
  document_id: string;
  title: string;
  source: string;
  section?: string;
  excerpt?: string;
  page?: number;
  highlight?: HighlightInfo;
  confidence_score?: number;
}

interface DiagnosticResult {
  diagnoses: DifferentialDiagnosis[];
  fallback_used: boolean;
  degraded_warning?: string;
  confidence_score?: number;
  locale: string;
}
```

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1 : Grounding prompt présent dans tout contexte LLM

*Pour toute* requête soumise à `RAGService.query()`, le premier message `system` passé à `LLMRouter.generate()` doit contenir le `GROUNDING_SYSTEM_PROMPT` constant.

**Validates: Requirements 1.1**

---

### Property 2 : Refus sans appel LLM quand aucun chunk ne passe le seuil

*Pour tout* ensemble de chunks récupérés avec des scores variés, `RAGService` ne doit passer au LLM que les chunks dont le score de similarité cosinus est ≥ 0.75 ; si aucun chunk ne passe ce filtre, `RAGService.query()` doit retourner `answer == NO_CONTEXT_MESSAGE`, `sources == []`, et ne doit pas appeler `LLMRouter.generate()`.

**Validates: Requirements 1.2, 1.3**

---

### Property 3 : Indépendance des champs title et source dans DocumentSource

*Pour tout* chunk dont `metadata.title` et `metadata.source` sont des valeurs distinctes, le `DocumentSource` produit doit avoir `title` peuplé depuis `metadata.title` et `source` peuplé depuis `metadata.source` indépendamment.

**Validates: Requirements 1.4**

---

### Property 4 : grounding_warning présent quand degraded_warning est actif

*Pour toute* `RAGResponse` où `degraded_warning` est non-null, le champ `grounding_warning` doit également être non-null et contenir le message fixe indiquant que les résultats sont basés sur la récupération par mots-clés uniquement.

**Validates: Requirements 1.5**

---

### Property 5 : source_filter correct pour chaque agent spécialiste

*Pour toute* requête diagnostique, chaque agent spécialiste dispatché par `MCP_Host` doit recevoir un `source_filter` correspondant à son type de document : `epidemiology` pour `Epidemiology_Agent`, `guideline` pour `Symptomatology_Agent`, `laboratory` pour `Lab_Agent`, `protocol` ou `guideline` pour `Treatment_Agent`.

**Validates: Requirements 2.2, 2.3, 2.4, 2.5, 2.6**

---

### Property 6 : Synthesis_Agent garantit au moins 3 diagnostics différentiels

*Pour tout* ensemble de résultats d'agents (y compris le cas où tous les agents retournent zéro chunk), `Synthesis_Agent` doit produire une liste de diagnostics de longueur ≥ 3, en ajoutant des entrées `confidence: low` si nécessaire.

**Validates: Requirements 2.7**

---

### Property 7 : Agents sans chunks exclus de la synthèse

*Pour tout* ensemble de résultats d'agents où certains agents retournent zéro chunk grounded, `Synthesis_Agent` doit exclure ces agents de la fusion et enregistrer leur omission dans le `DiagnosticAudit`.

**Validates: Requirements 2.9**

---

### Property 8 : Chunker respecte la taille maximale et les frontières sémantiques

*Pour tout* texte d'entrée, chaque chunk produit par `Chunker.chunk()` doit avoir une longueur ≤ 800 caractères, et les frontières de chunk doivent coïncider avec les en-têtes de section, les étapes numérotées, ou les limites de phrases.

**Validates: Requirements 3.1**

---

### Property 9 : Préservation de l'en-tête de section dans metadata.section

*Pour tout* texte contenant un en-tête de section détectable, le chunk produit à partir de ce texte doit avoir `metadata.section` égal à l'en-tête de section correspondant.

**Validates: Requirements 3.2**

---

### Property 10 : Enrichissement correct des métadonnées selon la source

*Pour tout* document ingéré depuis une source connue (PNLP, CHU, MSF, OMS/WHO), tous les chunks produits doivent avoir `metadata.document_type` et `metadata.evidence_level` correspondant aux règles de mapping définies dans les requirements.

**Validates: Requirements 3.3**

---

### Property 11 : Reciprocal Rank Fusion produit un classement cohérent

*Pour toutes* deux listes classées de chunks (vecteur et BM25), la fusion RRF doit produire un classement où le score de chaque chunk est la somme de `1 / (k + rank)` sur toutes les listes où il apparaît, avec k = 60.

**Validates: Requirements 3.5**

---

### Property 12 : ConfidenceScore est la moyenne arithmétique des scores retenus

*Pour tout* ensemble de chunks retenus après filtrage par `SIMILARITY_THRESHOLD`, `RAGResponse.confidence_score` doit être égal à la moyenne arithmétique de leurs scores de similarité cosinus.

**Validates: Requirements 4.1**

---

### Property 13 : DiagnosticAudit écrit pour chaque appel diagnostique

*Pour tout* appel à `DiagnosticOrchestrator.get_differential_diagnosis()`, exactement un document `DiagnosticAudit` doit être inséré dans la collection `diagnostic_audit`, contenant tous les champs requis (timestamp, symptoms, patient_profile_hash, locale, region, confidence_score, diagnoses, fallback_used, agent_results).

**Validates: Requirements 4.3, 4.4**

---

### Property 14 : Hash du profil patient exclut les champs PII

*Pour tout* `PatientProfile`, modifier les champs `name` ou les identifiants ne doit pas changer le `patient_profile_hash`, mais modifier `age`, `weight`, `sex`, ou `comorbidities` doit produire un hash différent.

**Validates: Requirements 4.3**

---

### Property 15 : Feedback de récupération stocké avec tous les champs requis

*Pour toute* soumission valide à `POST /api/v1/feedback/retrieval`, le document inséré dans `retrieval_feedback` doit contenir `session_id`, `user_id`, `document_id`, `chunk_id`, `rating` (1 ou -1), et `timestamp`.

**Validates: Requirements 4.7**

---

### Property 16 : Extraction BBox et offsets pour tous les chunks PDF

*Pour tout* document PDF contenant du texte extractible, chaque chunk produit par `DocumentService` doit avoir `metadata.bbox` non-null, `metadata.page_char_start` non-null, et `metadata.page_char_end` non-null.

**Validates: Requirements 5.1**

---

### Property 17 : Migration par lots de 100 chunks maximum

*Pour tout* nombre N de chunks non migrés, l'endpoint `POST /api/v1/admin/migrate-chunks` doit les traiter en ⌈N/100⌉ lots de 100 chunks au maximum chacun.

**Validates: Requirements 6.2**

---

## Error Handling

### Grounding — aucun chunk disponible
- Zéro chunks après filtrage → retourner `RAGResponse` avec `answer = NO_CONTEXT_MESSAGE`, `sources = []`, `confidence_score = 0.0`, sans appeler le LLM.

### MCP — timeout ou échec d'agent
- Agent timeout (> 30s) → traité comme zéro chunks grounded, omission enregistrée dans `DiagnosticAudit`.
- Tous les agents échouent → `Synthesis_Agent` produit 3 diagnostics `confidence: low`.

### LLM — indisponibilité
- LLM primaire indisponible → circuit breaker route vers GPT-5 fallback.
- Les deux LLM indisponibles → HTTP 503 `"llm_unavailable"`.
- `fallback_used=True` → disclaimer ajouté dans la réponse (REQ 4.2).

### Documents — accès et validation
- `GET /api/v1/documents/{id}/view` pour un document inexistant → HTTP 404.
- Chunk non-PDF → `highlight = None`, `CitationPopup` affiche uniquement l'excerpt.

### Migration — données mixtes
- Chunks sans nouveaux champs de métadonnées → log WARNING au démarrage avec le compte.
- `POST /api/v1/admin/reindex-document/{id}` pour un document inexistant → HTTP 404.
- Suppression d'un document → les enregistrements `diagnostic_audit` sont préservés avec des références tombstone.

---

## Testing Strategy

### Approche duale

**Tests unitaires** — exemples spécifiques et cas limites :
- Refus sans contexte : `RAGService` retourne `NO_CONTEXT_MESSAGE` quand zéro chunks passent le seuil
- Dispatch parallèle : `MCP_Host` appelle les quatre agents pour chaque requête
- Timeout agent : un agent lent est traité comme zéro chunks après 30s
- Accès `GET /documents/{id}/view` : 404 pour document inexistant, URL présignée pour document existant
- Intégrité référentielle : suppression de document préserve les enregistrements `diagnostic_audit`
- Détection au démarrage : warning loggé avec le compte de chunks non migrés

**Tests property-based** — propriétés universelles sur entrées générées :
- Bibliothèque Python : **Hypothesis** (déjà utilisé dans le projet)
- Minimum **100 itérations** par propriété (`max_examples=100`)

### Mapping propriétés → tests

| Propriété | Fichier de test | Bibliothèque |
|-----------|----------------|--------------|
| P1 — Grounding prompt présent | `backend/tests/test_rag_service.py` | Hypothesis |
| P2 — Refus/filtrage chunks sous seuil | `backend/tests/test_rag_service.py` | Hypothesis |
| P3 — Indépendance title/source | `backend/tests/test_document_service.py` | Hypothesis |
| P4 — grounding_warning avec degraded_warning | `backend/tests/test_rag_service.py` | Hypothesis |
| P5 — source_filter correct par agent | `backend/tests/test_mcp_host.py` | Hypothesis |
| P6 — Minimum 3 diagnostics | `backend/tests/test_synthesis_agent.py` | Hypothesis |
| P7 — Agents sans chunks exclus | `backend/tests/test_synthesis_agent.py` | Hypothesis |
| P8 — Chunker taille et frontières | `backend/tests/test_chunker.py` | Hypothesis |
| P9 — Préservation section dans metadata | `backend/tests/test_chunker.py` | Hypothesis |
| P10 — Enrichissement métadonnées | `backend/tests/test_document_service.py` | Hypothesis |
| P11 — RRF classement cohérent | `backend/tests/test_rag_service.py` | Hypothesis |
| P12 — ConfidenceScore moyenne arithmétique | `backend/tests/test_rag_service.py` | Hypothesis |
| P13 — DiagnosticAudit écrit à chaque appel | `backend/tests/test_diagnostic_orchestrator.py` | Hypothesis |
| P14 — Hash profil patient exclut PII | `backend/tests/test_diagnostic_orchestrator.py` | Hypothesis |
| P15 — Feedback stocké avec champs requis | `backend/tests/test_feedback_router.py` | Hypothesis |
| P16 — BBox et offsets pour chunks PDF | `backend/tests/test_document_service.py` | Hypothesis |
| P17 — Migration par lots de 100 | `backend/tests/test_admin_router.py` | Hypothesis |

### Configuration Hypothesis

```python
from hypothesis import settings, HealthCheck

settings.register_profile("ci", max_examples=100, suppress_health_check=[HealthCheck.too_slow])
settings.load_profile("ci")
```

Chaque test property-based est annoté :
```python
# Feature: diagno-pilot-improvements, Property N: <texte de la propriété>
@given(...)
@settings(max_examples=100)
def test_property_N_...(...)
```
