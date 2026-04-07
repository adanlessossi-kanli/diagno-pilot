# Document d'Exigences — Diagnostic Guidé Multi-Agent

## Introduction

Le mode « Diagnostic Guidé Multi-Agent » formalise et enrichit le pipeline de diagnostic différentiel de Diagno-Pilot en exploitant pleinement l'architecture MCP (Model Context Protocol) standard. Chaque agent spécialiste est un serveur MCP HTTP exposant trois primitives standard : **Tools** (outils invocables), **Resources** (bases de connaissances consultables) et **Prompts** (templates de requêtes spécialisées). Le MCP_Host agit comme client/hôte MCP qui découvre et invoque ces primitives via le transport HTTP+SSE (requêtes JSON-RPC 2.0 envoyées par HTTP POST, réponses streamées via Server-Sent Events).

Chaque serveur MCP spécialiste est déployé comme un service Docker indépendant (FastAPI/Starlette) exposant un endpoint `/rpc` pour les requêtes JSON-RPC 2.0 et un endpoint `/health` pour les vérifications de disponibilité. Le MCP_Host communique avec ces services via HTTP POST et reçoit les réponses via SSE.

Le flux complet part de la requête du praticien, traverse quatre serveurs MCP spécialistes appelés en parallèle via des requêtes HTTP concurrentes (Épidémiologie, Symptomatologie, Laboratoire, Traitement), passe par un Agent de Synthèse qui fusionne les résultats avec citations de preuves, et retourne une réponse diagnostique structurée avec diagnostics classés, preuves sourcées et recommandations thérapeutiques.

Ce document couvre : l'orchestration MCP standard, les primitives MCP (tools, resources, prompts), la qualité des résultats agents, la synthèse avec citations, la traçabilité, la gestion des erreurs et la réponse finale au praticien.

## Glossaire

- **MCP** : Model Context Protocol — protocole standard définissant trois primitives (Tools, Resources, Prompts) pour la communication entre un hôte et des serveurs spécialistes, transportées via JSON-RPC 2.0 sur HTTP+SSE.
- **MCP_Host** : Client/hôte MCP qui découvre les primitives (tools, resources, prompts) exposées par chaque serveur MCP spécialiste, les invoque via JSON-RPC 2.0 sur transport HTTP+SSE (HTTP POST vers `/rpc` pour les requêtes, SSE pour les réponses), et coordonne les quatre agents en parallèle via des requêtes HTTP concurrentes. Implémenté dans `backend/services/mcp_host.py`.
- **MCP_Server** : Service Docker HTTP (FastAPI/Starlette) exposant les trois primitives standard (Tools, Resources, Prompts) via un endpoint `/rpc` acceptant des requêtes JSON-RPC 2.0 par HTTP POST et retournant les réponses via SSE.
- **MCP_Tool** : Primitive MCP de type « tool » — fonction invocable exposée par un serveur MCP, identifiée par un nom unique et un schéma JSON d'entrée/sortie (ex. `query_epidemiology`, `query_symptomatology`, `query_lab`, `query_treatment`).
- **MCP_Resource** : Primitive MCP de type « resource » — source de données consultable exposée par un serveur MCP, identifiée par un URI (ex. collections de documents, bases de connaissances épidémiologiques, guidelines cliniques).
- **MCP_Prompt** : Primitive MCP de type « prompt » — template de requête exposé par un serveur MCP, définissant comment formuler les questions pour un domaine spécialiste donné, avec paramètres typés.
- **JSON-RPC 2.0** : Protocole de communication utilisé pour les messages MCP, avec les champs standard `jsonrpc`, `method`, `params`, `id`, `result`, `error`.
- **Transport_SSE** : Mécanisme de transport MCP standard où les requêtes JSON-RPC 2.0 sont envoyées via HTTP POST et les réponses sont streamées via Server-Sent Events (SSE).
- **Agent_Épidémiologie** : Serveur MCP spécialiste exposant le tool `query_epidemiology`, des resources de données épidémiologiques et des prompts pour formuler les requêtes épidémiologiques.
- **Agent_Symptomatologie** : Serveur MCP spécialiste exposant le tool `query_symptomatology`, des resources de guidelines cliniques et des prompts pour formuler les requêtes symptomatologiques.
- **Agent_Laboratoire** : Serveur MCP spécialiste exposant le tool `query_lab`, des resources de données de laboratoire et des prompts pour formuler les requêtes de laboratoire.
- **Agent_Traitement** : Serveur MCP spécialiste exposant le tool `query_treatment`, des resources de protocoles thérapeutiques et des prompts pour formuler les requêtes de traitement.
- **Agent_Synthèse** : Agent qui fusionne les résultats des quatre agents spécialistes en un diagnostic différentiel consolidé avec citations de preuves. Implémenté dans `backend/agents/synthesis_agent.py`.
- **DiagnosticOrchestrator** : Orchestrateur mince qui dispatche vers le chemin MCP, AgentPipeline ou RAG. Implémenté dans `backend/services/diagnostic_service.py`.
- **DiagnosticResult** : Structure de retour contenant les diagnostics, indicateur de fallback, avertissements de dégradation, locale et disclaimer.
- **DiagnosticAuditData** : Métadonnées d'audit collectées pendant une exécution diagnostique (timeouts, omissions, résultats agents).
- **AgentResult** : Résultat produit par un agent spécialiste unique (sous-question, chunks, score de confiance, diagnostic partiel).
- **Chunk_Grounded** : Fragment de document récupéré par recherche vectorielle, servant de preuve sourcée pour un diagnostic.
- **Citation_Preuve** : Référence structurée à un Chunk_Grounded incluant document_id, titre, source, extrait et page.
- **Score_Confiance** : Valeur numérique entre 0.0 et 1.0 représentant le degré de certitude d'un diagnostic.
- **Praticien** : Utilisateur authentifié avec le rôle `medecin` ou `infirmière` utilisant le mode diagnostic guidé.
- **Locale** : Chaîne BCP-47 identifiant la langue et la région (ex. `fr-TG`, `fr-BJ`, `en`).
- **Région** : Code pays ISO 3166-1 alpha-2 (ex. `TG`, `BJ`) utilisé pour filtrer les données épidémiologiques et protocoles locaux.
- **Consultation** : Document MongoDB dans la collection `consultations` représentant une session diagnostique persistée, liée à un Praticien (user_id) et optionnellement à un patient (patient_id). Modèle défini dans `backend/models/consultation.py`.
- **MCP_Session_ID** : Identifiant unique de la session diagnostique MCP, permettant de relier une Consultation aux résultats des agents spécialistes.
- **Agent_Contributions** : Liste structurée des contributions de chaque agent spécialiste à une session diagnostique, incluant le nom de l'agent, son Score_Confiance et ses diagnostics partiels.
- **Evidence_Citations** : Liste de Citation_Preuve associées à une Consultation, traçant les sources documentaires utilisées par les agents pour produire le diagnostic.
- **Script_Migration** : Script Python idempotent dans `backend/scripts/` qui modifie le schéma ou les index d'une collection MongoDB, exécutable manuellement via `python -m`.

