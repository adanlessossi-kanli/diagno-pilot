# Requirements — Diagno-Pilot

## Introduction

Diagno-pilot est une application web et mobile d'aide au diagnostic des maladies infectieuses et à la prescription antibiotique, destinée aux professionnels de santé en Afrique de l'Ouest (Togo, Bénin). Elle couvre la pédiatrie et la médecine adulte. L'application est disponible en français et en anglais.

---

## REQ-01 : Authentification et gestion des rôles

**En tant que** professionnel de santé,  
**je veux** me connecter avec mes identifiants et accéder aux fonctionnalités selon mon rôle,  
**afin de** garantir la sécurité et la traçabilité des actions.

### Critères d'acceptation
- L'application supporte les rôles : médecin généraliste, pédiatre, urgentiste, pharmacien, interne, administrateur
- L'accès aux fonctionnalités est restreint selon le rôle (ex. : seul l'admin peut gérer les documents)
- Les sessions expirent après inactivité
- Toutes les actions sont tracées dans un journal d'audit

---

## REQ-02 : Mode guidé — Saisie des symptômes et diagnostic différentiel

**En tant que** médecin,  
**je veux** saisir les symptômes et signes cliniques d'un patient,  
**afin d'** obtenir une liste de diagnostics différentiels classés par probabilité.

### Critères d'acceptation
- L'utilisateur peut saisir des symptômes en texte libre ou via une liste structurée
- L'app retourne au moins 3 diagnostics différentiels avec un score de probabilité
- Chaque diagnostic est accompagné des symptômes concordants et d'un code CIM-10 si disponible
- Les résultats sont générés via le pipeline RAG (base de connaissances + LLM infectiologie)
- Le profil patient (âge, poids, comorbidités) influence les suggestions

---

## REQ-03 : Mode guidé — Prescription antibiotique adaptée

**En tant que** médecin,  
**je veux** obtenir une prescription antibiotique adaptée au diagnostic retenu et au profil patient,  
**afin de** prescrire de manière sûre et conforme aux directives locales.

### Critères d'acceptation
- La prescription inclut : molécule, dose, fréquence, durée, voie d'administration
- La dose est calculée au poids pour les patients pédiatriques
- La dose est plafonnée à la dose adulte maximale si nécessaire
- Les ajustements pour insuffisance rénale ou hépatique sont appliqués automatiquement
- Les allergies connues du patient déclenchent une alerte et une alternative est proposée

---

## REQ-04 : Assistant Q&A conversationnel (interface de chat)

**En tant que** professionnel de santé,  
**je veux** poser des questions libres sur les antibiotiques et les maladies infectieuses,  
**afin d'** obtenir des réponses basées sur les documents de référence chargés.

### Critères d'acceptation
- L'interface de chat permet une conversation multi-tours
- Les réponses sont générées via RAG (retrieval sur la base vectorielle MongoDB + LLM)
- Chaque réponse cite les sources utilisées (document, section, extrait)
- Le contexte patient peut être attaché à une session de chat pour personnaliser les réponses
- L'historique de la session est conservé pendant la durée de la session

---

## REQ-05 : Base de connaissances médicale

**En tant qu'** administrateur,  
**je veux** charger et indexer des documents médicaux de référence,  
**afin d'** alimenter la base de connaissances utilisée par le pipeline RAG.

### Critères d'acceptation
- Les sources supportées : CHU Lomé, CHU Abomey-Calavi, OMS AFRO, MSF (Lassa, choléra, méningite), PNLP
- Les formats supportés pour l'indexation : PDF, DOCX, TXT, CSV
- Les documents sont découpés en chunks, encodés en vecteurs et indexés dans MongoDB Atlas Vector Search
- Les fichiers sources sont stockés sur AWS S3 (LocalStack en développement local)
- L'admin peut voir la liste des documents indexés, leur statut et les supprimer
- La recherche vectorielle retourne les passages les plus pertinents (top-k par similarité cosinus)

---

## REQ-06 : Gestion des profils patients

**En tant que** médecin,  
**je veux** créer et gérer des profils patients avec leurs données cliniques,  
**afin d'** obtenir des recommandations personnalisées.

