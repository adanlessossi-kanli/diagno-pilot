# RAG & Chat Workflow — Diagno-Pilot

## Document Ingestion Pipeline

```mermaid
flowchart TD
    A([Admin / Médecin]) -->|POST /api/v1/documents/upload| B[documents router]
    B --> C{Format check\nPDF · DOCX · TXT · CSV}
    C -->|unsupported| ERR1([HTTP 422])
    C -->|supported| D[DocumentService.ingest]

    D --> E[Extract text\npypdf · python-docx · utf-8 · csv]
    E --> F[Upload raw file\nto S3  documents/ prefix]
    F --> G[Persist metadata\nmongodb: medical_documents]
    G --> H[chunk_text\n500 chars · 50 overlap]
    H --> I[EmbeddingModel.encode per chunk\nOpenAI-compatible /embeddings]

    I --> J{Redis cache\nSHA256 text · TTL 24 h}
    J -->|hit| K[Return cached vector]
    J -->|miss| L[Call embedding API\ntext-embedding-ada-002]
    L --> M[Cache vector in Redis]
    M --> K

    K --> N[Store chunk + vector\nmongodb: document_chunks\nembedding_index vectorSearch]
    N --> O[Update chunk_count\non medical_documents]
    O --> P([MedicalDocument returned])
```

---

## RAG Query Pipeline

```mermaid
flowchart TD
    Q([User query + optional PatientProfile]) --> R[RAGService.query]

    R --> S{Redis RAG cache\nSHA256 question+context+region · TTL 5 min}
    S -->|hit| T([Return cached RAGResponse])
    S -->|miss| U[EmbeddingModel.encode question]

    U --> V[MongoDB $vectorSearch\ncollection: document_chunks\nindex: embedding_index\ntop_k = 5 · cosine similarity\noptional region pre-filter]

    V -->|success| W[Retrieved chunks\ncontent · metadata · score]
    V -->|failure| X[Keyword fallback\n$text search on content\ndegraded_warning set]
    X --> W

    W --> Y[Build LLM context\nsystem messages + retrieved passages\n+ patient context if present]
    Y --> Z[LLMRouter.generate]

    Z --> AA{Primary LLM\nMedicalQwen3-Reasoning-14B\nCircuitBreaker · RetryPolicy}
    AA -->|success| AB[LLM answer\nfallback_used = false]
    AA -->|circuit open / retries exhausted| AC{Fallback LLM\nGPT-5\nCircuitBreaker · RetryPolicy}
    AC -->|success| AD[LLM answer\nfallback_used = true]
    AC -->|failure| AE([HTTP 503 LLM_UNAVAILABLE])

    AB --> AF[Cache RAGResponse in Redis\nTTL 5 min]
    AD --> AF
    AF --> AG([RAGResponse\nanswer · sources · llm_used · warnings])
```

---

## Chat Session Flow

```mermaid
sequenceDiagram
    actor User
    participant ChatRouter as chat router<br/>POST /api/v1/chat/message
    participant ChatService
    participant RAGService as LlamaIndexPipeline
    participant EmbeddingModel
    participant MongoDB
    participant Redis
    participant LLMRouter

    User->>ChatRouter: {message, session_id?, patient_context?}
    ChatRouter->>ChatRouter: Validate ownership<br/>(user_id == session owner OR admin)
    ChatRouter->>ChatService: send_message(session_id, message, patient_context, user_id)

    ChatService->>MongoDB: _load_history(session_id)
    MongoDB-->>ChatService: session messages
    ChatService->>ChatService: Cap history to last 20 messages

    ChatService->>RAGService: query(question, context, top_k=5,<br/>session_history=history[-20:])

    RAGService->>Redis: GET rag cache key<br/>(includes history hash when session_history present)
    alt cache hit
        Redis-->>RAGService: RAGResponse
    else cache miss
        RAGService->>EmbeddingModel: encode(question)
        EmbeddingModel->>Redis: GET embedding cache
        alt embedding cached
            Redis-->>EmbeddingModel: vector
        else
            EmbeddingModel->>EmbeddingModel: call /embeddings API
            EmbeddingModel->>Redis: SET embedding (TTL 24 h)
        end
        EmbeddingModel-->>RAGService: query vector

        RAGService->>MongoDB: $vectorSearch document_chunks
        MongoDB-->>RAGService: top-k chunks

        RAGService->>RAGService: Filter sources by<br/>SOURCE_RELEVANCE_THRESHOLD (≥ 0.3)

        RAGService->>LLMRouter: generate(question, context+chunks+session_history)
        LLMRouter->>LLMRouter: try MedicalQwen3 (CircuitBreaker + Retry)
        alt primary ok
            LLMRouter-->>RAGService: answer, fallback_used=false
        else primary failed
            LLMRouter->>LLMRouter: try GPT-5 (CircuitBreaker + Retry)
            LLMRouter-->>RAGService: answer, fallback_used=true
        end

        RAGService->>Redis: SET rag cache (TTL 5 min)
        RAGService-->>ChatService: RAGResponse
    end

    ChatService->>MongoDB: upsert chat_sessions\n(user turn + assistant turn + sources)
    ChatService-->>ChatRouter: (session_id, RAGResponse)
    ChatRouter-->>User: {session_id, answer, sources, llm_used, warnings}
```

