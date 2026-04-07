# Plan d'Implémentation : Diagnostic Guidé Multi-Agent

## Vue d'ensemble

Ce plan convertit la conception du pipeline MCP multi-agent en tâches de codage incrémentales. L'ordre suit les dépendances : infrastructure et configuration d'abord, puis les composants de base (serveurs MCP, MCP_Host refactoré), ensuite l'enrichissement des modèles et services existants, et enfin l'intégration et les tests. Chaque tâche référence les exigences et propriétés du document de conception.

## Tâches

- [x] 1. Configuration et infrastructure
  - [x] 1.1 Ajouter les URLs des agents dans `backend/core/config.py`
    - Ajouter les champs `AGENT_EPIDEMIOLOGY_URL`, `AGENT_SYMPTOMATOLOGY_URL`, `AGENT_LAB_URL`, `AGENT_TREATMENT_URL` à la classe `Settings` avec les valeurs par défaut Docker (ex. `http://agent-epidemiology:8001`)
    - _Exigences : 2.1, 14.3_

  - [x] 1.2 Étendre le modèle `Consultation` avec les champs MCP dans `backend/models/consultation.py`
    - Ajouter les modèles Pydantic `EvidenceCitation` et `AgentContribution`
    - Ajouter les champs `mcp_session_id: str | None = None`, `agent_contributions: list[AgentContribution] = []`, `evidence_citations: list[EvidenceCitation] = []` au modèle `Consultation`
    - _Exigences : 11.5, 11.6, 11.7_

  - [x] 1.3 Étendre `DiagnosticResult` dans `backend/services/diagnostic_service.py`
    - Ajouter les champs `session_id`, `confidence_score`, `evidence_citations`, `agent_contributions` au dataclass `DiagnosticResult`
    - _Exigences : 5.7, 5.8, 6.3_

  - [x] 1.4 Ajouter `fallback_used` au dataclass `AgentResult` dans `backend/services/mcp_host.py`
    - Ajouter le champ `fallback_used: bool = False` au dataclass `AgentResult` existant
    - _Exigences : 4.7, 8.3_

- [x] 2. Checkpoint — Vérifier que les modèles étendus compilent
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Serveurs MCP spécialistes
  - [x] 3.1 Créer la classe de base `BaseMCPServer` dans `backend/agents/mcp_servers/base_server.py`
    - Créer le répertoire `backend/agents/mcp_servers/` avec `__init__.py`
    - Implémenter `BaseMCPServer` avec : routes FastAPI `POST /rpc` et `GET /health`, dispatch JSON-RPC 2.0 (`tools/list`, `tools/call`, `resources/list`, `resources/read`, `prompts/list`, `prompts/get`), réponse SSE via `EventSourceResponse`, méthodes `register_tool()`, `register_resource()`, `register_prompt()`
    - _Exigences : 1.7, 3.1, 3.2, 3.3, 14.2_

  - [x] 3.2 Implémenter `EpidemiologyMCPServer` dans `backend/agents/mcp_servers/epidemiology_server.py`
    - Hériter de `BaseMCPServer`, enregistrer le tool `query_epidemiology`, la resource `epidemiology://documents`, le prompt `epidemiology_query`
    - Implémenter le handler du tool avec `LlamaIndexPipeline` et le `source_filter` épidémiologique
    - Instancier sa propre connexion MongoDB, `EmbeddingModel`, `IndexManager`, `LlamaIndexPipeline`
    - Retourner un `AgentResult` sérialisé en JSON-RPC 2.0 via SSE
    - _Exigences : 1.1, 1.5, 1.6, 4.1, 4.5, 4.6, 4.7, 4.8, 9.2_

  - [x] 3.3 Implémenter `SymptomatologyMCPServer` dans `backend/agents/mcp_servers/symptomatology_server.py`
    - Même structure que 3.2 avec tool `query_symptomatology`, resource `guidelines://documents`, prompt `symptomatology_query`
    - _Exigences : 1.2, 1.5, 1.6, 4.2, 4.5, 4.6, 4.7, 4.8_

  - [x] 3.4 Implémenter `LabMCPServer` dans `backend/agents/mcp_servers/lab_server.py`
    - Même structure que 3.2 avec tool `query_lab`, resource `laboratory://documents`, prompt `lab_query`
    - _Exigences : 1.3, 1.5, 1.6, 4.3, 4.5, 4.6, 4.7, 4.8_

  - [x] 3.5 Implémenter `TreatmentMCPServer` dans `backend/agents/mcp_servers/treatment_server.py`
    - Même structure que 3.2 avec tool `query_treatment`, resource `protocols://documents`, prompt `treatment_query`
    - _Exigences : 1.4, 1.5, 1.6, 4.4, 4.5, 4.6, 4.7, 4.8, 9.3_

  - [x] 3.6 Créer le Dockerfile commun pour les serveurs agents dans `backend/agents/mcp_servers/Dockerfile`
    - Dockerfile basé sur Python 3.12, installer les dépendances, exposer le port via `SERVER_PORT`
    - _Exigences : 14.5, 14.6_

  - [x] 3.7 Écrire les tests unitaires pour `BaseMCPServer`
    - Tester le dispatch JSON-RPC 2.0 (tools/list, resources/list, prompts/list, tools/call, resources/read, prompts/get)
    - Tester les réponses SSE et les codes d'erreur JSON-RPC 2.0 (-32700, -32600, -32601, -32602, -32603)
    - _Exigences : 1.7, 3.2, 3.5_

  - [x] 3.8 Écrire le test property-based pour la sérialisation round-trip des payloads MCP
    - **Propriété 1 : Aller-retour de sérialisation JSON des payloads MCP**
    - **Valide : Exigence 3.4**

  - [x] 3.9 Écrire le test property-based pour la validité structurelle des requêtes JSON-RPC 2.0
    - **Propriété 2 : Validité structurelle des requêtes JSON-RPC 2.0**
    - **Valide : Exigences 2.4, 3.1**

  - [x] 3.10 Écrire le test property-based pour l'invariant structurel des AgentResult
    - **Propriété 5 : Invariant structurel des AgentResult**
    - **Valide : Exigences 4.5, 4.6**