## Exigences

### Exigence 1 : Serveurs MCP spécialistes — Exposition des primitives standard

**User Story :** En tant que développeur, je veux que chaque agent spécialiste soit un serveur MCP standard exposant tools, resources et prompts, afin de garantir l'interopérabilité et la conformité au protocole MCP.

#### Critères d'acceptation

1. THE Agent_Épidémiologie SHALL exposer un MCP_Tool nommé `query_epidemiology` avec un schéma JSON d'entrée acceptant les paramètres `symptoms`, `patient_profile`, `locale` et `region`.
2. THE Agent_Symptomatologie SHALL exposer un MCP_Tool nommé `query_symptomatology` avec un schéma JSON d'entrée acceptant les paramètres `symptoms`, `patient_profile`, `locale` et `region`.
3. THE Agent_Laboratoire SHALL exposer un MCP_Tool nommé `query_lab` avec un schéma JSON d'entrée acceptant les paramètres `symptoms`, `patient_profile`, `locale` et `region`.
4. THE Agent_Traitement SHALL exposer un MCP_Tool nommé `query_treatment` avec un schéma JSON d'entrée acceptant les paramètres `symptoms`, `patient_profile`, `locale` et `region`.
5. THE chaque serveur MCP spécialiste SHALL exposer au moins une MCP_Resource identifiée par un URI unique représentant sa collection de documents spécialisée (ex. `epidemiology://documents`, `guidelines://documents`, `laboratory://documents`, `protocols://documents`).
6. THE chaque serveur MCP spécialiste SHALL exposer au moins un MCP_Prompt définissant le template de requête pour son domaine, avec des paramètres typés pour les symptômes, le profil patient, la Locale et la Région.
7. THE chaque serveur MCP spécialiste SHALL répondre aux méthodes de découverte MCP standard `tools/list`, `resources/list` et `prompts/list` en retournant la liste de ses primitives disponibles.

### Exigence 2 : Orchestration MCP — Découverte et invocation des primitives

**User Story :** En tant que Praticien, je veux que ma requête diagnostique soit traitée simultanément par quatre serveurs MCP spécialistes, afin d'obtenir un diagnostic différentiel complet couvrant épidémiologie, symptomatologie, laboratoire et traitement.

#### Critères d'acceptation

