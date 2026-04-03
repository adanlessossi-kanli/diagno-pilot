# Plan d'implémentation : Diagno-Pilot Improvements

## Vue d'ensemble

Implémentation des six axes d'amélioration de Diagno-Pilot : Strict Document Grounding (REQ 1), Multi-Agent Diagnostic via MCP (REQ 2), RAG Pipeline amélioré (REQ 3), Safety & Audit (REQ 4), PDF Citation Popup (REQ 5), Data Integrity & Migration (REQ 6). Stack : FastAPI (Python 3.12) + MongoDB (Motor async) + Next.js 15 App Router (TypeScript) + React Native Expo.

## Tâches

- [x] 1. Strict Document Grounding — RAGService
  - [x] 1.1 Ajouter `GROUNDING_SYSTEM_PROMPT`, `SIMILARITY_THRESHOLD`, et `NO_CONTEXT_MESSAGE` dans `backend/services/rag_service.py`
    - Définir les constantes `SIMILARITY_THRESHOLD = 0.75` et `NO_CONTEXT_MESSAGE`
    - Injecter `GROUNDING_SYSTEM_PROMPT` comme premier message `system` dans chaque appel `LLMRouter.generate()`
    - Filtrer les chunks dont le score cosinus est < 0.75 avant d'appeler le LLM
    - Retourner `RAGResponse(answer=NO_CONTEXT_MESSAGE, sources=[], confidence_score=0.0)` si aucun chunk ne passe le filtre, sans appeler le LLM
    - _Requirements: 1.1, 1.2, 1.3_

  - [x] 1.2 Étendre `DocumentSource` et `RAGResponse` dans `backend/models/`
    - Ajouter `title: str` (depuis `metadata.title`) et `source: str` (depuis `metadata.source`) dans `DocumentSource`, indépendants l'un de l'autre
    - Ajouter `confidence_score: float | None` et `grounding_warning: str | None` dans `RAGResponse`
    - Peupler `grounding_warning` quand `degraded_warning` est actif
    - _Requirements: 1.4, 1.5_

  - [x] 1.3 Écrire le test property-based P1 — Grounding prompt présent dans tout contexte LLM
    - **Property 1 : Grounding prompt présent dans tout contexte LLM**
    - **Validates: Requirements 1.1**
    - Fichier : `backend/tests/test_rag_service.py`
    - Utiliser Hypothesis pour générer des requêtes variées et vérifier que le premier message `system` contient `GROUNDING_SYSTEM_PROMPT`

  - [x] 1.4 Écrire le test property-based P2 — Refus sans appel LLM quand aucun chunk ne passe le seuil
    - **Property 2 : Refus sans appel LLM quand aucun chunk ne passe le seuil**
    - **Validates: Requirements 1.2, 1.3**
    - Fichier : `backend/tests/test_rag_service.py`
    - Générer des ensembles de chunks avec scores < 0.75 et vérifier `answer == NO_CONTEXT_MESSAGE`, `sources == []`, et absence d'appel LLM

  - [x] 1.5 Écrire le test property-based P3 — Indépendance des champs title et source dans DocumentSource
    - **Property 3 : Indépendance des champs title et source dans DocumentSource**
    - **Validates: Requirements 1.4**
    - Fichier : `backend/tests/test_document_service.py`

  - [x] 1.6 Écrire le test property-based P4 — grounding_warning présent quand degraded_warning est actif
    - **Property 4 : grounding_warning présent quand degraded_warning est actif**
    - **Validates: Requirements 1.5**
    - Fichier : `backend/tests/test_rag_service.py`

- [x] 2. Checkpoint — Grounding
  - Vérifier que tous les tests de grounding passent, demander à l'utilisateur si des questions se posent.