- [x] 4. Checkpoint — Vérifier que les serveurs MCP démarrent et répondent aux requêtes de découverte
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Refactoring du MCP_Host
  - [x] 5.1 Refactorer `MCP_Host` dans `backend/services/mcp_host.py` pour HTTP+SSE
    - Supprimer le code obsolète : `_AGENT_SCRIPTS`, `_build_sub_question()`, `SOURCE_FILTERS`, `_call_agent()` (subprocess)
    - Remplacer par : `httpx.AsyncClient` avec pool de connexions, `_AGENT_URLS` lues depuis `settings`, dataclasses `MCPCapabilities` et `MCPRequest`
    - Implémenter `_check_agent_health()` (GET /health), `_send_rpc()` (POST /rpc + parse SSE), `_discover_capabilities()` (tools/list, resources/list, prompts/list avec cache), `shutdown()` (fermeture du client HTTP)
    - Implémenter `run_diagnostic()` : health check → découverte (si pas en cache) → invocation tools/call en parallèle via `asyncio.gather` → collecte des `AgentResult` → construction de `DiagnosticAuditData`
    - Timeout de 30s par agent couvrant l'ensemble du cycle (découverte + invocation)
    - Invalidation du cache quand un serveur est injoignable
    - _Exigences : 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 3.1, 3.5, 3.6, 9.1, 14.1, 14.3, 14.4, 15.3_

  - [x] 5.2 Écrire le test property-based pour l'idempotence du cache de découverte
    - **Propriété 3 : Idempotence du cache de découverte des primitives**
    - **Valide : Exigences 2.2, 2.3, 2.4**

  - [x] 5.3 Écrire le test property-based pour les agents en erreur marqués comme omis
    - **Propriété 4 : Agents en erreur marqués comme omis**
    - **Valide : Exigences 2.9, 3.6**

  - [x] 5.4 Écrire le test property-based pour le passthrough de la Locale
    - **Propriété 13 : Passthrough de la Locale sans transformation**
    - **Valide : Exigences 9.1, 9.4, 9.5**

  - [x] 5.5 Écrire le test property-based pour l'exécution parallèle des agents
    - **Propriété 17 : Exécution parallèle des agents (structurelle)**
    - **Valide : Exigence 15.3**

  - [x] 5.6 Écrire les tests unitaires pour le MCP_Host refactoré
    - Tester le health check, le timeout 30s, l'agent HTTP injoignable, l'invalidation du cache, la gestion des erreurs JSON-RPC 2.0
    - _Exigences : 2.7, 2.8, 2.9, 2.10, 3.5, 3.6, 14.1_