1. WHEN le Praticien soumet une liste de symptômes via le endpoint `/api/v1/diagnose/symptoms`, THE MCP_Host SHALL lancer les requêtes vers les quatre serveurs MCP spécialistes (Agent_Épidémiologie, Agent_Symptomatologie, Agent_Laboratoire, Agent_Traitement) en parallèle via Transport_SSE (HTTP POST vers `/rpc` + réponses SSE).
2. WHEN un serveur MCP spécialiste est contacté pour la première fois, THE MCP_Host SHALL découvrir les primitives disponibles en envoyant les requêtes JSON-RPC 2.0 `tools/list`, `resources/list` et `prompts/list` via HTTP POST vers l'endpoint `/rpc` du serveur, puis mettre en cache les primitives découvertes pour ce serveur.
3. WHEN le MCP_Host a déjà découvert les primitives d'un serveur MCP spécialiste, THE MCP_Host SHALL utiliser les primitives en cache sans renvoyer les requêtes de découverte.
4. WHEN un serveur MCP spécialiste HTTP est injoignable (connexion refusée, erreur DNS, timeout de connexion), THE MCP_Host SHALL invalider le cache des primitives pour ce serveur et tenter une redécouverte lors de la prochaine session.
5. THE MCP_Host SHALL invoquer le MCP_Tool approprié sur chaque serveur spécialiste via une requête JSON-RPC 2.0 `tools/call` envoyée par HTTP POST vers l'endpoint `/rpc`, contenant le nom du tool et les arguments structurés.
6. THE MCP_Host SHALL lire les MCP_Resources pertinentes de chaque serveur spécialiste via une requête JSON-RPC 2.0 `resources/read` envoyée par HTTP POST vers l'endpoint `/rpc` pour obtenir le contexte documentaire.
7. THE MCP_Host SHALL utiliser les MCP_Prompts exposés par chaque serveur spécialiste via une requête JSON-RPC 2.0 `prompts/get` envoyée par HTTP POST vers l'endpoint `/rpc` pour formuler les sous-questions adaptées à chaque domaine.
8. THE MCP_Host SHALL appliquer un timeout de 30 secondes par serveur MCP spécialiste, couvrant l'ensemble du cycle requête HTTP POST + réponse SSE (découverte, lecture de resources, récupération de prompts et invocation du tool).
9. WHEN un serveur MCP spécialiste dépasse le timeout de 30 secondes, THE MCP_Host SHALL annuler la requête HTTP et fermer la connexion SSE vers ce serveur, et enregistrer le timeout dans DiagnosticAuditData.
10. WHEN un serveur MCP spécialiste échoue ou retourne une erreur HTTP ou JSON-RPC 2.0, THE MCP_Host SHALL marquer cet agent comme omis dans DiagnosticAuditData et continuer le traitement avec les agents restants.

### Exigence 3 : Transport MCP — Conformité JSON-RPC 2.0 sur HTTP+SSE

**User Story :** En tant que développeur, je veux que la communication entre le MCP_Host et les serveurs MCP spécialistes suive le protocole JSON-RPC 2.0 standard sur transport HTTP+SSE, afin de garantir l'interopérabilité et la conformité MCP.

#### Critères d'acceptation

1. THE MCP_Host SHALL envoyer chaque requête aux serveurs MCP spécialistes sous forme de message JSON-RPC 2.0 valide via HTTP POST vers l'endpoint `/rpc` du serveur, contenant les champs `jsonrpc` (valeur `"2.0"`), `method`, `params` et `id`.
2. THE chaque serveur MCP spécialiste SHALL retourner chaque réponse sous forme de message JSON-RPC 2.0 valide streamé via Server-Sent Events (SSE), contenant les champs `jsonrpc` (valeur `"2.0"`), `result` ou `error`, et `id` correspondant à la requête.
3. THE Transport_SSE SHALL transmettre les requêtes JSON-RPC 2.0 via HTTP POST (Content-Type `application/json`) et les réponses via SSE (Content-Type `text/event-stream`), chaque événement SSE contenant un message JSON-RPC 2.0 complet dans le champ `data`.
4. FOR ALL payloads de type AgentResult et arguments d'invocation de MCP_Tool, la sérialisation en JSON puis la désérialisation SHALL produire un payload équivalent à l'original (propriété aller-retour).
5. IF un serveur MCP spécialiste retourne une erreur HTTP (4xx, 5xx) ou un message JSON-RPC 2.0 avec un champ `error`, THEN THE MCP_Host SHALL interpréter le code d'erreur et le message conformément à la spécification HTTP et JSON-RPC 2.0.
6. IF un serveur MCP spécialiste HTTP est injoignable (connexion refusée, erreur DNS, timeout de connexion), THEN THE MCP_Host SHALL marquer cet agent comme omis et enregistrer l'erreur dans DiagnosticAuditData.