### Critères d'acceptation
- Un profil patient contient : nom, date de naissance, poids, allergies, comorbidités (insuffisance rénale/hépatique), médicaments en cours
- Le groupe d'âge est calculé automatiquement : néonatal (0–28j), nourrisson (1–23 mois), enfant (2–17 ans), adulte (18+)
- Les profils sont persistés en base de données et accessibles à travers les sessions
- Une consultation "one-shot" est possible sans création de dossier patient

---

## REQ-07 : Dossier patient, historique et fichiers cliniques

**En tant que** médecin,  
**je veux** accéder à l'historique des consultations d'un patient et joindre des fichiers cliniques,  
**afin de** suivre l'évolution et centraliser les données médicales.

### Critères d'acceptation
- Le dossier patient liste toutes les consultations passées avec date, symptômes, diagnostic retenu et prescription
- Une consultation peut être rouverte en lecture seule
- Les consultations one-shot ne sont pas rattachées à un dossier patient
- Les fichiers patients (résultats de laboratoire, imagerie, PDF, CSV) peuvent être joints à une consultation et sont stockés sur AWS S3
- L'accès au dossier est restreint au professionnel créateur et aux administrateurs

---

## REQ-08 : Fonctionnalités pédiatriques spécifiques

**En tant que** pédiatre,  
**je veux** des calculs de doses et des recommandations adaptés à l'âge et au poids de l'enfant,  
**afin de** prescrire en toute sécurité en pédiatrie.

### Critères d'acceptation
- Le calcul de dose au poids (mg/kg) est automatique pour les tranches néonatal, nourrisson, enfant
- Des alertes spécifiques sont affichées pour les molécules contre-indiquées selon la tranche d'âge (ex. : fluoroquinolones chez l'enfant)
- La dose calculée est toujours plafonnée à la dose adulte maximale
- Les recommandations pédiatriques sont issues des directives PNLP et des registres MSF

---

## REQ-09 : Alertes de sécurité

**En tant que** prescripteur,  
**je veux** être alerté en temps réel sur les risques liés à la prescription,  
**afin d'** éviter les erreurs médicamenteuses.

### Critères d'acceptation
- Les alertes couvrent : allergies connues, interactions médicamenteuses, contre-indications (âge, insuffisance organique)
- Les alertes critiques bloquent la prescription et exigent une confirmation explicite
- Les alertes de niveau warning sont affichées sans bloquer
- Une alternative thérapeutique est proposée en cas d'alerte critique

---

## REQ-10 : Traçabilité et audit

**En tant qu'** administrateur,  
**je veux** accéder aux journaux d'audit de l'application,  
**afin de** garantir la conformité et la traçabilité des actions médicales.

### Critères d'acceptation
- Toutes les actions sensibles sont enregistrées : connexion, consultation, prescription, modification de dossier, upload de document
- Les logs incluent : utilisateur, action, ressource concernée, horodatage, adresse IP
- Les logs sont accessibles uniquement aux administrateurs
- Les logs sont conservés au minimum 12 mois

---

## REQ-11 : Application mobile (React Native)

**En tant que** professionnel de santé en mobilité,  
**je veux** accéder aux fonctionnalités de Diagno-pilot depuis mon smartphone,  
**afin de** consulter et prescrire depuis n'importe quel contexte clinique.

### Critères d'acceptation
- L'application mobile partage la logique métier et les composants UI avec le web (monorepo)
- Les fonctionnalités disponibles sur mobile : mode guidé, chat Q&A, consultation dossier patient
- L'interface est adaptée aux écrans mobiles (navigation native)
- L'application supporte iOS et Android

---

## REQ-12 : Internationalisation (i18n)

**En tant que** professionnel de santé,  
**je veux** utiliser l'application dans ma langue préférée,  
**afin de** travailler efficacement sans barrière linguistique.

### Critères d'acceptation
- L'application est disponible en français et en anglais
- Le changement de langue est accessible depuis l'interface sans rechargement
- Tous les textes de l'interface, messages d'erreur et alertes sont traduits
- La langue par défaut est détectée depuis les préférences du navigateur/système
