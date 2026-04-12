# Requirements Document

## Introduction

Refonte de deux pages de l'application Diagno-Pilot : la page « Assistant Q&A » (chat) et la page « Documents ». L'objectif est de (1) restreindre l'assistant conversationnel aux seules questions médicales/tropicales en supprimant l'affichage des citations de sources et en s'appuyant exclusivement sur le LLM médical, et (2) transformer la page Documents en une interface « chat avec documents » utilisant le pipeline RAG LlamaIndex, où l'import et la liste des documents indexés sont déplacés dans la barre latérale, le panneau principal devenant un chat contextuel avec citations liées aux documents uploadés.

## Glossary

- **Assistant_QA** : Page de chat conversationnel existante (`/[locale]/chat`), permettant aux professionnels de santé de poser des questions médicales. Utilise exclusivement le LLM médical (pas de RAG, pas de sources).
- **Documents_Page** : Page de gestion et consultation des documents médicaux indexés (`/[locale]/documents`).
- **Grounding_System_Prompt** : Prompt système injecté dans le pipeline pour cadrer les réponses de l'assistant (défini dans `llamaindex_pipeline.py`).
- **Accepted_Medical_Topics** : Ensemble des sujets acceptés par l'assistant — maladies tropicales, maladies infectieuses, médecine clinique générale, nutrition, santé mentale, et éthique médicale.
- **Topic_Guard** : Mécanisme de filtrage intégré au prompt système du LLM, qui détecte les questions hors du périmètre Accepted_Medical_Topics et décline poliment d'y répondre. Implémenté comme une instruction dans le prompt système — le LLM agit comme garde et générateur dans un seul appel d'inférence. Pour le Q&A (sans RAG), cela évite tout compute inutile. Pour le Document_Chat (avec RAG), le Topic_Guard est évalué dans le prompt avant que les chunks récupérés ne soient utilisés pour la génération.
- **Document_Chat** : Nouveau chat contextuel sur la page Documents utilisant le LlamaIndex_Pipeline RAG pour interroger les documents uploadés avec citations. Inclut un panneau d'historique des sessions pour naviguer entre les conversations précédentes.
- **Document_Sidebar** : Barre latérale de la page Documents contenant le formulaire d'import, la liste des documents indexés et les actions de téléchargement/suppression.
- **Citation_Chip** : Composant inline `[N]` dans les réponses du Document_Chat, cliquable pour ouvrir le CitationPopup.
- **Citation_Popup** : Modal affichant la page PDF avec surbrillance jaune du passage cité.
- **Source_Panel** : Composant existant affichant les sources dans le chat (à supprimer du Assistant_QA).
- **LlamaIndex_Pipeline** : Pipeline RAG backend combinant retrieval hybride et génération LLM. Utilisé exclusivement par le Document_Chat.
- **Document_Service** : Service backend gérant l'ingestion, le chunking, l'embedding et le stockage S3 des documents.
- **Index_Manager** : Service backend gérant la recherche hybride (vector + BM25 via RRF) et le re-ranking cross-encoder.
- **SSE_Stream** : Flux Server-Sent Events utilisé pour le streaming des tokens de réponse.
- **DocumentSource** : Modèle Pydantic contenant documentId, title, source, section, excerpt, page, highlight (bbox), confidenceScore.

## Dependency Map

| Requirement | Depends On | Priority |
|---|---|---|
| Req 1 — Suppression citations Q&A | Req 10 (migration sessions) | Must |
| Req 2 — Restriction domaine médical | — | Must |
| Req 3 — Upload dans sidebar | — | Must |
| Req 4 — Liste docs dans sidebar | Req 3 | Must |
| Req 5 — Document_Chat panneau principal | Req 7 (endpoint backend) | Must |
| Req 6 — Citations dans Document_Chat | Req 5, Req 7 | Must |
| Req 7 — Endpoint backend documents/chat | — | Must |
| Req 8 — Layout responsive | Req 3, Req 4, Req 5 | Should |
| Req 9 — i18n | Req 3, Req 4, Req 5 | Should |
| Req 10 — Migration sessions existantes | — | Must |
| Req 11 — Téléchargement documents | — | Should |
| Req 12 — Contrôle d'accès frontend Document_Chat | Req 7 | Must |
| Req 13 — Feedback Topic_Guard | Req 1, Req 2 | Should |

## Requirements

### Requirement 1: Suppression du RAG et des citations de sources dans le Assistant_QA