### Exigence 4 : Qualité des résultats des agents spécialistes

**User Story :** En tant que Praticien, je veux que chaque agent spécialiste retourne des résultats structurés et sourcés, afin de pouvoir évaluer la fiabilité de chaque contribution au diagnostic.

#### Critères d'acceptation

1. THE Agent_Épidémiologie SHALL retourner un AgentResult contenant au moins un Chunk_Grounded lorsque des données épidémiologiques pertinentes existent pour la Région et les symptômes fournis.
2. THE Agent_Symptomatologie SHALL retourner un AgentResult contenant au moins un Chunk_Grounded lorsque des guidelines cliniques pertinentes existent pour les symptômes fournis.
3. THE Agent_Laboratoire SHALL retourner un AgentResult contenant au moins un Chunk_Grounded lorsque des données de laboratoire pertinentes existent pour les symptômes fournis.
4. THE Agent_Traitement SHALL retourner un AgentResult contenant au moins un Chunk_Grounded lorsque des protocoles de traitement pertinents existent pour les symptômes fournis.
5. THE chaque agent spécialiste SHALL retourner un Score_Confiance compris entre 0.0 et 1.0 dans son AgentResult.
6. THE chaque agent spécialiste SHALL retourner une liste de diagnostics partiels (partial_differential) dans son AgentResult, chaque diagnostic contenant un nom de condition, une probabilité, un code CIM-10 optionnel et une liste de symptômes correspondants.
7. THE chaque agent spécialiste SHALL inclure un champ `fallback_used` (booléen) dans son AgentResult indiquant si le LLM de secours a été utilisé à la place du LLM principal pour produire le résultat.
8. THE chaque agent spécialiste SHALL utiliser le seuil de similarité vectorielle configuré (`LLAMAINDEX_SIMILARITY_THRESHOLD`, par défaut 0.75) pour déterminer si des données pertinentes existent dans sa collection de documents.

### Exigence 5 : Synthèse avec citations de preuves

**User Story :** En tant que Praticien, je veux que les résultats des quatre agents soient fusionnés en un diagnostic différentiel unique avec citations de preuves, afin de disposer d'une vue consolidée et traçable.

#### Critères d'acceptation

1. THE Agent_Synthèse SHALL fusionner les diagnostics partiels de tous les agents actifs en une liste unique de diagnostics différentiels.
2. WHEN deux agents retournent le même diagnostic (comparaison insensible à la casse), THE Agent_Synthèse SHALL dédupliquer en conservant la probabilité la plus élevée.
3. THE Agent_Synthèse SHALL trier les diagnostics par probabilité décroissante.
4. WHEN le nombre de diagnostics fusionnés est inférieur à 3, THE Agent_Synthèse SHALL compléter avec des diagnostics placeholder jusqu'à atteindre un minimum de 3 diagnostics.
5. THE Agent_Synthèse SHALL exclure de la synthèse les agents dont le AgentResult ne contient aucun Chunk_Grounded.
6. WHEN un agent est exclu de la synthèse, THE Agent_Synthèse SHALL enregistrer le nom de cet agent dans un avertissement de dégradation (degraded_warning).
7. THE Agent_Synthèse SHALL associer à chaque diagnostic issu d'agents actifs (ayant des Chunk_Grounded) au moins une Citation_Preuve contenant document_id, titre, source, extrait et numéro de page du Chunk_Grounded d'origine. Les diagnostics placeholder (ajoutés pour atteindre le minimum de 3) SHALL avoir une liste de citations vide.
8. THE Agent_Synthèse SHALL calculer un Score_Confiance global comme moyenne pondérée par le nombre de Chunk_Grounded de chaque agent actif.

### Exigence 6 : Réponse diagnostique structurée

**User Story :** En tant que Praticien, je veux recevoir une réponse diagnostique complète et structurée, afin de prendre des décisions cliniques éclairées.

#### Critères d'acceptation

1. THE DiagnosticOrchestrator SHALL retourner un DiagnosticResult contenant la liste des diagnostics différentiels, l'indicateur de fallback, l'avertissement de dégradation et la Locale.
2. WHEN le LLM principal (MedicalQwen3-Reasoning-14B) est indisponible et le LLM de secours (GPT-5) est utilisé, THE DiagnosticOrchestrator SHALL ajouter un disclaimer au DiagnosticResult indiquant que la réponse nécessite une vérification clinique.
3. THE DiagnosticOrchestrator SHALL persister la session diagnostique dans MongoDB avec un MCP_Session_ID unique, utilisé comme session_id dans la réponse et comme clé de liaison avec la Consultation.
4. THE endpoint `/api/v1/diagnose/symptoms` SHALL retourner un DiagnoseResponse contenant session_id, diagnostics, fallback_warning optionnel, degraded_warning optionnel et indicateur warnings_present.

