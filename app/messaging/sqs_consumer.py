import json
import logging
from typing import Any

import boto3

from app.messaging.dispatcher import Dispatcher, parse_body
from app.shared.settings import settings
from app.shared.tracing import consume_trace

logger = logging.getLogger(__name__)


class SqsConsumer:
    """Lê as filas do serviço e entrega cada mensagem ao `Dispatcher`.

    A mensagem só é apagada da fila depois de processada com sucesso. Se o
    processamento levantar exceção (falha técnica), ela não é apagada: volta
    a ficar visível e é tentada de novo; depois de 5 tentativas, a política
    de *redrive* da fila (Terraform) a move para a DLQ. Mensagem malformada
    (JSON inválido, sem `type`) também não é apagada, pelo mesmo caminho:
    vai parar na DLQ para análise, sem travar a fila.
    """

    def __init__(self, queue_urls: list[str], dispatcher: Dispatcher, wait_seconds: int = 10) -> None:
        self._queue_urls = [url for url in queue_urls if url]
        self._dispatcher = dispatcher
        self._wait_seconds = wait_seconds
        self._client = boto3.client("sqs", region_name=settings.aws_region)

    @property
    def queue_urls(self) -> list[str]:
        return list(self._queue_urls)

    def poll_once(self) -> int:
        """Uma rodada de leitura em cada fila. Retorna quantas mensagens foram apagadas."""
        return sum(self.poll_queue(queue_url) for queue_url in self._queue_urls)

    def poll_queue(self, queue_url: str) -> int:
        """Uma leitura (*long polling*) numa fila. Retorna quantas mensagens foram apagadas."""
        handled = 0
        response = self._client.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=self._wait_seconds,
            MessageAttributeNames=["All"],
        )
        for message in response.get("Messages", []):
            if self._process(message):
                self._client.delete_message(QueueUrl=queue_url, ReceiptHandle=message["ReceiptHandle"])
                handled += 1
        return handled

    def _process(self, message: dict[str, Any]) -> bool:
        attributes = {k: v.get("StringValue", "") for k, v in message.get("MessageAttributes", {}).items()}
        try:
            envelope = parse_body(message["Body"])
        except (json.JSONDecodeError, KeyError, TypeError):
            logger.error("mensagem malformada mantida na fila (irá para a DLQ) message_id_sqs=%s", message.get("MessageId"))
            return False
        with consume_trace(f"sqs/{envelope.type}", attributes):
            try:
                self._dispatcher.handle(envelope)
            except Exception:
                logger.exception(
                    "falha ao processar mensagem; ela voltará para a fila type=%s message_id=%s",
                    envelope.type, envelope.message_id,
                )
                return False
        return True
