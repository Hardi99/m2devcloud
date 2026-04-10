# Synthèse — Dev pour le Cloud

## Le projet : c'est quoi ?

Une application web qui permet d'**uploader un document PDF** et de le stocker sur Azure. C'est une app de traitement de documents (genre soumettre une carte vitale, un justificatif, etc.).

---

## Les 3 couches du projet

### 1. Le Frontend — `src/front/`
Application React/TypeScript. C'est ce que l'utilisateur voit dans son navigateur : un formulaire pour sélectionner un fichier et l'envoyer.

### 2. L'API — `src/api/`
Serveur Python (FastAPI). C'est le cerveau : il reçoit les demandes du front, enregistre des données en base, et génère des autorisations d'upload.

### 3. La Function — `src/functions/`
Un script Azure qui se déclenche automatiquement quand un fichier arrive. C'est lui qui est censé **traiter** le document une fois uploadé.

---

## Ce qui se passe quand tu envoies un PDF (dans l'ordre)

```
Étape 1 : Le front dit à l'API "je veux uploader Carte Vitale.pdf"
Étape 2 : L'API crée un job dans Cosmos DB + génère une URL temporaire
Étape 3 : Le front envoie le PDF directement sur Azure Blob avec cette URL
Étape 4 : Le front demande toutes les 3 secondes "c'est traité ?"
Étape 5 : La Function Azure détecte le fichier et traite le document
```

---

## Pourquoi le PDF ne passe pas par l'API ?

C'est le point le plus important à comprendre.

L'API génère une **SAS URL** — une URL temporaire valable 15 minutes qui autorise l'upload directement sur Azure Blob, sans passer par le serveur.

```
Sans SAS URL :   Navigateur → API → Azure Blob   (l'API supporte tout le trafic)
Avec SAS URL  :  Navigateur → API (juste pour créer le job)
                 Navigateur → Azure Blob directement (le fichier)
```

C'est une pratique standard dans le cloud (AWS, GCP et Azure font tous pareil). Le serveur n'est jamais engorgé par des fichiers lourds.

---

## Les services Azure utilisés

| Service | Rôle dans le projet |
|---|---|
| **App Service** | Héberge l'API Python (dans un conteneur Docker) |
| **Azure Blob Storage** | Stocke les PDFs uploadés |
| **Cosmos DB** | Stocke les métadonnées de chaque job (id, statut, date...) |
| **Azure Function** | Script déclenché automatiquement quand un PDF arrive dans le Blob |
| **Container Registry** | Stocke l'image Docker de l'API |
| **Static Web App** | Héberge le frontend React |

---

## Le déploiement (CI/CD)

A chaque `git push` sur `main`, GitHub Actions fait tout automatiquement :

```
Tu push du code
       ↓
GitHub Actions détecte le changement
       ↓
   src/api/ modifié ?  → Build Docker → push sur Container Registry → déploie sur App Service
   src/front/ modifié? → Build React → déploie sur Static Web App
   src/functions/ ?    → Déploie la Function Azure
```

Tu n'as jamais besoin de déployer manuellement.

---

## Pourquoi tu apprendras ça en tant que dev

- **SAS URL / Presigned URL** : pattern universel sur tous les clouds pour les uploads de fichiers
- **Architecture découplée** : front, API et workers sont indépendants — tu peux mettre à jour l'un sans toucher aux autres
- **Event-driven** : la Function réagit à un événement (fichier déposé) plutôt que de tourner en boucle — c'est plus efficace et moins cher
- **CI/CD** : le déploiement est automatique et reproductible — pas de "ça marche sur ma machine"