### Exigence 7 : Traçabilité et audit

**User Story :** En tant qu'administrateur, je veux que chaque session diagnostique soit auditée, afin de garantir la traçabilité des décisions médicales assistées par IA.

#### Critères d'acceptation

1. WHEN une session diagnostique est complétée via le chemin MCP, THE DiagnosticOrchestrator SHALL écrire un document DiagnosticAudit dans la collection `diagnostic_audit` de MongoDB.
2. THE DiagnosticAudit SHALL contenir : timestamp, symptômes, hash du profil patient (sans données PII), Locale, Région, Score_Confiance, diagnostics, indicateur de fallback, avertissement de dégradation et résultats agents.
3. IF l'écriture du DiagnosticAudit échoue, THEN THE DiagnosticOrchestrator SHALL journaliser l'erreur et continuer le traitement sans faire échouer la requête du Praticien.
4. THE DiagnosticAudit SHALL enregistrer la liste des agents en timeout et la liste des agents omis.

### Exigence 8 : Gestion des modes dégradés

**User Story :** En tant que Praticien, je veux être informé lorsque le diagnostic est produit en mode dégradé, afin d'adapter mon niveau de confiance dans les résultats.

#### Critères d'acceptation

1. WHEN tous les serveurs MCP spécialistes échouent ou sont en timeout, THE Agent_Synthèse SHALL marquer le DiagnosticResult avec fallback_used à true.
2. WHEN au moins un serveur MCP spécialiste est omis de la synthèse, THE Agent_Synthèse SHALL inclure un degraded_warning listant les noms des agents omis.
3. WHEN au moins un AgentResult contient `fallback_used` à true, THE DiagnosticOrchestrator SHALL ajouter un avertissement de fallback dans la réponse indiquant quels agents ont utilisé le LLM de secours.
4. THE endpoint `/api/v1/diagnose/symptoms` SHALL positionner le champ warnings_present à true lorsque fallback_warning ou degraded_warning est présent.

### Exigence 9 : Support multi-locale et régional

**User Story :** En tant que Praticien au Togo ou au Bénin, je veux que le diagnostic tienne compte de ma région et de ma langue, afin d'obtenir des résultats pertinents pour mon contexte clinique.

#### Critères d'acceptation

1. THE MCP_Host SHALL inclure la Locale et la Région dans les arguments de chaque invocation de MCP_Tool sur les serveurs spécialistes.
2. THE Agent_Épidémiologie SHALL filtrer les données épidémiologiques en fonction de la Région fournie (TG pour Togo, BJ pour Bénin).
3. THE Agent_Traitement SHALL prioriser les protocoles locaux (PNLP Togo, PNLP Bénin) lorsque la Région est spécifiée.
4. WHEN la Locale est `fr-TG` ou `fr-BJ`, THE chaque serveur MCP spécialiste et l'Agent_Synthèse SHALL produire leurs résultats en français. THE DiagnosticOrchestrator SHALL transmettre la Locale aux agents sans transformation.
5. WHEN la Locale est `en`, THE chaque serveur MCP spécialiste et l'Agent_Synthèse SHALL produire leurs résultats en anglais. THE DiagnosticOrchestrator SHALL transmettre la Locale aux agents sans transformation.

### Exigence 10 : Contrôle d'accès au diagnostic guidé

**User Story :** En tant qu'administrateur, je veux que seuls les utilisateurs autorisés puissent accéder au mode diagnostic guidé, afin de protéger les données médicales.

#### Critères d'acceptation

1. THE endpoint `/api/v1/diagnose/symptoms` SHALL exiger un token JWT valide avec le rôle `admin`, `medecin` ou `infirmière`.
2. WHEN un utilisateur sans rôle autorisé tente d'accéder au endpoint, THE système SHALL retourner une erreur HTTP 403.
3. THE endpoint `/api/v1/diagnose/symptoms` SHALL appliquer une limite de débit de 30 requêtes par minute par utilisateur.
4. THE endpoint `GET /api/v1/consultations/me` SHALL exiger un token JWT valide avec le rôle `admin`, `medecin` ou `infirmière`.
5. THE endpoint `GET /api/v1/consultations/me` SHALL appliquer une limite de débit de 30 requêtes par minute par utilisateur.

### Exigence 11 : Historique des diagnostics du praticien

**User Story :** En tant que Praticien, je veux que chaque diagnostic produit par le pipeline MCP multi-agent soit automatiquement enregistré dans mon historique de consultations, afin de pouvoir retrouver et consulter mes diagnostics passés.

#### Critères d'acceptation

