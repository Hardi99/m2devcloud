import logging
import json
import os
from datetime import datetime, timezone

import azure.functions as func
from azure.servicebus import ServiceBusClient, ServiceBusMessage


def main(myblob: func.InputStream):
    blob_name = myblob.name  # ex: docstoragetabuna/input/123_cv_amine_azure.pdf
    file_part = blob_name.split("/")[-1]  # ex: 123_cv_amine_azure.pdf

    parts = file_part.split("_", 1)
    document_id = parts[0]
    file_name = parts[1] if len(parts) > 1 else file_part

    message_body = {
        "documentId": document_id,
        "fileName": file_name,
        "blobName": blob_name,
        "size": myblob.length,
        "uploadedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    connection_str = os.environ["ServiceBusConnection"]
    queue_name = os.environ.get("ServiceBusQueueName", "document-queue")

    with ServiceBusClient.from_connection_string(connection_str) as client:
        with client.get_queue_sender(queue_name) as sender:
            sender.send_messages(ServiceBusMessage(json.dumps(message_body)))

    logging.info(f"Message envoyé dans Service Bus pour le document {document_id}")
