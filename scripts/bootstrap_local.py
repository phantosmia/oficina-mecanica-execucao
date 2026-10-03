"""Cria no LocalStack a tabela, o tópico e a fila de comandos da Execução
(docker-compose). Na AWS, esses recursos vêm do Terraform. Idempotente.

Uso: `python -m scripts.bootstrap_local`
"""

import logging

import boto3

from app.shared.dynamodb import create_table_if_missing
from app.shared.settings import settings


def bootstrap() -> dict[str, str]:
    create_table_if_missing(settings.table_name)
    topic = boto3.client("sns", region_name=settings.aws_region).create_topic(
        Name=settings.events_topic_arn.rsplit(":", 1)[-1]
    )["TopicArn"]
    queue = boto3.client("sqs", region_name=settings.aws_region).create_queue(
        QueueName=settings.commands_queue_url.rstrip("/").rsplit("/", 1)[-1]
    )["QueueUrl"]
    return {"table": settings.table_name, "events_topic": topic, "commands_queue": queue}


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("bootstrap").info("recursos locais prontos: %s", bootstrap())