**User Story:** En tant que professionnel de santé, je veux que l'assistant conversationnel réponde à mes questions médicales en s'appuyant exclusivement sur le LLM médical, sans afficher de citations de sources, afin que l'interface de chat soit épurée et centrée sur la réponse.

#### Acceptance Criteria

1. THE Assistant_QA backend SHALL NOT use the LlamaIndex_Pipeline RAG retrieval or the document index to generate answers. The Assistant_QA SHALL rely exclusively on the medical LLM (MedicalQwen3-Reasoning-14B / GPT-5 fallback) for generating responses.
2. WHEN the Assistant_QA renders an assistant message, THE Assistant_QA SHALL NOT display the Source_Panel component beneath the message.
3. WHEN the Assistant_QA receives a `done` SSE event containing a `sources` array, THE Assistant_QA SHALL ignore the sources array and not render any Citation_Chip components.
4. THE Assistant_QA backend SHALL persist an empty sources array (`sources: []`) in the chat session MongoDB document for each assistant turn.

### Requirement 2: Restriction du domaine de l'assistant aux maladies tropicales et médicales

**User Story:** En tant qu'administrateur, je veux que l'assistant ne réponde qu'aux questions portant sur les maladies tropicales et la médecine, afin de garantir que l'outil reste dans son périmètre clinique.

#### Acceptance Criteria

1. THE Grounding_System_Prompt SHALL instruct the LLM to answer questions about Accepted_Medical_Topics (tropical diseases, infectious diseases, general clinical medicine, nutrition, mental health, and medical ethics).
2. THE Grounding_System_Prompt SHALL instruct the LLM to politely decline any question that is not related to Accepted_Medical_Topics, explaining that the assistant is specialized in medical and tropical disease topics.
3. THE Topic_Guard SHALL be implemented as an instruction within the Grounding_System_Prompt, so that the LLM acts as both guard and generator in a single inference pass. For the Q&A chat (no RAG), this avoids any unnecessary compute. For the Document_Chat, the Topic_Guard instruction is evaluated by the LLM before it uses the retrieved chunks for generation.
4. WHEN a user submits a non-medical question (e.g., sports, politics, cooking, entertainment), THE assistant SHALL return a polite refusal message stating that the assistant is specialized in medical and tropical disease questions.
5. WHEN a user submits a question about any Accepted_Medical_Topics, THE assistant SHALL process the question normally.
6. THE polite refusal message SHALL be generated in the same language as the user's question (French or English).

### Requirement 3: Déplacement du formulaire d'import dans la Document_Sidebar

**User Story:** En tant qu'administrateur ou médecin, je veux que le formulaire d'upload de documents soit accessible depuis la barre latérale de la page Documents, afin de libérer le panneau principal pour le chat contextuel.

#### Acceptance Criteria

1. WHEN the Documents_Page loads, THE Document_Sidebar SHALL display the document upload form (title, source, file picker, submit button).
2. WHEN a document is successfully uploaded via the Document_Sidebar, THE Document_Sidebar SHALL update the indexed documents list to include the new document without requiring a full page reload.
3. THE Document_Sidebar SHALL validate that the uploaded file format is one of PDF, DOCX, TXT, or CSV before submitting.
4. WHILE a document upload is in progress, THE Document_Sidebar SHALL display a progress indicator with elapsed time.
5. IF a document upload fails, THEN THE Document_Sidebar SHALL display an error message within the sidebar.

### Requirement 4: Déplacement de la liste des documents indexés dans la Document_Sidebar

**User Story:** En tant qu'administrateur ou médecin, je veux voir la liste des documents indexés dans la barre latérale, afin de pouvoir consulter et gérer les documents tout en utilisant le chat contextuel.

#### Acceptance Criteria

1. WHEN the Documents_Page loads, THE Document_Sidebar SHALL display the list of all indexed medical documents with title, source, and date.
2. WHEN an admin user clicks the delete button on a document entry, THE Document_Sidebar SHALL remove the document from the list and trigger backend deletion.
3. THE Document_Sidebar SHALL support scrolling when the document list exceeds the visible area.
4. IF the document list fetch fails, THEN THE Document_Sidebar SHALL display an error message.
5. WHEN the document list is empty, THE Document_Sidebar SHALL display an empty state message.

### Requirement 5: Chat contextuel avec documents dans le panneau principal

**User Story:** En tant que professionnel de santé, je veux pouvoir poser des questions sur les documents uploadés via un chat dans le panneau principal de la page Documents, afin d'interroger directement la base de connaissances médicales.

