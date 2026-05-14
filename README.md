# Pipeline Cloud Asynchrone – Gestion de Documents

Application cloud événementielle de traitement de documents avec tagging IA et notifications temps réel.

**Groupe :** ibtissam EL HANY / Hardi TABUNA  
**Soutenance :** 18 mai 2026 – 16h15

---

## Architecture

```
React (frontend)
  │
  │ upload fichier (SAS URL)
  ▼
Azure Blob Storage (container: input/)
  │
  │ Blob Trigger
  ▼
Azure Function – blob_upload_worker
  │  └─ publie dans Service Bus
  │  └─ notifie React : UPLOADED
  ▼
Azure Service Bus Queue (document-queue)
  │  maxDeliveryCount = 3
  ▼
Azure Function – service_bus_worker
  │  └─ met le doc en PROCESSING
  │  └─ appelle OpenAI pour les tags
  │  └─ met à jour Cosmos DB (status + tags)
  │  └─ notifie React : PROCESSED
  │
  │ (si échecs répétés)
  ▼
Service Bus Dead Letter Queue
  │
  │ DLQ Trigger
  ▼
Azure Function – dlq_alert_worker
  │  └─ met à jour Cosmos DB (status: ERROR)
  │  └─ notifie React : ERROR

Azure SignalR Service ──── notifications temps réel ───► React
```

**États métier :** `CREATED → UPLOADED → QUEUED → PROCESSING → PROCESSED`  
**En erreur :** `→ ERROR` (depuis tout état)

---

## Stack technique

| Composant | Technologie |
|---|---|
| Frontend | React 19 + TypeScript + Vite |
| Backend API | FastAPI (Python 3.12) |
| Functions | Azure Functions v2 (Python 3.12) |
| Base de données | Azure Cosmos DB (NoSQL) |
| Stockage | Azure Blob Storage |
| Messaging | Azure Service Bus |
| Notifications | Azure SignalR Service |
| Tagging IA | OpenAI API – gpt-4o-mini |
| Conteneurs | Docker + Azure Container Registry |
| Hébergement | Azure App Service (Web App) |
| CI/CD | GitLab CI/CD |

---

## Structure du projet

```
.
├── .gitlab-ci.yml              # Pipeline GitLab CI/CD
├── AUTHORS.TXT
├── src/
│   ├── api/                    # FastAPI – création des jobs, génération SAS URL
│   │   ├── app/
│   │   │   ├── main.py
│   │   │   ├── routes_jobs.py
│   │   │   ├── blob_service.py
│   │   │   ├── cosmos.py
│   │   │   └── models.py
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   ├── front/                  # React – upload + notifications SignalR
│   │   ├── src/
│   │   │   ├── App.tsx
│   │   │   └── App.css
│   │   └── Dockerfile
│   └── functions/worker/       # Azure Functions (Blob, Service Bus, DLQ, SignalR)
│       ├── function_app.py
│       ├── host.json
│       └── requirements.txt
```

---

## Azure Functions

### `blob_upload_worker`
Déclenché par l'upload d'un fichier dans `input/`. Publie un message JSON dans Service Bus et envoie une notification `UPLOADED` via SignalR.

### `service_bus_worker`
Consomme les messages de la queue. Appelle OpenAI (`gpt-4o-mini`) pour générer 3 à 8 tags en français. Met à jour Cosmos DB et envoie les notifications `PROCESSING` puis `PROCESSED` avec les tags.

**Fallback :** si l'appel IA échoue, les tags sont générés par règles (extension du fichier + mots-clés).

### `dlq_alert_worker`
Déclenché quand un message atteint la Dead Letter Queue (après 3 tentatives échouées). Met à jour Cosmos DB avec `status: ERROR` et la raison, et notifie le frontend.

### `negotiate`
Endpoint HTTP pour la négociation SignalR. Retourne le token de connexion au hub `documents`.

---

## Variables d'environnement

### Azure Functions (App Settings)

| Variable | Description |
|---|---|
| `CosmosEndpoint` | URI du compte Cosmos DB |
| `CosmosKey` | Clé primaire Cosmos DB |
| `ServiceBusConnection` | Chaîne de connexion Service Bus |
| `ServiceBusQueueName` | Nom de la queue (défaut : `document-queue`) |
| `docstoragetabuna_STORAGE` | Chaîne de connexion Blob Storage |
| `AzureSignalRConnectionString` | Chaîne de connexion SignalR |
| `OpenAIApiKey` | Clé API OpenAI |
| `AzureWebJobsStorage` | Stockage interne Azure Functions |
| `AzureWebJobsFeatureFlags` | `EnableWorkerIndexing` (requis Python v2) |

### Frontend (variables Vite)

| Variable | Description |
|---|---|
| `VITE_API_URL` | URL de l'API FastAPI |
| `VITE_FUNCTIONS_URL` | URL de l'Azure Function App |

---

## CI/CD – GitLab

Le pipeline `.gitlab-ci.yml` comporte 3 stages :

| Stage | Jobs |
|---|---|
| `lint` | `lint-functions` (flake8), `lint-frontend` (eslint) |
| `build` | `build-frontend` (Docker → ACR), `build-api` (Docker → ACR) |
| `deploy` | `deploy-functions` (zip → Azure), `deploy-frontend`, `deploy-api` |

### Variables GitLab à configurer (`Settings > CI/CD > Variables`)

```
AZURE_CLIENT_ID
AZURE_CLIENT_SECRET
AZURE_TENANT_ID
AZURE_SUBSCRIPTION_ID
AZURE_RESOURCE_GROUP
AZURE_FUNCTION_APP_NAME
AZURE_WEB_APP_RESOURCE_GROUP
AZURE_FRONT_APP_NAME
AZURE_API_APP_NAME
ACR_LOGIN_SERVER
ACR_USERNAME
ACR_PASSWORD
VITE_API_URL
VITE_FUNCTIONS_URL
```

---

## Configuration Service Bus

La queue `document-queue` est configurée avec `maxDeliveryCount = 3` : après 3 tentatives de traitement échouées, le message est automatiquement déplacé en Dead Letter Queue.

```bash
az servicebus queue update \
  --name document-queue \
  --namespace-name tabuna-servicebus \
  --resource-group tabuna_group \
  --max-delivery-count 3
```

---

## Flux complet

1. L'utilisateur sélectionne un fichier dans le frontend React
2. L'API FastAPI crée un job dans Cosmos DB et retourne une SAS URL
3. Le frontend uploade directement le fichier dans Azure Blob Storage
4. Le Blob Trigger se déclenche et publie un message dans Service Bus
5. Le frontend se connecte à SignalR et écoute les événements `documentStatus`
6. Le Service Bus Trigger traite le message, appelle OpenAI, met à jour Cosmos DB
7. Les notifications SignalR arrivent en temps réel : `UPLOADED → QUEUED → PROCESSING → PROCESSED`
8. Les tags générés par l'IA s'affichent dans le frontend
