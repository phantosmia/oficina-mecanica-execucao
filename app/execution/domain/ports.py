from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.shared.events import Envelope
from app.execution.domain.entities import ExecutionJob
from app.execution.domain.value_objects import JobStatus


class AlreadyProcessedError(Exception):
    """A mensagem já tinha sido processada (reentrega): nada foi gravado."""


class IExecutionRepository(ABC):
    @abstractmethod
    def get(self, order_id: int) -> ExecutionJob | None: ...

    @abstractmethod
    def list_by_status(self, status: JobStatus) -> list[ExecutionJob]:
        """OS de um status, na ordem em que entraram nele (a fila)."""
        ...

    @abstractmethod
    def is_processed(self, message_id: str) -> bool: ...

    @abstractmethod
    def save(
        self,
        job: ExecutionJob,
        expected_status: JobStatus | None,
        events: list[Envelope],
        message_id: str | None = None,
    ) -> None:
        """Grava a OS, os eventos (outbox) e, se vier de uma mensagem, o
        registro dela como processada, tudo numa transação.

        `expected_status=None` cria a OS (falha se já existir); caso
        contrário só grava se o status salvo ainda for `expected_status`.
        Levanta `ConcurrencyError` se a condição falhar e
        `AlreadyProcessedError` se a mensagem já tiver sido processada."""
        ...

    @abstractmethod
    def reply(self, events: list[Envelope], message_id: str) -> None:
        """Só responde (outbox + mensagem processada), sem mudar nenhuma OS."""
        ...


@dataclass(frozen=True)
class CatalogItem:
    id: str
    name: str
    price: float
    active: bool


@dataclass(frozen=True)
class CatalogLookup:
    services: dict[str, CatalogItem]
    parts: dict[str, CatalogItem]
    missing_service_ids: list[str]
    missing_part_ids: list[str]


class ICatalogGateway(ABC):
    @abstractmethod
    def lookup(self, service_ids: list[str], part_ids: list[str]) -> CatalogLookup:
        """Consulta o Catálogo (REST síncrono). Levanta `CatalogUnavailableError`
        se ele não responder."""
        ...