- [x] 3. Multi-Agent Diagnostic via MCP
  - [x] 3.1 Créer `backend/services/mcp_host.py` avec `MCP_Host`
    - Implémenter `MCP_Host.run_diagnostic()` qui lance les quatre agents en parallèle via `asyncio.gather` avec timeout de 30 secondes par agent
    - Définir `SOURCE_FILTERS` pour chaque agent (`epidemiology`, `guideline`, `laboratory`, `protocol`)
    - Traiter un agent en timeout comme retournant zéro chunks grounded
    - Enregistrer les timeouts et omissions dans `DiagnosticAuditData`
    - _Requirements: 2.1, 2.2, 2.10, 2.12_

  - [x] 3.2 Créer les quatre agents spécialistes dans `backend/agents/`
    - Créer `epidemiology_agent.py` — lit stdin MCP, appelle `RAGService.query()` avec `source_filter={"metadata.document_type": "epidemiology"}`, écrit sur stdout
    - Créer `symptomatology_agent.py` — `source_filter={"metadata.document_type": "guideline"}`
    - Créer `lab_agent.py` — `source_filter={"metadata.document_type": "laboratory"}`
    - Créer `treatment_agent.py` — `source_filter={"metadata.document_type": {"$in": ["protocol", "guideline"]}}`
    - _Requirements: 2.3, 2.4, 2.5, 2.6, 2.11_

  - [x] 3.3 Créer `backend/agents/synthesis_agent.py` avec `Synthesis_Agent`
    - Fusionner les résultats des quatre agents en un `DiagnosticResult`
    - Garantir un minimum de 3 diagnostics différentiels (ajouter des entrées `confidence: low` si nécessaire)
    - Exclure les agents sans chunks grounded et enregistrer l'omission dans `DiagnosticAudit`
    - _Requirements: 2.7, 2.9_

  - [x] 3.4 Modifier `DiagnosticOrchestrator` dans `backend/services/diagnostic_service.py`
    - Déléguer à `MCP_Host` pour chaque appel à `get_differential_diagnosis`
    - Préserver l'interface publique `get_differential_diagnosis` pour les appelants existants
    - Écrire le `DiagnosticAudit` après chaque appel
    - _Requirements: 2.8_

  - [x] 3.5 Écrire le test property-based P5 — source_filter correct pour chaque agent spécialiste
    - **Property 5 : source_filter correct pour chaque agent spécialiste**
    - **Validates: Requirements 2.2, 2.3, 2.4, 2.5, 2.6**
    - Fichier : `backend/tests/test_mcp_host.py`

  - [x] 3.6 Écrire le test property-based P6 — Synthesis_Agent garantit au moins 3 diagnostics
    - **Property 6 : Synthesis_Agent garantit au moins 3 diagnostics différentiels**
    - **Validates: Requirements 2.7**
    - Fichier : `backend/tests/test_synthesis_agent.py`

  - [x] 3.7 Écrire le test property-based P7 — Agents sans chunks exclus de la synthèse
    - **Property 7 : Agents sans chunks exclus de la synthèse**
    - **Validates: Requirements 2.9**
    - Fichier : `backend/tests/test_synthesis_agent.py`

- [x] 4. Checkpoint — Multi-Agent MCP
  - Vérifier que tous les tests MCP passent, demander à l'utilisateur si des questions se posent.

