from dataclasses import dataclass, field
from datetime import datetime

from app.shared.exceptions import DomainError
from app.execution.domain.value_objects import JobStatus, ensure_transition


@dataclass(frozen=True)
class Vehicle:
    plate: str
    brand: str | None = None
    model: str | None = None
    year: int | None = None


@dataclass(frozen=True)
class DiagnosedItem:
    """Serviço ou peça escolhido pelo mecânico, com o preço copiado do
    Catálogo no momento do diagnóstico (snapshot: mudanças de preço depois
    não alteram o orçamento desta OS)."""

    item_id: str
    name: str
    quantity: int
    unit_price: float

    @property
    def subtotal(self) -> float:
        return round(self.unit_price * self.quantity, 2)


@dataclass(frozen=True)
class Diagnosis:
    notes: str
    services: list[DiagnosedItem]
    parts: list[DiagnosedItem]

    def __post_init__(self) -> None:
        if not self.services and not self.parts:
            raise DomainError("O diagnóstico precisa de pelo menos um serviço ou peça.")

    @property
    def labor_total(self) -> float:
        return round(sum(s.subtotal for s in self.services), 2)

    @property
    def parts_total(self) -> float:
        return round(sum(p.subtotal for p in self.parts), 2)

    @property
    def total(self) -> float:
        return round(self.labor_total + self.parts_total, 2)


@dataclass
class ExecutionJob:
    """Uma OS dentro da Execução: do diagnóstico até o fim do reparo."""

    order_id: int
    saga_id: str
    problem_description: str
    vehicle: Vehicle | None
    status: JobStatus
    # Quando a OS entrou em cada etapa (para a fila e para medir tempos).
    status_history: dict[JobStatus, datetime] = field(default_factory=dict)
    diagnosis: Diagnosis | None = None
    repair_notes: str | None = None

    @classmethod
    def enqueue_for_diagnosis(
        cls, order_id: int, saga_id: str, problem_description: str, vehicle: Vehicle | None, now: datetime
    ) -> "ExecutionJob":
        return cls(
            order_id=order_id,
            saga_id=saga_id,
            problem_description=problem_description,
            vehicle=vehicle,
            status=JobStatus.AWAITING_DIAGNOSIS,
            status_history={JobStatus.AWAITING_DIAGNOSIS: now},
        )

    @property
    def status_since(self) -> datetime:
        return self.status_history[self.status]

    def start_diagnosis(self, now: datetime) -> None:
        self._move_to(JobStatus.IN_DIAGNOSIS, now)

    def complete_diagnosis(self, diagnosis: Diagnosis, now: datetime) -> None:
        self._move_to(JobStatus.DIAGNOSED, now)
        self.diagnosis = diagnosis

    def enqueue_for_repair(self, now: datetime) -> None:
        self._move_to(JobStatus.AWAITING_REPAIR, now)

    def start_repair(self, now: datetime) -> None:
        self._move_to(JobStatus.IN_REPAIR, now)

    def finish(self, notes: str | None, now: datetime) -> None:
        self._move_to(JobStatus.FINISHED, now)
        self.repair_notes = notes

    def _move_to(self, target: JobStatus, now: datetime) -> None:
        ensure_transition(self.status, target)
        self.status = target
        self.status_history[target] = now
