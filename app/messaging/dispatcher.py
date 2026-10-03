"""Roteia cada mensagem recebida para o caso de uso correspondente."""

import json
import logging
from collections.abc import Callable
from typing import Any

from app.shared.events import Envelope
from app.execution.application.saga_handlers import EnqueueDiagnosisUseCase, EnqueueRepairUseCase
from app.execution.domain.ports import IExecutionRepository

logger = logging.getLogger(__name__)

# Comandos do orquestrador (fila execucao-comandos)
HANDLERS: dict[str, type] = {
    "EnfileirarDiagnostico": EnqueueDiagnosisUseCase,
    "EnfileirarReparo": EnqueueRepairUseCase,
}


def parse_body(body: str) -> Envelope:
    """Corpo da mensagem SQS → envelope (aceita também o embrulho do SNS
    quando `RawMessageDelivery` está desligado)."""
    data: dict[str, Any] = json.loads(body)
    if data.get("Type") == "Notification" and "Message" in data:
        data = json.loads(data["Message"])
    return Envelope(
        type=data["type"],
        payload=data.get("payload") or {},
        saga_id=data.get("saga_id"),
        order_id=data.get("order_id"),
        message_id=data["message_id"],
        occurred_at=data["occurred_at"],
    )


class Dispatcher:
    def __init__(self, repo_factory: Callable[[], IExecutionRepository]) -> None:
        self._repo_factory = repo_factory

    def handle(self, envelope: Envelope) -> bool:
        """Processa a mensagem. Retorna False para tipo desconhecido."""
        handler = HANDLERS.get(envelope.type)
        if handler is None:
            logger.warning("mensagem de tipo desconhecido ignorada type=%s message_id=%s", envelope.type, envelope.message_id)
            return False
        handler(self._repo_factory()).execute(envelope)
        logger.info(
            "mensagem processada type=%s message_id=%s saga_id=%s order_id=%s",
            envelope.type, envelope.message_id, envelope.saga_id, envelope.order_id,
        )
        return True