- [x] 5. RAG Pipeline amélioré
  - [x] 5.1 Créer `backend/services/chunker.py` avec `Chunker` et `ChunkResult`
    - Implémenter la détection de frontières sémantiques : en-têtes de section (`SECTION_HEADER_RE`), étapes numérotées (`NUMBERED_STEP_RE`), lignes de tableau (pipe `|`)
    - Respecter la limite de 800 caractères par chunk ; split aux frontières de phrases si aucune règle ne s'applique
    - Retourner `ChunkResult(content, section)` avec `section` peuplé depuis l'en-tête de section ou la légende de tableau
    - _Requirements: 3.1, 3.2_

  - [x] 5.2 Étendre `DocumentService._index_chunks()` dans `backend/services/document_service.py`
    - Remplacer la fonction `chunk_text` actuelle par `Chunker.chunk()`
    - Calculer `disease_tags` via `DISEASE_KEYWORDS`, `document_type` et `evidence_level` via `infer_document_type(source)`
    - Charger le `CrossEncoder` (`cross-encoder/ms-marco-MiniLM-L-6-v2`) au démarrage comme singleton
    - _Requirements: 3.3, 3.6_

  - [x] 5.3 Implémenter la récupération hybride dans `RAGService.query()`
    - Combiner les résultats du vector search et du `BM25_Retriever` via `reciprocal_rank_fusion(k=60)`
    - Passer le résultat fusionné au `CrossEncoder` pour re-ranking
    - Inclure les 5 derniers messages de session comme contexte additionnel quand appelé depuis `ChatService`
    - Appliquer le filtre `region` depuis `request.state.region` (pas de filtre si `None` ou inconnu)
    - _Requirements: 3.4, 3.5, 3.7, 3.8, 3.9_

  - [x] 5.4 Écrire le test property-based P8 — Chunker respecte la taille maximale et les frontières sémantiques
    - **Property 8 : Chunker respecte la taille maximale et les frontières sémantiques**
    - **Validates: Requirements 3.1**
    - Fichier : `backend/tests/test_chunker.py`
    - Générer des textes variés avec Hypothesis et vérifier que chaque chunk a ≤ 800 caractères

  - [x] 5.5 Écrire le test property-based P9 — Préservation de l'en-tête de section dans metadata.section
    - **Property 9 : Préservation de l'en-tête de section dans metadata.section**
    - **Validates: Requirements 3.2**
    - Fichier : `backend/tests/test_chunker.py`

  - [x] 5.6 Écrire le test property-based P10 — Enrichissement correct des métadonnées selon la source
    - **Property 10 : Enrichissement correct des métadonnées selon la source**
    - **Validates: Requirements 3.3**
    - Fichier : `backend/tests/test_document_service.py`

  - [x] 5.7 Écrire le test property-based P11 — Reciprocal Rank Fusion produit un classement cohérent
    - **Property 11 : Reciprocal Rank Fusion produit un classement cohérent**
    - **Validates: Requirements 3.5**
    - Fichier : `backend/tests/test_rag_service.py`
    - Vérifier que le score de chaque chunk est la somme de `1 / (k + rank)` sur toutes les listes où il apparaît

- [x] 6. Checkpoint — RAG Pipeline
  - Vérifier que tous les tests RAG passent, demander à l'utilisateur si des questions se posent.

