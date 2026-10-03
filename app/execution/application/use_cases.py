"""Ações do mecânico (API REST). Cada uma muda a etapa da OS e publica o
evento correspondente para o orquestrador (docs/saga.md)."""

from datetime import UTC, datetime

from app.shared.events import Envelope
from app.shared.exceptions import DomainError, NotFoundError
from app.execution.domain.entities import DiagnosedItem, Diagnosis, ExecutionJob
from app.execution.domain.ports import ICatalogGateway, IExecutionRepository
from app.execution.domain.value_objects import JobStatus, ensure_transition

# Etapas que aparecem na fila por padrão (as que ainda têm trabalho a fazer).
ACTIVE_STATUSES = [JobStatus.AWAITING_DIAGNOSIS, JobStatus.IN_DIAGNOSIS, JobStatus.AWAITING_REPAIR, JobStatus.IN_REPAIR]


def _event(job: ExecutionJob, event_type: str, payload: dict | None = None) -> Envelope:
    return Envelope(type=event_type, payload=payload or {}, saga_id=job.saga_id, order_id=job.order_id)


def _get(repo: IExecutionRepository, order_id: int) -> ExecutionJob:
    job = repo.get(order_id)
    if job is None:
        raise NotFoundError("OS na execução", order_id)
    return job


class ListQueueUseCase:
    def __init__(self, repo: IExecutionRepository) -> None:
        self._repo = repo

    def execute(self, statuses: list[JobStatus] | None = None) -> list[ExecutionJob]:
        jobs: list[ExecutionJob] = []
        for status in statuses or ACTIVE_STATUSES:
            jobs.extend(self._repo.list_by_status(status))
        return jobs


class GetJobUseCase:
    def __init__(self, repo: IExecutionRepository) -> None:
        self._repo = repo

    def execute(self, order_id: int) -> ExecutionJob:
        return _get(self._repo, order_id)


class StartDiagnosisUseCase:
    def __init__(self, repo: IExecutionRepository) -> None:
        self._repo = repo

    def execute(self, order_id: int) -> ExecutionJob:
        job = _get(self._repo, order_id)
        previous = job.status
        job.start_diagnosis(datetime.now(UTC))
        self._repo.save(job, expected_status=previous, events=[_event(job, "DiagnosticoIniciado")])
        return job


class CompleteDiagnosisUseCase:
    """O mecânico informa o que a OS precisa. Os itens são validados no
    Catálogo (REST síncrono, ADR-0010) e os preços são copiados de lá."""

    def __init__(self, repo: IExecutionRepository, catalog: ICatalogGateway) -> None:
        self._repo = repo
        self._catalog = catalog

    def execute(self, order_id: int, notes: str, services: dict[str, int], parts: dict[str, int]) -> ExecutionJob:
        job = _get(self._repo, order_id)
        # Checado antes de consultar o Catálogo, para não fazer a chamada à toa.
        ensure_transition(job.status, JobStatus.DIAGNOSED)
        if any(q <= 0 for q in [*services.values(), *parts.values()]):
            raise DomainError("As quantidades devem ser maiores que zero.")

        lookup = self._catalog.lookup(list(services), list(parts))
        problems = [f"serviço {i} não existe no catálogo" for i in lookup.missing_service_ids]
        problems += [f"peça {i} não existe no catálogo" for i in lookup.missing_part_ids]
        problems += [f"serviço {s.name} está desativado" for s in lookup.services.values() if not s.active]
        problems += [f"peça {p.name} está desativada" for p in lookup.parts.values() if not p.active]
        if problems:
            raise DomainError("Itens inválidos no diagnóstico: " + "; ".join(problems) + ".")

        diagnosis = Diagnosis(
            notes=notes,
            services=[DiagnosedItem(i, lookup.services[i].name, q, lookup.services[i].price) for i, q in services.items()],
            parts=[DiagnosedItem(i, lookup.parts[i].name, q, lookup.parts[i].price) for i, q in parts.items()],
        )
        job.complete_diagnosis(diagnosis, datetime.now(UTC))
        self._repo.save(job, expected_status=JobStatus.IN_DIAGNOSIS, events=[_event(job, "DiagnosticoConcluido", diagnosis_payload(diagnosis))])
        return job


def diagnosis_payload(diagnosis: Diagnosis) -> dict:
    """Payload do `DiagnosticoConcluido`: o que a saga usa para reservar as
    peças (Estoque) e gerar o orçamento (Orçamento & Pagamento)."""

    def items(entries: list[DiagnosedItem], key: str) -> list[dict]:
        return [
            {key: i.item_id, "name": i.name, "quantity": i.quantity, "unit_price": i.unit_price, "subtotal": i.subtotal}
            for i in entries
        ]

    return {
        "notes": diagnosis.notes,
        "services": items(diagnosis.services, "service_id"),
        "parts": items(diagnosis.parts, "part_id"),
        "labor_total": diagnosis.labor_total,
        "parts_total": diagnosis.parts_total,
        "total": diagnosis.total,
    }


class StartRepairUseCase:
    def __init__(self, repo: IExecutionRepository) -> None:
        self._repo = repo

    def execute(self, order_id: int) -> ExecutionJob:
        job = _get(self._repo, order_id)
        previous = job.status
        job.start_repair(datetime.now(UTC))
        self._repo.save(job, expected_status=previous, events=[_event(job, "ReparoIniciado")])
        return job


class FinishRepairUseCase:
    def __init__(self, repo: IExecutionRepository) -> None:
        self._repo = repo

    def execute(self, order_id: int, notes: str | None) -> ExecutionJob:
        job = _get(self._repo, order_id)
        previous = job.status
        job.finish(notes, datetime.now(UTC))
        self._repo.save(job, expected_status=previous, events=[_event(job, "ExecucaoFinalizada", {"notes": notes})])
        return job
