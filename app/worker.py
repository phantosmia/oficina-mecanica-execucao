"""Processo consumidor da fila de comandos da Execução (`python -m app.worker`)."""

import logging

from app.messaging.dispatcher import Dispatcher
from app.messaging.sqs_consumer import SqsConsumer
from app.shared.dynamodb import get_table
from app.shared.logging_config import configure_logging
from app.shared.settings import settings
from app.execution.adapters.dynamodb_repository import DynamoDBExecutionRepository

logger = logging.getLogger("app.worker")


def main() -> None:  # pragma: no cover - laço infinito; a lógica testada fica em SqsConsumer/Dispatcher
    configure_logging(settings.log_level)
    dispatcher = Dispatcher(lambda: DynamoDBExecutionRepository(get_table()))
    consumer = SqsConsumer([settings.commands_queue_url], dispatcher, settings.worker_wait_seconds)
    logger.info("worker iniciado fila=%s", settings.commands_queue_url)
    while True:
        try:
            consumer.poll_queue(settings.commands_queue_url)
        except Exception:
            logger.exception("falha ao ler a fila; tentando de novo")


if __name__ == "__main__":  # pragma: no cover
    main()