- [x] 7. Safety & Audit
  - [x] 7.1 Ajouter le calcul de `ConfidenceScore` dans `RAGService.query()`
    - Calculer la moyenne arithmétique des scores de similarité cosinus des chunks retenus
    - Inclure le résultat dans `RAGResponse.confidence_score`
    - _Requirements: 4.1_

  - [x] 7.2 Créer `backend/models/diagnostic_audit.py` avec `DiagnosticAudit` et `AgentAuditResult`
    - Définir `AgentAuditResult` : `agent_name`, `sub_question`, `chunk_ids`, `confidence_score`, `partial_differential`
    - Définir `DiagnosticAudit` avec tous les champs requis (timestamp, symptoms, patient_profile_hash, locale, region, confidence_score, diagnoses, fallback_used, degraded_warning, agent_results)
    - Calculer `patient_profile_hash` comme SHA-256 sur `age`, `weight`, `sex`, `comorbidities` uniquement (sans PII)
    - Créer l'index TTL de 2555 jours sur `timestamp` dans la collection `diagnostic_audit`
    - _Requirements: 4.3, 4.4, 4.8_

  - [x] 7.3 Intégrer l'écriture du `DiagnosticAudit` dans `DiagnosticOrchestrator`
    - Écrire un document `DiagnosticAudit` dans MongoDB après chaque appel à `get_differential_diagnosis`
    - Ajouter le disclaimer dans la réponse quand `fallback_used=True`
    - _Requirements: 4.2, 4.3_

  - [x] 7.4 Créer `backend/routers/feedback.py` avec `POST /api/v1/feedback/retrieval`
    - Valider le payload : `session_id`, `document_id`, `chunk_id`, `rating` (1 ou -1)
    - Stocker dans la collection `retrieval_feedback` avec `user_id` et `timestamp`
    - Restreindre l'accès aux rôles `admin`, `medecin`, `infirmière`
    - Enregistrer le router dans `main.py`
    - _Requirements: 4.6, 4.7_

  - [x] 7.5 Écrire le test property-based P12 — ConfidenceScore est la moyenne arithmétique des scores retenus
    - **Property 12 : ConfidenceScore est la moyenne arithmétique des scores retenus**
    - **Validates: Requirements 4.1**
    - Fichier : `backend/tests/test_rag_service.py`

  - [x] 7.6 Écrire le test property-based P13 — DiagnosticAudit écrit pour chaque appel diagnostique
    - **Property 13 : DiagnosticAudit écrit pour chaque appel diagnostique**
    - **Validates: Requirements 4.3, 4.4**
    - Fichier : `backend/tests/test_diagnostic_orchestrator.py`
    - Vérifier qu'exactement un document est inséré dans `diagnostic_audit` par appel

  - [x] 7.7 Écrire le test property-based P14 — Hash du profil patient exclut les champs PII
    - **Property 14 : Hash du profil patient exclut les champs PII**
    - **Validates: Requirements 4.3**
    - Fichier : `backend/tests/test_diagnostic_orchestrator.py`

  - [x] 7.8 Écrire le test property-based P15 — Feedback de récupération stocké avec tous les champs requis
    - **Property 15 : Feedback de récupération stocké avec tous les champs requis**
    - **Validates: Requirements 4.7**
    - Fichier : `backend/tests/test_feedback_router.py`

- [x] 8. Checkpoint — Safety & Audit
  - Vérifier que tous les tests d'audit passent, demander à l'utilisateur si des questions se posent.

- [x] 9. PDF Citation Popup
  - [x] 9.1 Étendre `DocumentService._extract_text_pdf()` pour extraire les BBox et offsets
    - Utiliser `pypdf` pour extraire `bbox`, `page_char_start`, `page_char_end` pour chaque chunk PDF
    - Stocker ces données dans `metadata.bbox`, `metadata.page_char_start`, `metadata.page_char_end` sur `DocumentChunk`
    - Ne pas tenter l'extraction BBox pour les fichiers non-PDF (DOCX, TXT, CSV)
    - _Requirements: 5.1, 5.8_

  - [x] 9.2 Étendre `DocumentSource` avec `HighlightInfo` et l'endpoint de vue
    - Créer `HighlightInfo(bbox: list[float], page: int)` dans `backend/models/`
    - Ajouter `highlight: HighlightInfo | None` dans `DocumentSource`, peuplé depuis `metadata.bbox` et `metadata.page`
    - Créer `GET /api/v1/documents/{id}/view` dans `backend/routers/documents.py` : retourner une URL S3 présignée valide 15 minutes
    - Retourner HTTP 404 si le document n'existe pas
    - Restreindre l'accès aux rôles `admin`, `medecin`, `infirmière`
    - _Requirements: 5.2, 5.3, 5.4_

  - [x] 9.3 Créer le composant `CitationChip` dans `apps/web/src/components/CitationChip.tsx`
    - Rendre `[N]` inline dans le texte de réponse (N = index 1-based dans `sources`)
    - Au clic, ouvrir `CitationPopup` avec la source correspondante
    - _Requirements: 5.5_

  - [x] 9.4 Créer le composant `CitationPopup` dans `apps/web/src/components/CitationPopup.tsx`
    - Récupérer l'URL présignée via `GET /api/v1/documents/{id}/view`
    - Rendre la page PDF via `react-pdf` et superposer un rectangle jaune aux coordonnées `highlight.bbox`
    - Afficher uniquement l'`excerpt` si `highlight` est absent
    - Fermer via Escape ou clic extérieur
    - _Requirements: 5.6, 5.7, 5.9_

  - [x] 9.5 Écrire le test property-based P16 — Extraction BBox et offsets pour tous les chunks PDF
    - **Property 16 : Extraction BBox et offsets pour tous les chunks PDF**
    - **Validates: Requirements 5.1**
    - Fichier : `backend/tests/test_document_service.py`
    - Vérifier que `metadata.bbox`, `metadata.page_char_start`, `metadata.page_char_end` sont non-null pour chaque chunk PDF