- [x] 6. Checkpoint — Vérifier que le MCP_Host communique avec les serveurs agents via HTTP+SSE
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Enrichissement du Synthesis_Agent
  - [x] 7.1 Enrichir `Synthesis_Agent` dans `backend/agents/synthesis_agent.py`
    - Ajouter `_compute_weighted_confidence()` : moyenne pondérée `sum(score_i × len(chunks_i)) / sum(len(chunks_i))`
    - Ajouter `_build_evidence_citations()` : associer les chunks des agents actifs aux diagnostics fusionnés comme `EvidenceCitation`
    - Ajouter `_build_agent_contributions()` : construire la liste des `AgentContribution` à partir des `AgentResult`
    - Modifier `synthesize()` pour retourner `confidence_score`, `evidence_citations`, `agent_contributions` dans le `DiagnosticResult`
    - Gérer le champ `fallback_used` des `AgentResult` pour déterminer le `fallback_used` global
    - _Exigences : 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 8.1, 8.2, 8.3_

  - [x] 7.2 Écrire le test property-based pour la déduplication par probabilité maximale
    - **Propriété 6 : Déduplication par probabilité maximale**
    - **Valide : Exigence 5.2**

  - [x] 7.3 Écrire le test property-based pour le tri des diagnostics par probabilité décroissante
    - **Propriété 7 : Tri des diagnostics par probabilité décroissante**
    - **Valide : Exigence 5.3**

  - [x] 7.4 Écrire le test property-based pour la garantie de minimum 3 diagnostics
    - **Propriété 8 : Garantie de minimum 3 diagnostics**
    - **Valide : Exigence 5.4**

  - [x] 7.5 Écrire le test property-based pour les citations de preuves
    - **Propriété 9 : Citations de preuves associées à chaque diagnostic non-placeholder**
    - **Valide : Exigence 5.7**

  - [x] 7.6 Écrire le test property-based pour le score de confiance pondéré
    - **Propriété 10 : Score de confiance pondéré par chunks**
    - **Valide : Exigence 5.8**

  - [x] 7.7 Écrire le test property-based pour le disclaimer fallback
    - **Propriété 11 : Disclaimer ajouté lors du fallback LLM**
    - **Valide : Exigences 4.7, 6.2, 8.3**

