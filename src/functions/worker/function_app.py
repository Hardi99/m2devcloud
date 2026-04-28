import logging
import json
import os
from datetime import datetime, timezone

import azure.functions as func
from azure.servicebus import ServiceBusClient, ServiceBusMessage
from azure.cosmos import CosmosClient, exceptions

app = func.FunctionApp()

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


def generate_tags(file_name: str) -> list:
    tags = set()
    name_lower = file_name.lower()
    if "." in name_lower:
        ext = "." + name_lower.rsplit(".", 1)[-1]
        tags.update(EXTENSION_TAGS.get(ext, []))
    for keyword, keyword_tags in KEYWORD_TAGS.items():
        if keyword in name_lower:
            tags.update(keyword_tags)
    return sorted(tags)


def get_cosmos_container():
    client = CosmosClient(os.environ["CosmosEndpoint"], os.environ["CosmosKey"])
    return client.get_database_client("db-docs").get_container_client("jobs")


@app.blob_trigger(
    arg_name="myblob",
    path="docstoragetabuna/input/{folder}/{name}",
    connection="docstoragetabuna_STORAGE"
)
def blob_upload_worker(myblob: func.InputStream):
    # blob path: docstoragetabuna/input/{uuid}/{fileName}
    parts = myblob.name.split("/")
    document_id = parts[-2]
    file_name = parts[-1]

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

    logging.info(f"Message envoyé dans Service Bus pour le document {document_id}")


@app.service_bus_queue_trigger(
    arg_name="msg",
    queue_name="document-queue",
    connection="ServiceBusConnection"
)
def service_bus_worker(msg: func.ServiceBusMessage):
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
        return

    try:
        doc = container.read_item(item=document_id, partition_key="JOB")
    except exceptions.CosmosResourceNotFoundError:
        logging.warning(f"Document {document_id} introuvable dans Cosmos DB")
        container.upsert_item({"id": document_id, "pk": "JOB", "fileName": file_name, "status": "ERROR"})
        return

    tags = generate_tags(file_name)
    doc["status"] = "PROCESSED"
    doc["tags"] = tags
    doc["processedAt"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    container.replace_item(item=document_id, body=doc)
    logging.info(f"Document {document_id} traité avec les tags : {tags}")