- [x] 10. Checkpoint — PDF Citation Popup
  - Vérifier que les tests backend passent et que le composant CitationPopup s'affiche correctement, demander à l'utilisateur si des questions se posent.

- [x] 11. Data Integrity & Migration
  - [x] 11.1 Ajouter la détection au démarrage dans `DocumentService`
    - Au démarrage, compter les chunks sans `metadata.disease_tags`, `metadata.document_type`, ou `metadata.evidence_level`
    - Logger un WARNING avec le compte (ne pas lancer de migration automatique)
    - _Requirements: 6.1_

  - [x] 11.2 Créer les endpoints admin dans `backend/routers/admin.py`
    - Implémenter `POST /api/v1/admin/migrate-chunks` : ré-enrichir les chunks non migrés par lots de 100 en arrière-plan
    - Implémenter `POST /api/v1/admin/reindex-document/{id}` : réingérer depuis S3 avec le nouveau `Chunker` et extraction BBox (PDF uniquement), supprimer les anciens chunks, insérer les nouveaux, mettre à jour `chunk_count`
    - Retourner HTTP 404 si le document n'existe pas pour `reindex-document`
    - Enregistrer le router dans `main.py`
    - _Requirements: 6.2, 6.3, 6.4, 6.5_

  - [x] 11.3 Préserver l'intégrité référentielle lors de la suppression de documents
    - Modifier `DELETE /api/v1/documents/{id}` pour conserver les enregistrements `diagnostic_audit` référençant les chunks supprimés (références tombstone)
    - _Requirements: 6.6_

  - [x] 11.4 Écrire le test property-based P17 — Migration par lots de 100 chunks maximum
    - **Property 17 : Migration par lots de 100 chunks maximum**
    - **Validates: Requirements 6.2**
    - Fichier : `backend/tests/test_admin_router.py`
    - Générer N chunks non migrés et vérifier que le traitement se fait en ⌈N/100⌉ lots

- [x] 12. Documentation — `docs/architecture.md`
  - [x] 12.1 Créer `docs/architecture.md` avec les diagrammes Mermaid requis
    - Diagramme du pipeline d'ingestion de documents (upload → extraction → chunking → enrichissement → embedding → S3 → MongoDB)
    - Diagramme du pipeline RAG (cache → embedding → récupération hybride → RRF → CrossEncoder → filtre seuil → grounding prompt → LLM → cache)
    - Diagramme de séquence du flux multi-agent (clinicien → Orchestrator → MCP_Host → 4 agents → Synthesis → Audit → résultat)
    - Diagramme de séquence du flux PDF Citation Popup (rendu → clic → URL présignée → PDF → highlight)
    - Section schéma MongoDB (document_chunks, medical_documents, chat_sessions, diagnostic_audit, retrieval_feedback)
    - Section nouveaux endpoints API avec méthode, chemin, rôles, corps de requête, forme de réponse
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7_

- [x] 13. Checkpoint final — Vérification complète
  - Vérifier que tous les tests passent (backend Python + frontend TypeScript), demander à l'utilisateur si des questions se posent.

## Notes

- Les tâches marquées `*` sont optionnelles et peuvent être ignorées pour un MVP rapide
- Chaque tâche référence les requirements spécifiques pour la traçabilité
- Les tests property-based utilisent **Hypothesis** (Python) avec `max_examples=100`
- Les tests unitaires et property-based sont complémentaires, pas redondants
- Les checkpoints permettent une validation incrémentale à chaque axe d'amélioration