---

## Session Ownership & Access Control

All chat endpoints enforce session ownership to protect PHI:

- `GET /api/v1/chat/history/{session_id}` — verifies `user_id` matches the session owner before returning data. Returns HTTP 404 if the session does not belong to the requester.
- `DELETE /api/v1/chat/sessions/{session_id}` — same ownership check before deletion.
- Users with the `admin` role bypass ownership checks and can access any session.

The `ChatService.get_history()` method accepts an optional `user_id` parameter that is included in the MongoDB query filter alongside `session_id`.

---

## Session Listing

`GET /api/v1/chat/sessions` returns the authenticated user's chat sessions, sorted by `updated_at` descending.

- Supports `skip` and `limit` query parameters (default limit: 20, cap: 100).
- Each session includes `session_id`, `created_at`, `updated_at`, and a preview of the first user message.
- Returns an empty list with HTTP 200 when the user has no sessions.

---

## Chat History Pagination

`GET /api/v1/chat/history/{session_id}` supports paginated message retrieval:

- `skip` (default 0) and `limit` (default 50, cap 200) query parameters.
- Response includes a `total_messages` field with the total count of messages in the session.
- Uses MongoDB `$slice` to return only the requested message window.

---

## Diagnosis Mode Routing

The `DIAGNOSIS_MODE` environment variable selects which diagnosis path the `DiagnosticOrchestrator` uses. When the selected dependency (MCP_Host or AgentPipeline) is not configured, the system falls back to the RAG path with a logged warning.

```mermaid
flowchart TD
    A[POST /api/v1/diagnose/symptoms] --> B[Diagnose Router]
    B --> C[DiagnosticOrchestrator]
    C --> D{DIAGNOSIS_MODE}
    D -->|rag| E[RAG Path: LlamaIndexPipeline]
    D -->|mcp| F{MCP_Host configured?}
    D -->|agent| G{AgentPipeline configured?}

    F -->|yes| H[MCP Path: MCP_Host + Synthesis_Agent]
    F -->|no| I[⚠ Warning logged — fallback to RAG]
    I --> E

    G -->|yes| J[Agent Path: AgentPipeline]
    G -->|no| K[⚠ Warning logged — fallback to RAG]
    K --> E

    E --> L[DiagnosticParser.parse]
    H --> M[Synthesis_Agent.synthesize]
    J --> N[_parse_partial_differential]

    L --> O[DiagnosticResult]
    M --> O
    N --> O

    O --> P[Diagnose Router Response<br/>includes diagnosis_mode field]
```

Valid values for `DIAGNOSIS_MODE`: `rag` (default), `mcp`, `agent`.

---

## LLM URL Priority

The `LLMRouter` selects the primary LLM endpoint using the following priority:

1. `MODEL_CONTAINER_URL` — used when set to a non-empty value (e.g. `http://model:8080/v1` for a local Docker model container)
2. `LLM_PRIMARY_URL` — used when `MODEL_CONTAINER_URL` is empty (default)

`MODEL_CONTAINER_URL` defaults to an empty string (`""`). Existing Docker Compose deployments that rely on a local model container must explicitly set `MODEL_CONTAINER_URL` in their `.env` file.

```mermaid
flowchart LR
    A{MODEL_CONTAINER_URL<br/>non-empty?} -->|yes| B[Use MODEL_CONTAINER_URL]
    A -->|no| C{LLM_PRIMARY_URL set?}
    C -->|yes| D[Use LLM_PRIMARY_URL]
    C -->|no| E[No primary LLM available]
```

---

## LLM Router — Resilience Detail

```mermaid
stateDiagram-v2
    direction LR

    [*] --> CLOSED_Primary : startup

    CLOSED_Primary --> CLOSED_Primary : request ok
    CLOSED_Primary --> CLOSED_Primary : retry (jittered backoff\nmax 3 attempts · 1–30 s)
    CLOSED_Primary --> OPEN_Primary : 5 consecutive failures

    OPEN_Primary --> HALF_OPEN_Primary : cooldown elapsed
    HALF_OPEN_Primary --> CLOSED_Primary : probe succeeds
    HALF_OPEN_Primary --> OPEN_Primary : probe fails

    OPEN_Primary --> CLOSED_Fallback : route to GPT-5

    CLOSED_Fallback --> CLOSED_Fallback : request ok
    CLOSED_Fallback --> OPEN_Fallback : 5 consecutive failures
    OPEN_Fallback --> [*] : HTTP 503
```

---

## Caching Layers

```mermaid
flowchart LR
    subgraph Redis
        EC["Embedding cache\nkey: v1:embedding:SHA256 text\nTTL: 24 h"]
        RC["RAG response cache\nkey: v1:rag:SHA256 q+ctx+region\nTTL: 5 min"]
        PC["Protocol / interaction cache\nwarm-up at startup · TTL: 1 h"]
    end

    EmbeddingModel <-->|read / write| EC
    RAGService <-->|read / write| RC
    PrescriptionService <-->|read / write| PC
    AlertService <-->|read / write| PC

    note["Degraded mode: Redis unavailable\n→ all cache ops become no-ops\n→ app continues with cold cache"]
```
