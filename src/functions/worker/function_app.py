import logging
import json
import os
from datetime import datetime, timezone

import azure.functions as func
from azure.servicebus import ServiceBusClient, ServiceBusMessage
from azure.cosmos import CosmosClient, exceptions
from openai import OpenAI

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

EXTENSION_TAGS = {
    ".pdf": ["pdf", "document"],
    ".docx": ["word", "document"],
    ".png": ["image"],
}

KEYWORD_TAGS = {
    "cv": ["cv", "rh"],
    "facture": ["facture", "comptabilite"],
    "contrat": ["contrat", "administratif"],
    "azure": ["azure", "cloud"],
    "docker": ["docker", "devops"],
}


def generate_tags_fallback(file_name: str) -> list:
    tags = set()
    name_lower = file_name.lower()
    if "." in name_lower:
        ext = "." + name_lower.rsplit(".", 1)[-1]
        tags.update(EXTENSION_TAGS.get(ext, []))
    for keyword, keyword_tags in KEYWORD_TAGS.items():
        if keyword in name_lower:
            tags.update(keyword_tags)
    return sorted(tags)


def generate_tags_ia(file_name: str) -> list:
    client = OpenAI(api_key=os.environ["OpenAIApiKey"])
    prompt = (
        f"Analyse le nom de fichier suivant et génère entre 3 et 8 tags courts en français.\n"
        f"Nom du fichier : {file_name}\n\n"
        f"Retourne uniquement un tableau JSON de chaînes, sans texte autour."
    )
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    raw = response.choices[0].message.content.strip()
    tags = json.loads(raw)
    return sorted([t.lower() for t in tags if isinstance(t, str)])


def generate_tags(file_name: str) -> list:
    try:
        tags = generate_tags_ia(file_name)
        logging.info(f"Tags IA générés : {tags}")
        return tags
    except Exception as e:
        logging.warning(f"Appel IA échoué, fallback sur les règles : {e}")
        return generate_tags_fallback(file_name)


def get_cosmos_container():
    client = CosmosClient(os.environ["CosmosEndpoint"], os.environ["CosmosKey"])
    return client.get_database_client("db-docs").get_container_client("jobs")


def signalr_message(document_id: str, status: str, message: str, extra: dict = None) -> str:
    payload = {"documentId": document_id, "status": status, "message": message}
    if extra:
        payload.update(extra)
    return json.dumps({"target": "documentStatus", "arguments": [payload]})


@app.route(route="negotiate", methods=["GET", "POST"])
@app.generic_input_binding(
    arg_name="connectionInfo",
    type="signalRConnectionInfo",
    hubName="documents",
    connectionStringSetting="AzureSignalRConnectionString"
)
def negotiate(req: func.HttpRequest, connectionInfo) -> func.HttpResponse:
    return func.HttpResponse(connectionInfo, mimetype="application/json")


@app.blob_trigger(
    arg_name="myblob",
    path="docstoragetabuna/input/{name}",
    connection="docstoragetabuna_STORAGE"
)
@app.generic_output_binding(
    arg_name="signalrMessages",
    type="signalR",
    hubName="documents",
    connectionStringSetting="AzureSignalRConnectionString"
)
def blob_upload_worker(myblob: func.InputStream, signalrMessages: func.Out[str]):
    file_part = myblob.name.split("/")[-1]
    document_id, file_name = file_part.split("_", 1)

    message_body = {
        "documentId": document_id,
        "fileName": file_name,
        "blobName": myblob.name,
        "size": myblob.length,
        "uploadedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    connection_str = os.environ["ServiceBusConnection"]
    queue_name = os.environ.get("ServiceBusQueueName", "document-queue")

    with ServiceBusClient.from_connection_string(connection_str) as client:
        with client.get_queue_sender(queue_name) as sender:
            sender.send_messages(ServiceBusMessage(json.dumps(message_body)))

    signalrMessages.set(signalr_message(document_id, "UPLOADED", "Fichier reçu"))
    logging.info(f"Message envoyé dans Service Bus pour le document {document_id}")


@app.service_bus_queue_trigger(
    arg_name="msg",
    queue_name="document-queue",
    connection="ServiceBusConnection"
)
@app.generic_output_binding(
    arg_name="signalrMessages",
    type="signalR",
    hubName="documents",
    connectionStringSetting="AzureSignalRConnectionString"
)
def service_bus_worker(msg: func.ServiceBusMessage, signalrMessages: func.Out[str]):
    body = msg.get_body().decode("utf-8")
    data = json.loads(body)

    document_id = data["documentId"]
    file_name = data["fileName"]
    size = data["size"]

    logging.info(f"Traitement document {document_id} - {file_name}")

    container = get_cosmos_container()

    if size == 0:
        logging.warning(f"Document {document_id} est vide")
        container.upsert_item({"id": document_id, "pk": "JOB", "fileName": file_name, "status": "ERROR"})
        signalrMessages.set(signalr_message(document_id, "ERROR", "Fichier vide"))
        return

    try:
        doc = container.read_item(item=document_id, partition_key="JOB")
    except exceptions.CosmosResourceNotFoundError:
        logging.warning(f"Document {document_id} introuvable dans Cosmos DB")
        container.upsert_item({"id": document_id, "pk": "JOB", "fileName": file_name, "status": "ERROR"})
        signalrMessages.set(signalr_message(document_id, "ERROR", "Document introuvable"))
        return

    doc["status"] = "PROCESSING"
    container.replace_item(item=document_id, body=doc)
    signalrMessages.set(signalr_message(document_id, "PROCESSING", "Traitement IA en cours"))

    tags = generate_tags(file_name)
    doc["status"] = "PROCESSED"
    doc["tags"] = tags
    doc["processedAt"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    container.replace_item(item=document_id, body=doc)
    signalrMessages.set(signalr_message(document_id, "PROCESSED", "Tagging terminé", {"tags": tags}))
    logging.info(f"Document {document_id} traité avec les tags : {tags}")
