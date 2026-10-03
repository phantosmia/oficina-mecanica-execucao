from collections import Counter

from fastapi import APIRouter, Depends, Query

from app.shared.dependencies import get_current_admin
from app.shared.dynamodb import get_table
from app.shared.http_errors import domain_error_handler
from app.shared.settings import settings
from app.execution.adapters.dynamodb_repository import DynamoDBExecutionRepository
from app.execution.adapters.http_catalog_gateway import HttpCatalogGateway
from app.execution.adapters.presenter import to_response
from app.execution.application.use_cases import (
    CompleteDiagnosisUseCase,
    FinishRepairUseCase,
    GetJobUseCase,
    ListQueueUseCase,
    StartDiagnosisUseCase,
    StartRepairUseCase,
)
from app.execution.domain.ports import ICatalogGateway, IExecutionRepository
from app.execution.domain.value_objects import JobStatus
from app.execution.schemas import DiagnosisRequest, FinishRequest, ItemRequest, JobRead

# Ações do mecânico. Usam o JWT de admin emitido pelo OS Service (o sistema
# ainda não tem um perfil separado de mecânico).
router = APIRouter(prefix="/jobs", tags=["execution"], dependencies=[Depends(get_current_admin)])


def get_repo() -> IExecutionRepository:
    return DynamoDBExecutionRepository(get_table())


def get_catalog() -> ICatalogGateway:
    return HttpCatalogGateway(settings.catalog_base_url, settings.catalog_timeout_seconds)


def _quantities(items: list[ItemRequest]) -> dict[str, int]:
    totals = Counter[str]()
    for item in items:
        totals[item.id] += item.quantity
    return dict(totals)


@router.get("", response_model=list[JobRead])
def list_queue(
    status: list[JobStatus] | None = Query(default=None, description="Padrão: etapas com trabalho pendente"),
    repo: IExecutionRepository = Depends(get_repo),
) -> list[JobRead]:
    """A fila da oficina: OS de cada etapa, na ordem em que chegaram nela."""
    return [to_response(j) for j in ListQueueUseCase(repo).execute(status)]


@router.get("/{order_id}", response_model=JobRead)
def get_job(order_id: int, repo: IExecutionRepository = Depends(get_repo)) -> JobRead:
    with domain_error_handler():
        return to_response(GetJobUseCase(repo).execute(order_id))


@router.post("/{order_id}/diagnosis/start", response_model=JobRead)
def start_diagnosis(order_id: int, repo: IExecutionRepository = Depends(get_repo)) -> JobRead:
    with domain_error_handler():
        return to_response(StartDiagnosisUseCase(repo).execute(order_id))


@router.post("/{order_id}/diagnosis/complete", response_model=JobRead)
def complete_diagnosis(
    order_id: int,
    payload: DiagnosisRequest,
    repo: IExecutionRepository = Depends(get_repo),
    catalog: ICatalogGateway = Depends(get_catalog),
) -> JobRead:
    """Registra o que a OS precisa. Serviços e peças são validados no
    Catálogo e os preços copiados de lá; a saga segue para reserva e orçamento."""
    with domain_error_handler():
        job = CompleteDiagnosisUseCase(repo, catalog).execute(
            order_id, payload.notes, _quantities(payload.services), _quantities(payload.parts)
        )
        return to_response(job)


@router.post("/{order_id}/repair/start", response_model=JobRead)
def start_repair(order_id: int, repo: IExecutionRepository = Depends(get_repo)) -> JobRead:
    with domain_error_handler():
        return to_response(StartRepairUseCase(repo).execute(order_id))


@router.post("/{order_id}/repair/finish", response_model=JobRead)
def finish_repair(order_id: int, payload: FinishRequest, repo: IExecutionRepository = Depends(get_repo)) -> JobRead:
    with domain_error_handler():
        return to_response(FinishRepairUseCase(repo).execute(order_id, payload.notes))