- [x] 8. Intégration dans le DiagnosticOrchestrator et les endpoints
  - [x] 8.1 Enrichir `DiagnosticOrchestrator._get_diagnosis_via_mcp()` dans `backend/services/diagnostic_service.py`
    - Générer un `mcp_session_id` (UUID) par session
    - Journaliser `duration_ms` pour chaque session
    - Propager `user_id` via un paramètre optionnel dans `get_differential_diagnosis()`
    - Appeler `_create_mcp_consultation()` pour auto-créer la `Consultation` (best-effort)
    - Assigner `result.session_id = mcp_session_id`
    - Gérer le `fallback_used` depuis les `AgentResult` pour ajouter le disclaimer
    - _Exigences : 6.1, 6.2, 6.3, 7.1, 7.2, 7.3, 11.1, 11.2, 11.3, 11.4, 11.8, 11.11, 15.4_

  - [x] 8.2 Mettre à jour `_doc_to_consultation()` dans `backend/services/consultation_service.py`
    - Ajouter la lecture des champs `mcp_session_id`, `agent_contributions`, `evidence_citations` depuis le document MongoDB
    - _Exigences : 11.5, 11.6, 11.7_

  - [x] 8.3 Ajouter `list_my_consultations()` dans `backend/services/consultation_service.py`
    - Implémenter la méthode avec pagination (`page`, `page_size`), tri par `created_at` décroissant, filtre par `user_id`
    - _Exigences : 11.10_

  - [x] 8.4 Créer le endpoint `GET /api/v1/consultations/me`
    - Créer le router `backend/routers/consultations.py` avec le endpoint paginé
    - Appliquer `require_role(["admin", "medecin", "infirmière"])` et rate limit 30/min
    - Retourner `PaginatedResponse[Consultation]`
    - Enregistrer le router dans `backend/main.py` avec le préfixe `/api/v1`
    - _Exigences : 10.4, 10.5, 11.10_

  - [x] 8.5 Mettre à jour le endpoint `POST /api/v1/diagnose/symptoms` dans `backend/routers/diagnose.py`
    - Passer `user_id=str(current_user["_id"])` à `diagnostic_service.get_differential_diagnosis()`
    - Inclure `mcp_session_id` dans la réponse `DiagnoseResponse` si disponible
    - _Exigences : 6.3, 6.4, 11.2_

  - [x] 8.6 Mettre à jour le lifespan dans `backend/main.py` pour initialiser le MCP_Host
    - Instancier `MCP_Host` et le passer au `DiagnosticService`
    - Appeler `mcp_host.shutdown()` lors du teardown
    - _Exigences : 14.3, 14.4_

  - [x] 8.7 Écrire le test property-based pour le champ warnings_present
    - **Propriété 12 : Champ warnings_present dérivé correctement**
    - **Valide : Exigence 8.4**

  - [x] 8.8 Écrire le test property-based pour l'intégrité structurelle des Consultations MCP
    - **Propriété 14 : Intégrité structurelle des Consultations MCP**
    - **Valide : Exigences 11.2, 11.5, 11.6, 11.7, 11.8**

  - [x] 8.9 Écrire le test property-based pour le tri de l'historique des consultations
    - **Propriété 15 : Historique des consultations trié par date décroissante**
    - **Valide : Exigence 11.10**

  - [x] 8.10 Écrire les tests unitaires pour les endpoints et l'orchestrateur
    - Tester l'accès avec rôle `infirmière` aux endpoints diagnose et consultations/me
    - Tester l'accès admin refusé pour `infirmière` (HTTP 403)
    - Tester la consultation auto-créée avec et sans `patient_id`
    - Tester que l'échec d'écriture audit/consultation ne bloque pas la requête
    - _Exigences : 7.3, 10.1, 10.2, 11.3, 11.4, 11.11, 13.2, 13.3_

- [x] 9. Checkpoint — Vérifier l'intégration complète du pipeline MCP
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Migration et Docker Compose
  - [x] 10.1 Créer le script de migration `backend/scripts/migrate_consultations_add_mcp_fields.py`
    - Implémenter `migrate()` : ajouter `mcp_session_id=None`, `agent_contributions=[]`, `evidence_citations=[]` aux documents sans ces champs (`$exists: False`)
    - Implémenter `create_indexes()` : index sparse sur `mcp_session_id`, index composé `{user_id: 1, created_at: -1}` sur `consultations`, index composé `{user_id: 1, patient_id: 1, created_at: -1}` sur `diagnostic_audit`
    - Implémenter `rollback()` : supprimer les champs sur les documents où `mcp_session_id` est null, supprimer les 3 index
    - Supporter `--rollback` via `argparse` ou `sys.argv`
    - Journaliser le nombre de documents mis à jour et d'index créés
    - Suivre le pattern existant de `migrate_protocols_add_region.py`
    - _Exigences : 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7, 12.8, 12.9, 12.10_

  - [x] 10.2 Écrire le test property-based pour l'idempotence de la migration
    - **Propriété 16 : Idempotence de la migration et préservation des champs**
    - **Valide : Exigences 12.5, 12.6**

  - [x] 10.3 Ajouter les 4 services agents dans `docker-compose.yml`
    - Ajouter les services `agent-epidemiology` (:8001), `agent-symptomatology` (:8002), `agent-lab` (:8003), `agent-treatment` (:8004) avec health checks sur `GET /health`
    - Ajouter les variables d'environnement `AGENT_*_URL` au service `backend`
    - Ajouter les dépendances `depends_on` du backend vers les 4 agents
    - _Exigences : 14.5, 14.6_

- [x] 11. Checkpoint final backend — Vérifier le pipeline complet
  - Ensure all tests pass, ask the user if questions arise.

