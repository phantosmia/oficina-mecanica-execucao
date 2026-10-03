"""Padrão *transactional outbox* (RFC-0007, em oficina-mecanica-fiap).

O evento não é publicado no SNS durante a requisição ou o processamento do
comando: ele é gravado como um item `OUTBOX#<message_id>` na mesma
`TransactWriteItems` da mudança de status (`outbox_put`), e um processo
separado (`app/outbox_relay.py`) publica e apaga esses itens (`OutboxRelay`).
Assim não existe "mudou o status mas o evento se perdeu" nem "publicou o
evento de uma mudança que não foi gravada".

A entrega é *at-least-once*: se o relay cair entre publicar e apagar, o
evento sai de novo na próxima volta. Os consumidores descartam repetições
pelo `message_id` (docs/saga.md).
"""

import json
import logging
from typing import Any, Protocol

from app.shared.dynamodb import query_gsi1
from app.shared.events import Envelope
from app.shared.tracing import current_trace_headers

OUTBOX_PARTITION = "OUTBOX"

logger = logging.getLogger(__name__)


def outbox_put(table_name: str, envelope: Envelope) -> dict[str, Any]:
    """Operação `Put` pronta para entrar numa `TransactWriteItems` feita pelo
    cliente do *resource* (`table.meta.client`, que converte sozinho os tipos
    Python para o formato do DynamoDB)."""
    item = {
        "pk": f"OUTBOX#{envelope.message_id}",
        "gsi1pk": OUTBOX_PARTITION,
        "gsi1sk": f"{envelope.occurred_at}#{envelope.message_id}",
        "envelope": json.dumps(envelope.to_dict(), ensure_ascii=False),
        "trace_headers": current_trace_headers(),
    }
    return {"Put": {"TableName": table_name, "Item": item}}


class EventPublisher(Protocol):
    def publish(self, envelope: dict[str, Any], trace_headers: dict[str, str]) -> None: ...


class OutboxRelay:
    def __init__(self, table: Any, publisher: EventPublisher) -> None:
        self._table = table
        self._publisher = publisher

    def run_once(self) -> int:
        """Publica os eventos pendentes, do mais antigo pro mais novo. Retorna quantos publicou."""
        published = 0
        for item in query_gsi1(self._table, OUTBOX_PARTITION):
            envelope = json.loads(item["envelope"])
            self._publisher.publish(envelope, dict(item.get("trace_headers") or {}))
            self._table.delete_item(Key={"pk": item["pk"]})
            logger.info("evento publicado type=%s message_id=%s", envelope["type"], envelope["message_id"])
            published += 1
        return published
