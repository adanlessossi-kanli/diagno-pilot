# Guide de conformité HIPAA — Diagno-Pilot

## Table des matières

- [Vue d'ensemble](#vue-densemble)
- [Classification PHI](#classification-phi)
- [Chiffrement AES-256](#chiffrement-aes-256)
- [Journal d'audit HIPAA](#journal-daudit-hipaa)
- [Chaîne de hachage et vérification](#chaîne-de-hachage-et-vérification)
- [Contrôles BAA (Business Associate Agreement)](#contrôles-baa)
- [Rotation des clés](#rotation-des-clés)
- [Frontière PHI dans le pipeline d'agents](#frontière-phi-dans-le-pipeline-dagents)

---

## Vue d'ensemble

Diagno-Pilot implémente les contrôles HIPAA suivants :

1. **Classification PHI** — Identification automatique des champs contenant des informations de santé protégées
2. **Chiffrement au repos** — AES-256-GCM (AESGCM) pour les champs PHI dans MongoDB, avec fallback Fernet pour la compatibilité descendante
3. **Audit anti-falsification** — Journal d'audit avec chaîne de hachage SHA-256
4. **Contrôles BAA** — Zéro PHI dans les appels vers les LLM externes (GPT-5)
5. **Frontière PHI** — Séparation stricte entre le modèle local (PHI autorisé) et les services externes (PHI interdit)

## Classification PHI

Le service `PHIClassifier` (`backend/services/phi_classifier.py`) classifie chaque champ de données comme PHI ou non-PHI.

### Champs PHI

| Champ | Source | Description |
|---|---|---|
| `full_name` | PatientProfile | Nom complet du patient |
| `date_of_birth` | PatientProfile | Date de naissance |
| `medical_record_number` | PatientProfile | Numéro de dossier médical |
| `allergies` | PatientProfile | Allergies connues |
| `current_medications` | PatientProfile | Médicaments en cours |
| `comorbidities` | PatientProfile | Comorbidités |
| `weight_kg` | PatientProfile | Poids |
| `diagnoses` | DiagnosticAudit | Diagnostics |
| `prescriptions` | DiagnosticAudit | Prescriptions |
| `consultation_notes` | DiagnosticAudit | Notes de consultation |
| `differential_diagnoses` | DiagnosticAudit | Diagnostics différentiels |
| `partial_differential` | DiagnosticAudit | Différentiel partiel |

### Champs non-PHI

`age_group`, `created_by`, `created_at`, `updated_at`, `confidence_score`, `locale`, `region`, `fallback_used`, `source`, `document_type`, `evidence_level`, `disease_tags`

### Règle par défaut

Les champs inconnus (non listés ci-dessus) sont classifiés comme PHI par défaut. Cette approche conservatrice garantit qu'aucune donnée sensible n'est accidentellement exposée.

## Chiffrement AES-256-GCM

Le service `EncryptionService` (`backend/services/encryption_service.py`) fournit le chiffrement au niveau des champs.

### Algorithme

- **AES-256-GCM** via `cryptography.hazmat.primitives.ciphers.aead.AESGCM` — chiffrement authentifié
- Clé de 32 octets (256 bits) encodée en base64 URL-safe
- Nonce aléatoire de 12 octets (96 bits) généré pour chaque opération de chiffrement
- Tag d'authentification GCM de 16 octets intégré au ciphertext

### Format ciphertext

```
base64url( nonce[12 octets] || ciphertext + tag[16 octets] )
```

Le nonce de 12 octets est préfixé au ciphertext+tag, puis le tout est encodé en base64 URL-safe pour stockage en MongoDB.

### Génération d'une clé

```bash
python -c "import os, base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
```

### Flux de chiffrement

```
Plaintext → AESGCM.encrypt(nonce, plaintext_utf8) → base64url(nonce || ciphertext+tag) → Stockage MongoDB
```

### Flux de déchiffrement

```
base64url ciphertext → Extraire nonce[12] et ciphertext+tag → AESGCM.decrypt(nonce, ciphertext+tag) → Plaintext original
```

### Fallback Fernet (compatibilité descendante)

Les données chiffrées avec l'ancien algorithme Fernet (AES-128-CBC + HMAC-SHA256) sont toujours lisibles. Le service de déchiffrement détecte automatiquement le format :

- Les tokens Fernet commencent par `gAAAAA` (base64 standard)
- Les tokens AES-256-GCM utilisent base64 URL-safe

Si le déchiffrement AES-256-GCM échoue, le service tente automatiquement un déchiffrement Fernet avant de lever une erreur.

> **Migration :** Les anciennes clés Fernet (44 caractères base64 standard) ne sont pas compatibles avec AES-256-GCM. Générez une nouvelle clé avec la commande ci-dessus et mettez à jour `HIPAA_ENCRYPTION_KEY_ID`.

### Chiffrement des champs PHI

```python
from backend.services.encryption_service import EncryptionService
from backend.services.phi_classifier import PHIClassifier

enc = EncryptionService(key="votre_clé_aesgcm_base64url")
classifier = PHIClassifier()

# Chiffrer tous les champs PHI d'un dictionnaire
data = {"full_name": "Jean Dupont", "region": "TG"}
encrypted = enc.encrypt_phi_fields(data, classifier)
# → {"full_name": "base64url_nonce_ciphertext...", "region": "TG"}

# Déchiffrer
decrypted = enc.decrypt_phi_fields(encrypted, classifier)
# → {"full_name": "Jean Dupont", "region": "TG"}
```

### Gestion des erreurs

- En cas d'échec de chiffrement/déchiffrement, une `EncryptionError` est levée
- L'erreur est journalisée dans l'Audit\_Logger sans exposer le plaintext
- Le plaintext n'est jamais inclus dans les messages d'erreur ou les logs

## Journal d'audit HIPAA

Le service `AuditLogger` (`backend/services/audit_service.py`) enregistre tous les accès et modifications PHI.

### Collection MongoDB

**Nom :** `hipaa_audit_logs`

**Sémantique :** Append-only — aucune opération de mise à jour ou suppression n'est autorisée.

### Format d'un enregistrement

```json
{
  "id": "uuid-v4",
  "timestamp": "2026-04-06T12:00:00Z",
  "user_id": "user_123",
  "action": "phi_read",
  "resource": "patient_profile",
  "resource_id": "patient_456",
  "details": {"field_types": ["full_name", "date_of_birth"]},
  "ip_address": "192.168.1.100",
  "previous_hash": "abc123...",
  "record_hash": "def456..."
}
```

### Types d'actions

| Action | Description |
|---|---|
| `phi_read` | Lecture de champs PHI |
| `phi_write` | Écriture/modification de champs PHI |
| `phi_delete` | Suppression de données PHI |
| `llm_request` | Requête LLM contenant du contexte PHI |
| `phi_strip` | Stripping PHI avant appel LLM externe |
| `phi_strip_failure` | Échec du stripping PHI |
| `encryption_failure` | Échec de chiffrement/déchiffrement |
| `agent_invocation` | Invocation d'un agent du pipeline diagnostique |

### Fallback local

Si l'écriture MongoDB échoue, l'enregistrement est écrit dans un fichier JSONL local :

```
/var/log/diagno-pilot/audit_fallback.jsonl
```

Chaque ligne est un objet JSON complet incluant les hashes de la chaîne.

## Chaîne de hachage et vérification

Chaque enregistrement d'audit inclut un hash cryptographique liant l'enregistrement au précédent.

### Calcul du hash

```
record_hash = SHA-256(previous_hash + JSON(record_data))
```

Où `record_data` contient : `id`, `timestamp`, `user_id`, `action`, `resource`, `resource_id`, `details`, `ip_address`.

### Vérification de l'intégrité

```python
from backend.services.audit_service import AuditLogger

logger = AuditLogger(database=db)
is_valid = await logger.verify_chain()
# True si la chaîne est intacte, False si falsification détectée
```

La vérification parcourt tous les enregistrements chronologiquement et recalcule chaque hash. Si un enregistrement a été modifié, le hash recalculé ne correspondra pas au hash stocké.

### Détection de falsification

| Scénario | Résultat de `verify_chain()` |
|---|---|
| Chaîne intacte | `True` |
| Enregistrement modifié | `False` (hash ne correspond pas) |
| Enregistrement supprimé | `False` (chaîne brisée) |
| Enregistrement inséré | `False` (hash précédent incorrect) |

## Contrôles BAA

Le `BAAController` (`backend/services/baa_controller.py`) garantit qu'aucune donnée PHI n'est transmise aux LLM externes.

### Flux de stripping PHI

```
Contexte LLM (avec PHI)
    ↓
BAAController.strip_phi()
    ↓ Remplacement par placeholders
Contexte sanitisé (zéro PHI)
    ↓
verify_no_phi() — vérification post-stripping
    ↓
Journalisation (types de champs uniquement)
    ↓
Envoi vers GPT-5
```

### Placeholders

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

Les champs PHI inconnus sont remplacés par `[REDACTED]`.

### Sécurité

- Si le stripping échoue → l'appel LLM externe est bloqué (`BAAStripError`)
- Si la vérification post-stripping détecte du PHI résiduel → l'appel est bloqué
- Les logs d'audit enregistrent les types de champs strippés, jamais les valeurs PHI

## Rotation des clés

Le service `EncryptionService` supporte la rotation de clés de chiffrement.

### Procédure

```python
enc = EncryptionService(key="ancienne_clé_aesgcm")

# Rotation vers une nouvelle clé
enc.rotate_key("nouvelle_clé_aesgcm_base64url")

# Après rotation :
# - Les nouvelles écritures utilisent la nouvelle clé AES-256-GCM
# - Les lectures tentent d'abord la nouvelle clé, puis l'ancienne (AESGCM), puis le fallback Fernet
```

### Étapes de rotation en production

1. Générer une nouvelle clé AES-256-GCM : `python -c "import os, base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"`
2. Mettre à jour `HIPAA_ENCRYPTION_KEY_ID` dans la configuration
3. Appeler `rotate_key()` sur le service — l'ancienne clé AESGCM et l'ancienne clé Fernet sont conservées pour le déchiffrement
4. Re-chiffrer progressivement les données existantes avec la nouvelle clé
5. Une fois toutes les données re-chiffrées, les anciennes clés peuvent être retirées

## Frontière PHI dans le pipeline d'agents

Le pipeline d'agents (`AgentPipeline`) applique une frontière PHI stricte :

```
┌─────────────────────────────────────────────┐
│           Model_Container (local)            │
│         PHI AUTORISÉ — données complètes     │
│  ┌─────────┐ ┌──────────┐ ┌──────────────┐  │
│  │Symptom. │ │Epidemio. │ │ Lab/Synth/Tx │  │
│  └─────────┘ └──────────┘ └──────────────┘  │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│            GPT-5 (externe)                   │
│       PHI INTERDIT — placeholders seuls      │
│                                              │
│  BAA_Controller.strip_phi() appliqué         │
│  avant chaque requête                        │
└─────────────────────────────────────────────┘
```

- Le `LLMRouter` applique automatiquement le stripping PHI lors du fallback vers GPT-5
- Chaque invocation d'agent est journalisée avec : type d'agent, hash de la requête, endpoint utilisé, durée
