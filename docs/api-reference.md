# Référence API — Diagno-Pilot

## Table des matières

- [Model\_Container (llama.cpp)](#model_container-llamacpp)
- [Pipeline LlamaIndex (RAG)](#pipeline-llamaindex-rag)
- [Services de conformité HIPAA](#services-de-conformité-hipaa)

---

## Model\_Container (llama.cpp)

Le Model\_Container est un serveur llama.cpp exposant une API compatible OpenAI. Il sert le modèle `MedicalQwen3-Reasoning-4B.Q8_0.gguf` depuis le répertoire `model/`.

### `POST /v1/chat/completions`

Génération de complétion de chat (format OpenAI).

**Corps de la requête :**

```json
{
  "model": "MedicalQwen3-Reasoning-4B",
  "messages": [
    {"role": "system", "content": "Tu es un assistant médical."},
    {"role": "user", "content": "Quels sont les symptômes du paludisme ?"}
  ]
}
```

**Réponse (200) :**

```json
{
  "choices": [
    {
      "message": {
        "role": "assistant",
        "content": "Les symptômes du paludisme incluent..."
      }
    }
  ]
}
```

### `POST /v1/embeddings`

Génération de vecteurs d'embedding pour l'indexation et la recherche sémantique.

**Corps de la requête :**

```json
{
  "model": "MedicalQwen3-Reasoning-4B",
  "input": "Protocole de traitement du paludisme"
}
```

**Réponse (200) :**

```json
{
  "data": [
    {
      "embedding": [0.0123, -0.0456, ...],
      "index": 0
    }
  ]
}
```

### `GET /health`

Vérification de l'état du serveur. Retourne HTTP 200 lorsque le modèle est chargé et prêt.

**Réponse (200) :**

```json
{"status": "ok"}
```

---

## Pipeline LlamaIndex (RAG)

### `LlamaIndexPipeline.query()`

Point d'entrée principal du pipeline RAG. Combine la recherche hybride (vecteur + BM25) avec la génération LLM.

**Paramètres :**

| Paramètre | Type | Défaut | Description |
|---|---|---|---|
| `question` | `str` | — | Question en langage naturel |
| `context` | `PatientProfile \| None` | `None` | Profil patient (contexte PHI) |
| `top_k` | `int` | `5` | Nombre de chunks à récupérer |
| `region` | `str \| None` | `None` | Pré-filtre régional (`"TG"`, `"BJ"`, `"ALL"`) |
| `source_filter` | `dict \| None` | `None` | Filtres de métadonnées MongoDB par agent |
| `session_history` | `list[dict] \| None` | `None` | Historique de conversation |
| `system_prompt` | `str \| None` | `None` | Prompt système personnalisé (remplace le prompt de grounding par défaut) |

**Retour : `RAGResponse`**

```python
class RAGResponse(BaseModel):
    answer: str                          # Réponse générée
    sources: list[DocumentSource]        # Sources utilisées
    llm_used: str                        # Modèle utilisé ("MedicalQwen3-Reasoning-4B" ou "gpt-5")
    confidence_score: float | None       # Score de confiance (moyenne des scores cosinus)
    fallback_used: bool                  # True si GPT-5 a été utilisé
    degraded_warning: str | None         # Avertissement si mode dégradé
```

**Flux interne :**

1. Vérification du cache Redis (TTL 5 min)
2. Embedding de la question via `EmbeddingModel`
3. Recherche hybride via `IndexManager.retrieve()` (vecteur + BM25 + RRF)
4. Re-ranking par cross-encoder (ms-marco-MiniLM-L-6-v2)
5. Filtrage par seuil de similarité (0.75)
6. Génération via `LLMRouter` (Model\_Container → fallback GPT-5)
7. Mise en cache de la réponse

### `IndexManager.retrieve()`

Recherche hybride combinant recherche vectorielle MongoDB Atlas et BM25.

**Paramètres :**

| Paramètre | Type | Description |
|---|---|---|
| `query_vector` | `list[float]` | Vecteur de la requête |
| `query_text` | `str` | Texte de la requête (pour BM25) |
| `top_k` | `int` | Nombre de résultats |
| `region` | `str \| None` | Filtre régional |
| `source_filter` | `dict \| None` | Filtres de métadonnées additionnels |

**Retour :** `list[dict]` — Liste de chunks triés par pertinence.

### `IndexManager.insert_nodes()`

Insertion incrémentale de nœuds LlamaIndex dans MongoDB.

**Paramètres :**

| Paramètre | Type | Description |
|---|---|---|
| `nodes` | `list[dict]` | Nœuds contenant `content`, `embedding`, `metadata`, `document_id` |

**Retour :** `int` — Nombre de documents insérés.


### `SemanticChunkerService.chunk()`

Découpage sémantique de documents en nœuds LlamaIndex respectant les limites de tokens.

**Paramètres :**

| Paramètre | Type | Description |
|---|---|---|
| `documents` | `list[Document]` | Documents LlamaIndex à découper |

**Retour :** `list[TextNode]` — Nœuds avec métadonnées (section, page, source, région).

**Post-traitements appliqués :**
- Préservation des limites de tableaux (`_preserve_table_boundaries`)
- Préservation de la numérotation des étapes cliniques (`_preserve_step_numbering`)

### `SourceLoaderService.load()`

Chargement de documents avec dispatch par format.

**Paramètres :**

| Paramètre | Type | Description |
|---|---|---|
| `content` | `bytes` | Contenu brut du fichier |
| `filename` | `str` | Nom du fichier (pour détection du format) |
| `source` | `str` | Organisation source (ex: `"PNLP"`, `"CHU Lomé"`) |
| `region` | `str` | Région (`"TG"`, `"BJ"`, `"ALL"`) — défaut `"ALL"` |

**Formats supportés :** PDF, DOCX, CSV, TXT, HTML

**Retour :** `list[Document]` — Documents LlamaIndex avec métadonnées (`source`, `region`, `document_type`, `disease_tags`).

**Erreur :** `ValueError` si le format n'est pas supporté, avec message listant les formats acceptés.

---

## Services de conformité HIPAA

---

## Endpoints Chat

### `GET /api/v1/chat/sessions`

Retourne la liste des sessions de chat de l'utilisateur authentifié, triées par `updated_at` décroissant.

| Attribut | Valeur |
|----------|--------|
| Méthode | `GET` |
| Chemin | `/api/v1/chat/sessions` |
| Rôles requis | `admin`, `medecin`, `infirmière` |

**Paramètres de requête :**

| Paramètre | Type | Défaut | Description |
|---|---|---|---|
| `skip` | `int` | `0` | Nombre de sessions à ignorer |
| `limit` | `int` | `20` | Nombre de sessions à retourner (cap : 100) |

**Réponse 200 OK :**

```json
[
  {
    "session_id": "uuid-string",
    "created_at": "2026-04-07T10:30:00Z",
    "updated_at": "2026-04-07T11:00:00Z",
    "messages": [
      {"role": "user", "content": "Quels sont les symptômes du paludisme ?"}
    ]
  }
]
```

Retourne une liste vide `[]` avec HTTP 200 lorsque l'utilisateur n'a aucune session.

---

### `GET /api/v1/chat/history/{session_id}`

Retourne l'historique paginé des messages d'une session de chat. Vérifie que la session appartient à l'utilisateur authentifié (bypass admin).

| Attribut | Valeur |
|----------|--------|
| Méthode | `GET` |
| Chemin | `/api/v1/chat/history/{session_id}` |
| Rôles requis | `admin`, `medecin`, `infirmière` |

**Paramètres de requête :**

| Paramètre | Type | Défaut | Description |
|---|---|---|---|
| `skip` | `int` | `0` | Offset dans la liste des messages |
| `limit` | `int` | `50` | Nombre de messages à retourner (cap : 200) |

**Réponse 200 OK :**

```json
{
  "session_id": "uuid-string",
  "messages": [...],
  "patient_context": {...},
  "created_at": "2026-04-07T10:30:00Z",
  "updated_at": "2026-04-07T11:00:00Z",
  "total_messages": 42
}
```

**Réponse 404 Not Found** — session inexistante ou non possédée par l'utilisateur :

```json
{"detail": "Chat session not found"}
```

---

### `DELETE /api/v1/chat/sessions/{session_id}`

Supprime une session de chat. Vérifie que la session appartient à l'utilisateur authentifié (bypass admin).

| Attribut | Valeur |
|----------|--------|
| Méthode | `DELETE` |
| Chemin | `/api/v1/chat/sessions/{session_id}` |
| Rôles requis | `admin`, `medecin`, `infirmière` |

**Réponse 200 OK :**

```json
{"status": "deleted"}
```

**Réponse 404 Not Found** — session inexistante ou non possédée par l'utilisateur :

```json
{"detail": "Chat session not found"}
```

---

## Endpoints Diagnostic — Champs mis à jour

### `POST /api/v1/diagnose/symptoms` — Champs de requête mis à jour

**Nouveaux champs dans `DiagnoseRequest` :**

| Champ | Type | Requis | Description |
|---|---|---|---|
| `idempotency_key` | `string \| null` | Non | Clé d'idempotence générée côté client. Si une consultation avec la même clé existe, la réponse existante est retournée (HTTP 200) sans créer de doublon. |

**Contraintes de validation :**

| Champ | Contrainte |
|---|---|
| `symptoms` | `min_length=1, max_length=30` |
| `symptoms[].name` | `max_length=200` |

**Nouveau champ dans `DiagnoseResponse` :**

| Champ | Type | Description |
|---|---|---|
| `parse_failed` | `bool` | `true` si le parseur n'a pas pu extraire ≥ 3 diagnostics valides. Le frontend affiche un avertissement. |

---

### `POST /api/v1/diagnose/prescription` — Champs de requête mis à jour

**Nouveau champ dans `PrescriptionRequest` :**

| Champ | Type | Requis | Description |
|---|---|---|---|
| `session_id` | `string \| null` | Non | Identifiant de la session diagnostique. Lorsque fourni, la prescription et les alertes sont liées à la consultation correspondante. |

Lorsque `session_id` est fourni, le routeur met à jour les champs `prescription` et `alerts` du document de consultation correspondant (avec vérification de propriété). Lorsque `session_id` est absent, la prescription est retournée sans persistance (comportement existant préservé).

---

## Services de conformité HIPAA

### PHI\_Classifier

Classifie les champs de données comme PHI ou non-PHI.

**Champs PHI connus :**
`full_name`, `date_of_birth`, `medical_record_number`, `allergies`, `current_medications`, `comorbidities`, `weight_kg`, `diagnoses`, `prescriptions`, `consultation_notes`, `differential_diagnoses`, `partial_differential`

**Champs non-PHI connus :**
`age_group`, `created_by`, `created_at`, `updated_at`, `confidence_score`, `locale`, `region`, `fallback_used`, `source`, `document_type`, `evidence_level`, `disease_tags`

**Règle par défaut :** Les champs inconnus sont classifiés comme PHI.

**Méthodes :**

| Méthode | Description |
|---|---|
| `is_phi(field_name)` | `True` si PHI, `False` si non-PHI, `True` si inconnu |
| `classify_document(data)` | Retourne `{champ: is_phi}` pour chaque clé |
| `extract_phi_fields(data)` | Retourne uniquement les champs PHI |
| `extract_non_phi_fields(data)` | Retourne uniquement les champs non-PHI |

### Encryption\_Service

Chiffrement AES-256 au niveau des champs pour les données PHI.

**Méthodes :**

| Méthode | Description |
|---|---|
| `encrypt_field(plaintext)` | Chiffre une valeur → ciphertext base64 |
| `decrypt_field(ciphertext)` | Déchiffre une valeur → plaintext original |
| `encrypt_phi_fields(data, classifier)` | Chiffre tous les champs PHI (string) d'un dict |
| `decrypt_phi_fields(data, classifier)` | Déchiffre tous les champs PHI (string) d'un dict |
| `rotate_key(new_key)` | Rotation de clé avec fallback sur l'ancienne clé pour déchiffrement |

**Gestion d'erreurs :** En cas d'échec, l'erreur est journalisée dans l'Audit\_Logger sans exposer le plaintext. Une `EncryptionError` est levée.

### Audit\_Logger

Journal d'audit HIPAA avec chaîne de hachage anti-falsification.

**Collection MongoDB :** `hipaa_audit_logs` (append-only, pas de mise à jour ni suppression)

**Méthodes :**

| Méthode | Description |
|---|---|
| `log_action(user_id, action, resource, ...)` | Enregistre un événement avec chaîne de hachage |
| `verify_chain(records)` | Vérifie l'intégrité de la chaîne de hachage |

**Schéma d'un enregistrement :**

```python
class HIPAAAuditRecord(BaseModel):
    id: str
    timestamp: datetime
    user_id: str
    action: str          # phi_read | phi_write | phi_delete | llm_request | phi_strip
    resource: str
    resource_id: str | None
    details: dict
    ip_address: str | None
    previous_hash: str   # Hash de l'enregistrement précédent
    record_hash: str     # SHA-256(previous_hash + json(record_data))
```

**Fallback :** Si l'écriture MongoDB échoue, l'enregistrement est écrit dans un fichier JSONL local (`/var/log/diagno-pilot/audit_fallback.jsonl`).

### BAA\_Controller

Contrôle BAA (Business Associate Agreement) — garantit zéro PHI dans les appels LLM externes.

**Méthodes :**

| Méthode | Description |
|---|---|
| `strip_phi(context, classifier)` | Remplace les valeurs PHI par des placeholders |
| `verify_no_phi(context, classifier)` | Vérifie l'absence de PHI — lève `BAAStripError` si PHI détecté |

**Placeholders utilisés :**

| Champ PHI | Placeholder |
|---|---|
| `full_name` | `[PATIENT_NAME]` |
| `date_of_birth` | `[DOB]` |
| `medical_record_number` | `[MRN]` |
| `allergies` | `[ALLERGIES]` |
| `current_medications` | `[MEDICATIONS]` |
| `comorbidities` | `[COMORBIDITIES]` |
| `weight_kg` | `[WEIGHT]` |
| `diagnoses` | `[DIAGNOSES]` |
| `prescriptions` | `[PRESCRIPTIONS]` |
| `consultation_notes` | `[NOTES]` |
| `differential_diagnoses` | `[DIFFERENTIAL]` |
| `partial_differential` | `[PARTIAL_DIFFERENTIAL]` |

**Flux :**
1. Remplacement des valeurs PHI par les placeholders
2. Vérification post-stripping (aucun PHI résiduel)
3. Journalisation de l'événement (types de champs uniquement, pas de valeurs PHI)
4. Si le stripping échoue → l'appel LLM externe est bloqué (`BAAStripError`)


---

## Serveurs MCP — Endpoints JSON-RPC 2.0

Chaque serveur MCP spécialiste est un service Docker FastAPI exposant deux endpoints HTTP. La communication utilise le protocole JSON-RPC 2.0 : les requêtes sont envoyées via HTTP POST et les réponses sont streamées via Server-Sent Events (SSE).

### `POST /rpc`

Point d'entrée JSON-RPC 2.0 pour toutes les interactions MCP (découverte et invocation des primitives).

**En-têtes requis :**

| En-tête | Valeur |
|---|---|
| `Content-Type` | `application/json` |

**Corps de la requête (JSON-RPC 2.0) :**

```json
{
  "jsonrpc": "2.0",
  "method": "tools/list | tools/call | resources/list | resources/read | prompts/list | prompts/get",
  "params": {},
  "id": 1
}
```

**Méthodes supportées :**

| Méthode | Description | Paramètres |
|---|---|---|
| `tools/list` | Liste les tools disponibles | `{}` |
| `tools/call` | Invoque un tool | `{"name": "tool_name", "arguments": {...}}` |
| `resources/list` | Liste les resources disponibles | `{}` |
| `resources/read` | Lit le contenu d'une resource | `{"uri": "resource_uri"}` |
| `prompts/list` | Liste les prompts disponibles | `{}` |
| `prompts/get` | Récupère un prompt | `{"name": "prompt_name"}` |

**Réponse (SSE — `text/event-stream`) :**

Succès :
```
data: {"jsonrpc": "2.0", "result": {...}, "id": 1}
```

Erreur :
```
data: {"jsonrpc": "2.0", "error": {"code": -32601, "message": "Method not found"}, "id": 1}
```

**Codes d'erreur JSON-RPC 2.0 :**

| Code | Signification |
|---|---|
| `-32700` | Parse error — JSON invalide |
| `-32600` | Invalid Request — structure JSON-RPC invalide |
| `-32601` | Method not found — méthode inconnue |
| `-32602` | Invalid params — paramètres manquants ou invalides |
| `-32603` | Internal error — erreur interne du serveur |

### `GET /health`

Vérification de la disponibilité du serveur MCP.

**Réponse (200) :**

```json
{"status": "ok", "server": "epidemiology"}
```

### Serveurs MCP disponibles

| Serveur | Port | Tool | Resource URI | Prompt |
|---|---|---|---|---|
| Épidémiologie | 8001 | `query_epidemiology` | `epidemiology://documents` | `epidemiology_query` |
| Symptomatologie | 8002 | `query_symptomatology` | `guidelines://documents` | `symptomatology_query` |
| Laboratoire | 8003 | `query_lab` | `laboratory://documents` | `lab_query` |
| Traitement | 8004 | `query_treatment` | `protocols://documents` | `treatment_query` |

### Schéma d'entrée commun des Tools MCP

Tous les tools MCP acceptent le même schéma JSON d'entrée :

```json
{
  "symptoms": [
    {"name": "fièvre", "severity": "élevée", "duration_days": 3}
  ],
  "patient_profile": {"age": 35, "weight_kg": 70, "sex": "M"},
  "locale": "fr-TG",
  "region": "TG"
}
```

| Paramètre | Type | Requis | Description |
|---|---|---|---|
| `symptoms` | `array[object]` | Oui | Liste des symptômes (chaque objet contient `name`, `severity` optionnel, `duration_days` optionnel) |
| `patient_profile` | `object \| null` | Non | Profil patient (âge, poids, antécédents) |
| `locale` | `string` | Oui | Locale BCP-47 (`fr-TG`, `fr-BJ`, `en`) |
| `region` | `string \| null` | Non | Code région ISO 3166-1 alpha-2 (`TG`, `BJ`) |

### Schéma de sortie AgentResult

Retourné dans le champ `result` de la réponse JSON-RPC 2.0 :

```json
{
  "agent_name": "epidemiology",
  "sub_question": "Quelles sont les données épidémiologiques...",
  "chunks": [
    {
      "document_id": "ObjectId",
      "title": "Bulletin épidémiologique Togo 2024",
      "source": "PNLP",
      "excerpt": "La prévalence du paludisme...",
      "page": 12
    }
  ],
  "confidence_score": 0.85,
  "partial_differential": [
    {
      "condition": "Paludisme",
      "probability": 0.75,
      "icd_code": "B50",
      "matching_symptoms": ["fièvre", "céphalées"]
    }
  ],
  "fallback_used": false
}
```

---

## Diagnostic guidé multi-agent — Réponse enrichie

### `POST /api/v1/diagnose/symptoms` — Schéma de réponse enrichi

Le endpoint existant retourne désormais des champs additionnels liés au pipeline MCP multi-agent.

**Nouveaux champs dans `DiagnoseResponse` :**

| Champ | Type | Description |
|---|---|---|
| `mcp_session_id` | `string \| null` | Identifiant unique de la session MCP (UUID) |
| `confidence_score` | `float \| null` | Score de confiance global [0.0, 1.0], moyenne pondérée par chunks |
| `agent_contributions` | `array[AgentContribution]` | Contributions de chaque agent spécialiste |
| `evidence_citations` | `array[EvidenceCitation]` | Citations de preuves documentaires |
| `fallback_warning` | `string \| null` | Avertissement si le LLM de secours a été utilisé |
| `degraded_warning` | `string \| null` | Avertissement listant les agents omis |
| `warnings_present` | `boolean` | `true` si `fallback_warning` ou `degraded_warning` est présent |

**Schéma `AgentContribution` :**

```json
{
  "agent_name": "epidemiology",
  "confidence_score": 0.85,
  "partial_differential": [
    {"condition": "Paludisme", "probability": 0.75, "icd_code": "B50", "matching_symptoms": ["fièvre"]}
  ]
}
```

**Schéma `EvidenceCitation` :**

```json
{
  "document_id": "ObjectId",
  "title": "Bulletin épidémiologique Togo 2024",
  "source": "PNLP",
  "excerpt": "La prévalence du paludisme dans la région...",
  "page": 12
}
```

**Exemple de réponse complète :**

```json
{
  "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "mcp_session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "diagnoses": [
    {"condition": "Paludisme", "probability": 0.75, "icd_code": "B50", "matching_symptoms": ["fièvre", "céphalées"]}
  ],
  "confidence_score": 0.82,
  "agent_contributions": [
    {"agent_name": "epidemiology", "confidence_score": 0.85, "partial_differential": [...]},
    {"agent_name": "symptomatology", "confidence_score": 0.80, "partial_differential": [...]}
  ],
  "evidence_citations": [
    {"document_id": "...", "title": "Bulletin épidémiologique", "source": "PNLP", "excerpt": "...", "page": 12}
  ],
  "fallback_warning": null,
  "degraded_warning": null,
  "warnings_present": false
}
```

---

### `GET /api/v1/consultations/me`

Retourne l'historique paginé des consultations du praticien authentifié, triées par date décroissante.

| Attribut | Valeur |
|---|---|
| Méthode | `GET` |
| Chemin | `/api/v1/consultations/me` |
| Rôles requis | `admin`, `medecin`, `infirmière` |
| Rate limit | 30 requêtes/minute par utilisateur |

**Paramètres de requête :**

| Paramètre | Type | Défaut | Description |
|---|---|---|---|
| `page` | `int` | `1` | Numéro de page (≥ 1) |
| `page_size` | `int` | `20` | Nombre d'éléments par page (1–100) |

**Réponse 200 OK — `PaginatedResponse[Consultation]` :**

```json
{
  "items": [
    {
      "id": "ObjectId",
      "patient_id": "ObjectId | null",
      "user_id": "ObjectId",
      "symptoms": [...],
      "diagnoses": [...],
      "prescription": null,
      "alerts": [],
      "llm_used": "MedicalQwen3-Reasoning-14B",
      "is_one_shot": true,
      "created_at": "2026-04-07T10:30:00Z",
      "mcp_session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "agent_contributions": [
        {"agent_name": "epidemiology", "confidence_score": 0.85, "partial_differential": [...]}
      ],
      "evidence_citations": [
        {"document_id": "...", "title": "...", "source": "PNLP", "excerpt": "...", "page": 12}
      ]
    }
  ],
  "total": 42,
  "page": 1,
  "page_size": 20
}
```

**Réponse 403 Forbidden** — rôle non autorisé

```json
{"detail": "Insufficient permissions"}
```
