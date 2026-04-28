import logging
import json
import os
from datetime import datetime, timezone

import azure.functions as func
from azure.servicebus import ServiceBusClient, ServiceBusMessage


def main(myblob: func.InputStream):
    # blob_name ex: docstoragetabuna/input/abc-uuid/cv_amine.pdf
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