- [x] 12. Intégration Frontend — Types partagés et API client
  - [x] 12.1 Ajouter `EvidenceCitationSchema` et `AgentContributionSchema` dans `packages/types/index.ts`
    - Créer le schéma Zod `EvidenceCitationSchema` avec les champs `documentId`, `title`, `source`, `excerpt`, `page`
    - Créer le schéma Zod `AgentContributionSchema` avec les champs `agentName`, `confidenceScore`, `partialDifferential`
    - Exporter les types TypeScript correspondants
    - _Exigences : 16.7_

  - [x] 12.2 Étendre `ConsultationSchema` dans `packages/types/index.ts`
    - Ajouter les champs `mcpSessionId` (string optionnel), `agentContributions` (liste de `AgentContributionSchema`), `evidenceCitations` (liste de `EvidenceCitationSchema`)
    - Utiliser `.optional().default([])` pour la compatibilité ascendante
    - _Exigences : 16.6_

  - [x] 12.3 Mettre à jour `DiagnosisResponse` et `DiagnosisResponseSchema` dans `packages/api-client/index.ts`
    - Ajouter les champs `fallbackWarning`, `degradedWarning`, `warningsPresent`, `confidenceScore`, `agentContributions`, `evidenceCitations` à l'interface et au schéma Zod
    - Utiliser `.optional().default()` pour les champs optionnels afin de ne pas casser les réponses existantes
    - _Exigences : 16.5_

  - [x] 12.4 Ajouter la méthode `listMyConsultations()` dans l'API client (`packages/api-client/index.ts`)
    - Ajouter dans le namespace `diagnose` : `listMyConsultations(page, pageSize, signal)` appelant `GET /api/v1/consultations/me`
    - Retourner `PaginatedResponse<Consultation>`
    - _Exigences : 16.8_

