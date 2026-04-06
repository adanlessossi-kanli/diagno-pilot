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
