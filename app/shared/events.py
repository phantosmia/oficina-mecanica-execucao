"""Envelope das mensagens entre microsserviços.

Formato definido em `docs/saga.md` (oficina-mecanica-fiap), seção "Envelope
das mensagens" — o mesmo para comandos e eventos, em todos os serviços.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
import uuid


@dataclass(frozen=True)
class Envelope:
    type: str
    payload: dict[str, Any]
    saga_id: str | None = None
    order_id: int | None = None
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    occurred_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "type": self.type,
            "saga_id": self.saga_id,
            "order_id": self.order_id,
            "occurred_at": self.occurred_at,
            "payload": self.payload,
        }
