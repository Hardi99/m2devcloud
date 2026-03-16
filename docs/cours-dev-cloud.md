# Dev pour le Cloud — Notes de cours

## Architecture globale du projet

```
┌─────────────────── Azure Subscription ───────────────────┐
│                                                           │
│  Groupe de ressources (Resource Group)                    │
│  └── conteneur logique qui regroupe tout ci-dessous       │
│                                                           │
│  ┌─────────────────┐  ┌──────────────────┐               │
│  │  Compte de      │  │  Cosmos DB       │               │
│  │  stockage       │  │  (base de        │               │
│  │  (Blob Storage) │  │   données NoSQL) │               │
│  │                 │  │                  │               │
│  │  Container:     │  │  Database:       │               │
│  │  docstorage...  │  │  db-docs         │               │
│  │  > input/       │  │  Container:      │               │
│  │    {jobId}/     │  │  jobs            │               │
│  │    fichier.pdf  │  │                  │               │
│  └─────────────────┘  └──────────────────┘               │
│                                                           │
│  ┌─────────────────┐  ┌──────────────────┐               │
│  │  Container      │  │  Azure Web App   │               │
│  │  Registry (ACR) │  │  (ton API)       │               │
│  │                 │  │                  │               │
│  │  Stocke les     │  │  Tire l'image    │               │
│  │  images Docker  │  │  depuis ACR et   │               │
│  │                 │  │  expose /jobs    │               │
│  └─────────────────┘  └──────────────────┘               │
│                                                           │
└───────────────────────────────────────────────────────────┘

                   + Azure Static Web Apps
                     (héberge le frontend React)
```

---

## Rôle de chaque ressource Azure

| Ressource | Rôle dans le projet |
|-----------|---------------------|
| **Resource Group** | Conteneur logique pour regrouper et facturer toutes les ressources ensemble |
| **Cosmos DB** | Stocke les jobs (métadonnées : id, status, fileName, createdAt...) |
| **Blob Storage** | Stocke les fichiers PDF uploadés (`input/{jobId}/fichier.pdf`) |
| **Container Registry (ACR)** | Stocke les images Docker de l'API (comme un Docker Hub privé) |
| **Azure Web App** | Exécute l'API FastAPI depuis l'image récupérée dans l'ACR |
| **Azure Static Web Apps** | Héberge le frontend React (HTML/CSS/JS statiques, CDN mondial) |

---

## Le flux complet

```
Utilisateur (navigateur)
     │
     │  1. Sélectionne un fichier, clique "Créer & Uploader"
     │
     │  POST /jobs  { fileName, contentType }
     ▼
Azure Web App — API FastAPI
     │
     ├──► Cosmos DB   →  crée un job  { id, status: "CREATED", ... }
     │
     └──► génère un SAS token (URL signée, valable 15 min)
          retourne { jobId, uploadUrl }
     │
     │  2. PUT uploadUrl  (fichier binaire, sans passer par l'API)
     ▼
Azure Blob Storage
     └── input/{jobId}/fichier.pdf

     │
     │  3. GET /jobs/{jobId}  (polling toutes les 3s)
     ▼
Azure Web App — retourne le statut du job
```

> Le fichier va **directement** du navigateur vers le Blob Storage, sans transiter par l'API.
> C'est le rôle du SAS token : il délègue temporairement l'accès au stockage.

---

## Azure Resource Manager (ARM)

Le **Gestionnaire des ressources** (ARM) est la couche centrale d'Azure qui reçoit toutes les demandes de création, modification, suppression de ressources.

- Quand tu crées une ressource dans le portail Azure → tu parles à ARM
- Quand tu déploies via GitHub Actions → tu parles à ARM
- Les templates ARM (fichiers JSON dans `infra/arm/`) permettent de **décrire toute l'infra en code** et de la recréer identiquement sur un autre environnement (infra-as-code)

---

## Commandes importantes

### Lancer l'API en local

```bash
python -m uvicorn app.main:app --reload
```

Décortiquée :

| Partie | Signification |
|--------|---------------|
| `python -m uvicorn` | Lance uvicorn **via Python** (garantit qu'on utilise le bon environnement virtuel) |
| `app.main` | Chemin Python vers le fichier : dossier `app/`, fichier `main.py` |
| `:app` | Nom de la variable FastAPI dans ce fichier (`app = FastAPI(...)`) |
| `--reload` | Redémarre automatiquement le serveur dès qu'un fichier change (mode dev uniquement) |

En production, le Dockerfile utilise cette commande sans `--reload` :
```bash
uvicorn app.main:app --host 0.0.0.0 --port 80
```

---

### Les 3 commandes Docker — et pourquoi l'ordre est crucial

```bash
# 1. S'authentifier sur le registry Azure
docker login <ton-acr>.azurecr.io

# 2. Tagger l'image avec l'adresse complète du registry
docker tag cloud-doc-api <ton-acr>.azurecr.io/cloud-doc-api:latest

# 3. Pousser l'image taguée vers le registry
docker push <ton-acr>.azurecr.io/cloud-doc-api:latest
```

**Pourquoi cet ordre est impératif :**

**Étape 1 — `docker login` d'abord**
Sans authentification, les étapes 2 et 3 peuvent s'exécuter localement mais le `push` sera rejeté avec une erreur 401 (non autorisé). Le login crée un token stocké localement que Docker réutilise ensuite.

**Étape 2 — `docker tag` avant `docker push`**
Docker détermine **où pousser** l'image uniquement à partir de son nom/tag.
- `cloud-doc-api` → Docker ne sait pas où envoyer ça
- `<ton-acr>.azurecr.io/cloud-doc-api:latest` → Docker sait que c'est sur ton ACR Azure

Sans le tag, le `push` échoue ou va sur Docker Hub public par défaut.

**Étape 3 — `docker push` en dernier**
C'est l'envoi réel des couches de l'image vers le registry. Il nécessite :
- Le token d'auth (étape 1) → pour avoir le droit d'écrire
- Le bon nom d'image (étape 2) → pour savoir où écrire

> Dans ton projet, **GitHub Actions exécute ces 3 étapes automatiquement**
> à chaque push sur `main` (voir `.github/workflows/api-build-push.yml`).

---

## Ce que je peux déduire de ton compte Azure (via le `.env`)

En lisant le fichier `.env` de ton projet :

| Information | Valeur déduite |
|-------------|----------------|
| **Nom du Cosmos DB account** | `tabuna-db` |
| **Database** | `db-docs` |
| **Container Cosmos** | `jobs` |
| **Nom du Storage Account** | `docstoragetabuna` |
| **Blob Container** | `docstoragetabuna` |
| **Région probable** | À vérifier dans le portail (déduite de l'endpoint `.documents.azure.com`) |

> Je ne peux pas me connecter directement à ton portail Azure —
> pour vérifier l'état réel des ressources, connecte-toi sur [portal.azure.com](https://portal.azure.com)
> et cherche le groupe de ressources qui contient `tabuna`.

---

## Points qui méritent attention

- Le **SAS token expire après 15 minutes** — le frontend doit uploader rapidement après avoir reçu l'URL
- Les **clés du `.env` sont des secrets** — elles ne doivent jamais être committées sur Git (le `.gitignore` les exclut)
- Le **`--reload` d'uvicorn** ne doit jamais être utilisé en production — uniquement en développement local
- Le **Container Registry** est indépendant du Web App : tu peux changer l'image déployée sans toucher à la config du Web App