1. WHEN le pipeline MCP multi-agent complète une session diagnostique, THE DiagnosticOrchestrator SHALL créer automatiquement un document Consultation dans la collection `consultations` de MongoDB, en utilisant le MCP_Session_ID persisté à l'Exigence 6 comme clé de liaison.
2. THE Consultation créée SHALL contenir le user_id du Praticien ayant initié la requête diagnostique.
3. WHEN un patient_id est fourni dans la requête diagnostique, THE Consultation créée SHALL contenir le patient_id correspondant.
4. WHEN aucun patient_id n'est fourni dans la requête diagnostique, THE Consultation créée SHALL positionner le champ `is_one_shot` à true et le champ `patient_id` à null.
5. THE Consultation créée SHALL contenir un champ `mcp_session_id` stockant le MCP_Session_ID unique de la session diagnostique.
6. THE Consultation créée SHALL contenir un champ `agent_contributions` stockant la liste des Agent_Contributions (nom de l'agent, Score_Confiance, diagnostics partiels) de chaque agent spécialiste ayant participé à la session.
7. THE Consultation créée SHALL contenir un champ `evidence_citations` stockant la liste des Evidence_Citations (document_id, titre, source, extrait, page) utilisées pour produire le diagnostic.
8. THE Consultation créée SHALL contenir les champs existants `symptoms`, `diagnoses`, `llm_used`, `alerts` et `created_at` remplis à partir des résultats de la session MCP.
9. WHEN le Praticien interroge le endpoint `GET /api/v1/patients/{patient_id}/consultations`, THE système SHALL retourner les Consultations MCP multi-agent au même titre que les consultations classiques.
10. WHEN le Praticien interroge le endpoint `GET /api/v1/consultations/me`, THE système SHALL retourner l'historique complet des Consultations du Praticien authentifié (triées par `created_at` décroissant), y compris les consultations `is_one_shot` issues du pipeline MCP, pour affichage dans l'interface d'historique des diagnostics.
11. IF la création de la Consultation échoue, THEN THE DiagnosticOrchestrator SHALL journaliser l'erreur et retourner le DiagnosticResult au Praticien sans faire échouer la requête.

### Exigence 12 : Migration de base de données

**User Story :** En tant que développeur, je veux disposer d'un script de migration idempotent pour mettre à jour le schéma de la collection `consultations` et les index associés, afin de supporter les nouveaux champs MCP sans casser les documents existants.

#### Critères d'acceptation

1. THE Script_Migration SHALL ajouter les champs `mcp_session_id` (valeur par défaut null), `agent_contributions` (valeur par défaut liste vide) et `evidence_citations` (valeur par défaut liste vide) aux documents existants de la collection `consultations` qui ne possèdent pas ces champs.
2. THE Script_Migration SHALL créer un index sur le champ `mcp_session_id` de la collection `consultations` pour permettre la recherche par session MCP.
3. THE Script_Migration SHALL créer un index composé `{ user_id: 1, created_at: -1 }` sur la collection `consultations` pour optimiser la récupération de l'historique du Praticien.
4. THE Script_Migration SHALL créer un index composé `{ user_id: 1, patient_id: 1, created_at: -1 }` sur la collection `diagnostic_audit` pour permettre la recherche d'audits par Praticien et par patient.
5. WHEN le Script_Migration est exécuté sur une base de données déjà migrée, THE Script_Migration SHALL compléter son exécution sans modifier les documents existants et sans produire d'erreur (idempotence).
6. THE Script_Migration SHALL conserver la compatibilité ascendante avec les documents Consultation existants en ne supprimant et ne renommant aucun champ existant.
7. THE Script_Migration SHALL journaliser le nombre de documents mis à jour et le nombre d'index créés à la fin de son exécution.
8. THE Script_Migration SHALL être exécutable manuellement via la commande `python -m backend.scripts.migrate_consultations_add_mcp_fields`.
9. IF le Script_Migration échoue en cours d'exécution, THEN THE Script_Migration SHALL journaliser l'état d'avancement (nombre de documents traités, index créés) et permettre une reprise à partir du point d'échec lors de la prochaine exécution (idempotence partielle).
10. THE Script_Migration SHALL fournir une commande de rollback `python -m backend.scripts.migrate_consultations_add_mcp_fields --rollback` qui supprime les champs `mcp_session_id`, `agent_contributions` et `evidence_citations` uniquement sur les documents où `mcp_session_id` est null (documents migrés mais non utilisés par le pipeline MCP), et supprime les index créés par la migration.

### Exigence 13 : Création du rôle infirmière

**User Story :** En tant qu'administrateur, je veux pouvoir créer des comptes avec le rôle `infirmière`, afin de permettre au personnel infirmier d'accéder au diagnostic guidé.

#### Critères d'acceptation

1. THE système SHALL supporter le rôle `infirmière` (déjà défini dans l'enum `UserRole` de `backend/models/common.py`) dans toutes les vérifications RBAC des endpoints de diagnostic.
2. THE rôle `infirmière` SHALL avoir accès aux endpoints `/api/v1/diagnose/symptoms`, `/api/v1/diagnose/prescription`, `/api/v1/diagnose/session/{session_id}` et `GET /api/v1/consultations/me`.
3. THE rôle `infirmière` SHALL NOT avoir accès aux endpoints d'administration (`/api/v1/admin/*`).
4. THE script de seed (`scripts/seed.py`) SHALL pouvoir créer des comptes utilisateurs avec le rôle `infirmière`.

### Exigence 14 : Gestion du cycle de vie des serveurs MCP HTTP

**User Story :** En tant que développeur, je veux que le cycle de vie des connexions HTTP vers les serveurs MCP soit géré de manière fiable, afin d'éviter les fuites de ressources et garantir un arrêt propre.

#### Critères d'acceptation

1. WHEN une session diagnostique est initiée, THE MCP_Host SHALL vérifier que chaque serveur MCP spécialiste est joignable via une requête HTTP vers l'endpoint `GET /health` du serveur avant de démarrer les requêtes de diagnostic.
2. THE chaque serveur MCP spécialiste SHALL exposer un endpoint `GET /health` retournant un statut HTTP 200 lorsque le serveur est prêt à recevoir des requêtes.
3. THE MCP_Host SHALL utiliser un pool de connexions HTTP (via httpx.AsyncClient) pour gérer les connexions vers les serveurs MCP spécialistes, réduisant la latence de connexion entre les sessions.
4. WHEN le MCP_Host est arrêté (shutdown de l'application), THE MCP_Host SHALL fermer proprement le client HTTP et toutes les connexions actives vers les serveurs MCP spécialistes.
5. THE Docker Compose SHALL définir les quatre services agents (agent-epidemiology, agent-symptomatology, agent-lab, agent-treatment) avec des health checks basés sur l'endpoint `GET /health` de chaque serveur.
6. THE chaque service agent Docker SHALL être configuré sur le réseau Docker interne pour permettre la communication avec le service backend.

### Exigence 15 : Performance du pipeline diagnostique

**User Story :** En tant que Praticien, je veux que le diagnostic guidé retourne un résultat dans un délai raisonnable, afin de ne pas ralentir ma consultation.

#### Critères d'acceptation

1. THE pipeline MCP multi-agent SHALL retourner un DiagnosticResult en moins de 10 secondes dans le cas nominal (tous les agents répondent sans timeout).
2. THE pipeline MCP multi-agent SHALL retourner un DiagnosticResult en moins de 35 secondes dans le pire cas (un ou plusieurs agents en timeout de 30 secondes).
3. THE MCP_Host SHALL exécuter les quatre agents spécialistes en parallèle via des requêtes HTTP concurrentes (asyncio.gather avec httpx.AsyncClient) pour minimiser la latence totale.
4. THE DiagnosticOrchestrator SHALL journaliser la durée totale de chaque session diagnostique (en millisecondes) pour le monitoring de performance.

### Exigence 16 : Interface utilisateur du diagnostic guidé

**User Story :** En tant que Praticien, je veux que l'interface du diagnostic guidé affiche les résultats MCP multi-agent avec les avertissements, citations de preuves et contributions des agents, afin de prendre des décisions cliniques éclairées.

#### Critères d'acceptation

1. WHEN le champ `warningsPresent` de la `DiagnosisResponse` est `true`, THE page `/diagnose` SHALL afficher un bandeau d'alerte pour `fallbackWarning` (avertissement de fallback LLM) et/ou `degradedWarning` (avertissement de mode dégradé avec noms des agents omis).
2. WHEN la `DiagnosisResponse` contient un `confidenceScore`, THE page `/diagnose` SHALL afficher le score de confiance global sous forme de pourcentage (ex. « Confiance : 78 % ») dans la section des résultats.
3. WHEN la `DiagnosisResponse` contient des `evidenceCitations`, THE page `/diagnose` SHALL afficher pour chaque diagnostic la liste des citations de preuves associées, incluant le titre du document, la source, un extrait et le numéro de page.
4. WHEN la `DiagnosisResponse` contient des `agentContributions`, THE page `/diagnose` SHALL afficher la liste des agents ayant contribué au diagnostic, avec le nom de chaque agent et son score de confiance individuel.
5. THE type `DiagnosisResponse` dans `packages/api-client/index.ts` SHALL inclure les champs `fallbackWarning` (string optionnel), `degradedWarning` (string optionnel), `warningsPresent` (booléen), `confidenceScore` (nombre), `agentContributions` (liste de `AgentContributionDTO`) et `evidenceCitations` (liste de `EvidenceCitationDTO`).
6. THE type `ConsultationSchema` dans `packages/types/index.ts` SHALL inclure les champs `mcpSessionId` (string optionnel), `agentContributions` (liste de `AgentContributionSchema`) et `evidenceCitations` (liste de `EvidenceCitationSchema`).
7. THE `packages/types/index.ts` SHALL exporter les schémas Zod `EvidenceCitationSchema` et `AgentContributionSchema` avec les champs correspondants aux modèles backend (`document_id`/`documentId`, `title`, `source`, `excerpt`, `page` pour les citations ; `agent_name`/`agentName`, `confidence_score`/`confidenceScore`, `partial_differential`/`partialDifferential` pour les contributions).
8. THE application SHALL fournir une page ou section d'historique des diagnostics accessible via `/diagnose/history` ou intégrée dans la page `/diagnose`, appelant `GET /api/v1/consultations/me` pour afficher la liste paginée des consultations passées du Praticien.
9. THE page d'historique des diagnostics SHALL afficher pour chaque consultation : la date, un résumé des symptômes, le diagnostic principal, le score de confiance et un lien vers les détails complets.
10. THE fichiers de traduction i18n (`fr.json`, `en.json`, `fr-TG.json`, `fr-BJ.json`) SHALL contenir les clés de traduction pour : les avertissements (`diagnose.fallbackWarning`, `diagnose.degradedWarning`), le score de confiance (`diagnose.confidenceScore`), les contributions des agents (`diagnose.agentContributions`, `diagnose.agentName`, `diagnose.agentConfidence`), les citations de preuves (`diagnose.evidenceCitations`, `diagnose.citationTitle`, `diagnose.citationSource`, `diagnose.citationExcerpt`, `diagnose.citationPage`), et la page d'historique (`diagnose.history.title`, `diagnose.history.noHistory`, `diagnose.history.date`, `diagnose.history.topDiagnosis`, `diagnose.history.confidence`, `diagnose.history.viewDetails`).
11. THE lien de navigation vers l'historique des diagnostics SHALL être accessible depuis la page `/diagnose` ou via un onglet/bouton visible dans l'interface.


### Exigence 17 : Documentation

**User Story :** En tant que développeur, je veux disposer d'une documentation complète et à jour couvrant l'architecture MCP multi-agent, les endpoints API, la configuration et le déploiement, afin de pouvoir comprendre, maintenir et étendre le système.

#### Critères d'acceptation

1. THE `docs/api-reference.md` SHALL être mis à jour avec : les endpoints JSON-RPC 2.0 des serveurs MCP (`POST /rpc`, `GET /health`), le schéma de réponse de `POST /api/v1/diagnose/symptoms` incluant les nouveaux champs MCP (`mcp_session_id`, `confidence_score`, `agent_contributions`, `evidence_citations`, `fallback_warning`, `degraded_warning`, `warnings_present`), et la documentation du endpoint `GET /api/v1/consultations/me`.
2. THE `docs/architecture.md` SHALL être mis à jour avec : un diagramme d'architecture MCP multi-agent, la description des serveurs agents (Épidémiologie, Symptomatologie, Laboratoire, Traitement), le flux de communication MCP_Host via HTTP+SSE, et le pipeline du Synthesis_Agent.
3. THE `docs/developer-guide.md` SHALL être mis à jour avec : les instructions pour créer un nouveau serveur MCP agent, les instructions pour exécuter les serveurs agents localement, et les instructions pour tester les serveurs MCP.
4. THE `docs/configuration.md` SHALL être mis à jour avec : les variables d'environnement `AGENT_EPIDEMIOLOGY_URL`, `AGENT_SYMPTOMATOLOGY_URL`, `AGENT_LAB_URL`, `AGENT_TREATMENT_URL`, et l'utilisation du seuil `LLAMAINDEX_SIMILARITY_THRESHOLD` par les agents.
5. THE `docs/deployment.md` SHALL être mis à jour avec : les services Docker Compose des agents (`agent-epidemiology`, `agent-symptomatology`, `agent-lab`, `agent-treatment`), la configuration des health checks, et les considérations de scaling.
6. THE `README.md` SHALL être mis à jour avec : l'architecture MCP multi-agent dans les sections « Stack technique » et « Structure du projet », les nouveaux services Docker dans le tableau « Accéder aux services », et le script de migration dans la section « Démarrage rapide ».
7. THE chaque fichier de serveur MCP (`backend/agents/mcp_servers/base_server.py`, `epidemiology_server.py`, `symptomatology_server.py`, `lab_server.py`, `treatment_server.py`) SHALL contenir un docstring de module décrivant l'objectif du serveur, les primitives exposées (tools, resources, prompts) et la configuration requise.
