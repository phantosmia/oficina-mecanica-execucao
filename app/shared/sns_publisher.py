import json
from typing import Any

import boto3

from app.shared.settings import settings


def message_attributes(envelope: dict[str, Any], trace_headers: dict[str, str]) -> dict[str, dict[str, str]]:
    """`MessageAttributes` padronizados (docs/saga.md, "Envelope das mensagens"):
    permitem filtrar assinaturas por `type` e propagar o trace sem abrir o corpo."""
    attributes = {
        "type": envelope["type"],
        "correlation_id": envelope.get("saga_id") or envelope["message_id"],
    }
    if envelope.get("saga_id"):
        attributes["saga_id"] = envelope["saga_id"]
    if envelope.get("order_id") is not None:
        attributes["order_id"] = str(envelope["order_id"])
    attributes.update(trace_headers)
    return {name: {"DataType": "String", "StringValue": value} for name, value in attributes.items()}


class SnsEventPublisher:
    def __init__(self, topic_arn: str) -> None:
        self._topic_arn = topic_arn
        self._client = boto3.client("sns", region_name=settings.aws_region)

    def publish(self, envelope: dict[str, Any], trace_headers: dict[str, str]) -> None:
        self._client.publish(
            TopicArn=self._topic_arn,
            Message=json.dumps(envelope, ensure_ascii=False),
            MessageAttributes=message_attributes(envelope, trace_headers),
        )