- [x] 13. Intégration Frontend — Page de diagnostic et historique
  - [x] 13.1 Mettre à jour la page DiagnosePage (`apps/web/src/app/[locale]/diagnose/page.tsx`)
    - Ajouter les bandeaux d'avertissement (`fallbackWarning`, `degradedWarning`) quand `warningsPresent` est `true`
    - Ajouter l'affichage du score de confiance global en pourcentage
    - Ajouter l'affichage des citations de preuves par diagnostic (titre, source, extrait, page)
    - Ajouter la section des contributions des agents (nom de l'agent, score de confiance)
    - Ajouter un lien/bouton vers la page d'historique des diagnostics
    - _Exigences : 16.1, 16.2, 16.3, 16.4, 16.11_

  - [x] 13.2 Créer la page d'historique des diagnostics (`apps/web/src/app/[locale]/diagnose/history/page.tsx`)
    - Appeler `apiClient.diagnose.listMyConsultations()` pour récupérer l'historique paginé
    - Afficher la liste avec : date, résumé des symptômes, diagnostic principal, score de confiance
    - Implémenter la pagination (boutons Précédent/Suivant)
    - Ajouter un lien vers les détails complets de chaque consultation
    - _Exigences : 16.8, 16.9_

  - [x] 13.3 Ajouter les clés i18n dans les fichiers de traduction
    - Ajouter les clés dans `packages/i18n/locales/fr.json` : `diagnose.fallbackWarning`, `diagnose.degradedWarning`, `diagnose.confidenceScore`, `diagnose.agentContributions`, `diagnose.agentName`, `diagnose.agentConfidence`, `diagnose.evidenceCitations`, `diagnose.citationTitle`, `diagnose.citationSource`, `diagnose.citationExcerpt`, `diagnose.citationPage`, `diagnose.history.*`
    - Ajouter les clés correspondantes en anglais dans `packages/i18n/locales/en.json`
    - _Exigences : 16.10_

  - [x] 13.4 Écrire les tests frontend (Vitest) pour les composants mis à jour
    - Tester l'affichage des bandeaux d'avertissement quand `warningsPresent` est `true`
    - Tester l'affichage du score de confiance
    - Tester l'affichage des citations de preuves
    - Tester l'affichage des contributions des agents
    - Tester la page d'historique avec données paginées mockées
    - _Exigences : 16.1, 16.2, 16.3, 16.4, 16.8, 16.9_

- [x] 14. Checkpoint — Vérifier l'intégration complète frontend + backend
  - Ensure all tests pass, ask the user if questions arise.

- [x] 15. Documentation
  - [x] 15.1 Mettre à jour `docs/api-reference.md` avec les endpoints MCP et les nouveaux schémas de réponse
    - Ajouter la section « Serveurs MCP — Endpoints JSON-RPC 2.0 » (`POST /rpc`, `GET /health`)
    - Documenter le schéma de réponse enrichi de `POST /api/v1/diagnose/symptoms` (champs `mcp_session_id`, `confidence_score`, `agent_contributions`, `evidence_citations`, `fallback_warning`, `degraded_warning`, `warnings_present`)
    - Documenter le endpoint `GET /api/v1/consultations/me` (paramètres, rôles, rate limit, réponse paginée)
    - _Exigences : 17.1_

  - [x] 15.2 Mettre à jour `docs/architecture.md` avec l'architecture MCP multi-agent
    - Ajouter un diagramme mermaid montrant les 4 serveurs MCP Docker, le MCP_Host, le Synthesis_Agent et les flux HTTP+SSE
    - Décrire chaque serveur agent (port, tool, resource URI, prompt)
    - Documenter le flux de communication MCP_Host et le pipeline du Synthesis_Agent
    - _Exigences : 17.2_

  - [x] 15.3 Mettre à jour `docs/developer-guide.md` avec le guide de développement MCP
    - Ajouter la section « Développement de serveurs MCP » : créer un serveur en héritant de `BaseMCPServer`, enregistrer les primitives, exécuter localement, tester avec curl
    - Mettre à jour la section « Ajout d'un nouvel agent » pour refléter l'architecture MCP
    - _Exigences : 17.3_

  - [x] 15.4 Mettre à jour `docs/configuration.md` avec les variables d'environnement des agents
    - Ajouter la section « Serveurs MCP Agents » avec `AGENT_EPIDEMIOLOGY_URL`, `AGENT_SYMPTOMATOLOGY_URL`, `AGENT_LAB_URL`, `AGENT_TREATMENT_URL`
    - Ajouter une note sur l'utilisation de `LLAMAINDEX_SIMILARITY_THRESHOLD` par les agents
    - _Exigences : 17.4_

  - [x] 15.5 Mettre à jour `docs/deployment.md` avec les services Docker Compose des agents
    - Ajouter les 4 services agents dans le tableau des services
    - Documenter la configuration des health checks et les considérations de scaling
    - _Exigences : 17.5_

  - [x] 15.6 Mettre à jour `README.md` avec l'architecture MCP multi-agent
    - Ajouter MCP dans « Stack technique », `backend/agents/mcp_servers/` dans « Structure du projet »
    - Ajouter les 4 services agents dans le tableau « Accéder aux services »
    - Ajouter le script de migration dans « Démarrage rapide »
    - Ajouter `GET /api/v1/consultations/me` dans « API — Endpoints principaux »
    - _Exigences : 17.6_

  - [x] 15.7 Ajouter les docstrings de module aux fichiers de serveurs MCP
    - Ajouter un docstring de module à `base_server.py`, `epidemiology_server.py`, `symptomatology_server.py`, `lab_server.py`, `treatment_server.py`
    - Chaque docstring doit décrire l'objectif du serveur, les primitives exposées (tools, resources, prompts) et la configuration requise
    - _Exigences : 17.7_

- [x] 16. Checkpoint final — Vérifier la documentation et l'intégration complète
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Les tâches marquées avec `*` sont optionnelles et peuvent être ignorées pour un MVP plus rapide
- Chaque tâche référence les exigences spécifiques pour la traçabilité
- Les checkpoints permettent une validation incrémentale
- Les tests property-based valident les 17 propriétés de correction du document de conception (Hypothesis, min 100 itérations)
- Les tests unitaires valident les cas spécifiques et les cas limites
- Le backend est en Python 3.12 avec FastAPI, Motor (async MongoDB), httpx, et Hypothesis
- Le frontend est en TypeScript/Next.js avec Zod, next-intl, et Vitest pour les tests
- Les tâches 12–13 couvrent l'intégration frontend (Exigence 16) : types partagés, API client, page de diagnostic enrichie, historique des diagnostics, et clés i18n
- La tâche 15 couvre la documentation (Exigence 17) : mise à jour de la référence API, de l'architecture, du guide développeur, de la configuration, du déploiement, du README et des docstrings des serveurs MCP