**Depends on:** Req 7 (endpoint backend)

#### Acceptance Criteria

1. WHEN the Documents_Page loads, THE Document_Chat SHALL display a chat interface in the main panel with a message input field and a send button.
2. WHEN a user submits a question in the Document_Chat, THE Document_Chat SHALL send the question to the backend POST `/api/v1/documents/chat` endpoint via SSE streaming and display the response tokens incrementally.
3. THE Document_Chat SHALL support multi-turn conversation with session history persisted in MongoDB (same persistence model as the Assistant_QA chat sessions).
4. THE Document_Chat SHALL include a session history navigation panel allowing users to switch between previous Document_Chat conversations, create new sessions, and delete existing ones.
5. WHEN the backend returns a `done` SSE event, THE Document_Chat SHALL display the complete assistant response in a message bubble.
6. IF the SSE stream encounters an error, THEN THE Document_Chat SHALL display an error message and offer a retry option for retryable errors.
7. THE Document_Chat SHALL use the LlamaIndex_Pipeline to perform RAG retrieval across all indexed medical documents (not scoped to a single document).

### Requirement 6: Citations avec lien vers le document source dans le Document_Chat

**User Story:** En tant que professionnel de santé, je veux que les réponses du chat contextuel incluent des citations cliquables renvoyant au document source avec surbrillance du passage pertinent, afin de pouvoir vérifier l'information à la source.

**Depends on:** Req 5, Req 7

#### Acceptance Criteria

1. WHEN the Document_Chat receives a `done` SSE event with a non-empty `sources` array, THE Document_Chat SHALL render Citation_Chip components inline or below the assistant message for each source.
2. WHEN a user clicks a Citation_Chip in the Document_Chat, THE Citation_Popup SHALL open and display the referenced document.
3. THE Citation_Popup SHALL fetch the presigned S3 URL via GET `/api/v1/documents/{id}/view` and render the PDF page containing the cited passage.
4. THE Citation_Popup SHALL overlay a yellow highlight rectangle at the bbox coordinates of the cited passage on the PDF page.
5. IF the DocumentSource has no highlight (bbox) data, THEN THE Citation_Popup SHALL display the excerpt text as a blockquote fallback.
6. WHEN the user presses Escape or clicks outside the Citation_Popup, THE Citation_Popup SHALL close.

### Requirement 7: Backend — endpoint de chat contextuel pour les documents

**User Story:** En tant que développeur, je veux un endpoint backend dédié au chat contextuel des documents, afin que le Document_Chat puisse interroger la base de connaissances avec des citations incluant les données de highlight.

#### Acceptance Criteria

1. THE backend SHALL expose a POST `/api/v1/documents/chat` SSE streaming endpoint that accepts a message, an optional session_id, and returns streamed tokens followed by a `done` event.
2. WHEN the `/api/v1/documents/chat` endpoint processes a query, THE LlamaIndex_Pipeline SHALL retrieve relevant chunks across all indexed documents and include highlight (bbox) and page data in each DocumentSource of the response.
3. THE `/api/v1/documents/chat` endpoint SHALL require authentication and be accessible to roles admin, medecin, and infirmière.
4. WHEN the `/api/v1/documents/chat` endpoint returns sources, each DocumentSource SHALL include the documentId, title, source, section, excerpt, page, highlight (with bbox and page), and confidenceScore fields.
5. THE `/api/v1/documents/chat` endpoint SHALL support multi-turn conversation by accepting a session_id and loading previous messages from the chat session stored in MongoDB.
6. IF no relevant document chunks are found, THEN THE `/api/v1/documents/chat` endpoint SHALL return a response indicating that no information was found in the indexed documents.

### Requirement 8: Layout responsive de la page Documents redesignée

**User Story:** En tant que professionnel de santé, je veux que la page Documents redesignée soit utilisable sur des écrans de différentes tailles, afin de pouvoir l'utiliser sur tablette ou desktop.

#### Acceptance Criteria

1. THE Documents_Page SHALL use a responsive layout using Tailwind CSS utility classes (flexbox, responsive breakpoints `md:`, relative/min/max width utilities).
2. ON desktop viewports (≥768px), THE Documents_Page SHALL display the Document_Sidebar and the Document_Chat side by side, with the sidebar using Tailwind classes `w-[25%] min-w-[280px] max-w-[380px]` and the chat panel using `flex-1`.
3. ON narrow viewports (<768px), THE Document_Sidebar SHALL be hidden by default (`hidden md:flex`), replaced by a toggle button, and THE Document_Chat SHALL occupy the full width (`w-full`).
4. WHEN the user clicks the sidebar toggle button on a narrow viewport, THE Document_Sidebar SHALL expand as a fixed overlay (`fixed inset-0 z-50`) with a semi-transparent backdrop.
5. THE Document_Sidebar content SHALL use `overflow-y-auto` and `overflow-x-hidden` to adapt gracefully to its available width without horizontal overflow or truncation of critical information.

### Requirement 9: Internationalisation (i18n) des nouveaux composants

**User Story:** En tant que professionnel de santé francophone ou anglophone, je veux que tous les nouveaux éléments d'interface soient traduits, afin de pouvoir utiliser l'application dans ma langue.

#### Acceptance Criteria

1. THE Document_Chat SHALL use next-intl translation keys for all user-facing text (placeholder, send button, error messages, empty state).
2. THE Document_Sidebar SHALL use next-intl translation keys for all user-facing text (upload form labels, document list headers, empty state, error messages, download button).
3. THE Topic_Guard polite refusal message in the Grounding_System_Prompt SHALL instruct the LLM to detect the user's language and respond with the refusal in that same language.

### Requirement 10: Migration des sessions de chat existantes

**User Story:** En tant qu'administrateur, je veux que les sessions de chat existantes soient supprimées lors du déploiement de la refonte, afin de repartir sur une base propre compatible avec la nouvelle architecture.

#### Acceptance Criteria

1. A migration script SHALL delete all existing chat session documents from the `chat_sessions` MongoDB collection.
2. THE migration script SHALL be idempotent — running it multiple times SHALL produce the same result.
3. THE migration script SHALL log the number of deleted sessions.
4. AFTER migration, THE Assistant_QA SHALL start with no session history, and users SHALL see an empty session list with a user-friendly message (i18n key: `sessionHistory.migratedEmpty`) indicating that previous conversations are no longer available.

### Requirement 11: Téléchargement des documents uploadés

**User Story:** En tant que professionnel de santé, je veux pouvoir télécharger les documents indexés depuis la barre latérale, afin de consulter le document original hors de l'application.

#### Acceptance Criteria

1. EACH document entry in the Document_Sidebar SHALL display a download button/icon.
2. WHEN a user clicks the download button, THE application SHALL fetch the presigned S3 URL via GET `/api/v1/documents/{id}/view` and trigger a browser download of the original file using the `Content-Disposition: attachment` header (forcing download rather than in-browser preview for all formats: PDF, DOCX, TXT, CSV).
3. THE download action SHALL be accessible to roles admin, medecin, and infirmière (same roles as the view endpoint).
4. IF the presigned URL fetch fails, THEN THE Document_Sidebar SHALL display an error message.

### Requirement 12: Contrôle d'accès frontend pour le Document_Chat

**User Story:** En tant qu'administrateur, je veux que le Document_Chat applique les mêmes restrictions d'accès côté frontend que côté backend, afin d'empêcher les utilisateurs non autorisés d'accéder à l'interface.

**Depends on:** Req 7

#### Acceptance Criteria

1. THE Documents_Page SHALL verify the user's role on load and restrict access to roles admin, medecin, and infirmière (matching the backend endpoint roles).
2. IF a user with an unauthorized role (e.g., pharmacien, guest) navigates to the Documents_Page, THE application SHALL redirect them to the home page.
3. THE Document_Chat input and send button SHALL be disabled if the user's authentication token is expired or missing, with a message prompting re-authentication.

### Requirement 13: Mécanisme de feedback pour le Topic_Guard

**User Story:** En tant que professionnel de santé, je veux pouvoir signaler lorsque l'assistant refuse à tort une question médicale légitime, afin que le système puisse être amélioré.

**Depends on:** Req 2

#### Acceptance Criteria

1. WHEN the Assistant_QA displays a Topic_Guard refusal message, THE Assistant_QA SHALL display a "This is a medical question" feedback button below the refusal message.
2. WHEN a user clicks the feedback button, THE application SHALL send a POST request to the backend recording the original question, the refusal response, and the user's feedback.
3. THE backend SHALL expose a POST `/api/v1/chat/feedback` endpoint that persists the feedback in a `topic_guard_feedback` MongoDB collection with fields: question, response, user_id, timestamp.
4. THE feedback endpoint SHALL require authentication and be accessible to all authenticated roles.
5. THE feedback mechanism SHALL NOT automatically retry the question — it only records the feedback for later review by administrators.
