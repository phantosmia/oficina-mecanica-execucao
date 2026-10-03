from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.messaging.dispatcher import Dispatcher
from app.execution.adapters.dynamodb_repository import DynamoDBExecutionRepository
from app.execution.domain.entities import DiagnosedItem, Diagnosis, ExecutionJob
from tests.conftest import (
    ALINHAMENTO, FILTRO, OLEO, PECA_DESATIVADA, TROCA_OLEO, FakeCatalog, command_msg, enqueue_diagnosis, make_token, outbox,
)


def diagnose(repo: DynamoDBExecutionRepository, order_id: int = 42) -> None:
    """Coloca uma OS direto em `diagnostico_concluido` (sem passar pela API)."""
    now = datetime.now(UTC)
    job = ExecutionJob.enqueue_for_diagnosis(order_id, f"saga-{order_id}", "Barulho", None, now)
    job.start_diagnosis(now)
    job.complete_diagnosis(Diagnosis("ok", [DiagnosedItem(TROCA_OLEO, "Troca de óleo", 1, 150.0)], []), now)
    repo.save(job, expected_status=None, events=[])


def post(client: TestClient, path: str, headers: dict[str, str], json: dict | None = None):  # noqa: ANN201
    return client.post(path, json=json or {}, headers=headers)


ROUTES = [
    ("get", "/jobs"),
    ("get", "/jobs/42"),
    ("post", "/jobs/42/diagnosis/start"),
    ("post", "/jobs/42/diagnosis/complete"),
    ("post", "/jobs/42/repair/start"),
    ("post", "/jobs/42/repair/finish"),
]


@pytest.mark.parametrize(("method", "path"), ROUTES)
def test_routes_require_admin(client: TestClient, method: str, path: str) -> None:
    assert getattr(client, method)(path).status_code == 401
    other = {"Authorization": f"Bearer {make_token('12345678909')}"}
    assert getattr(client, method)(path, headers=other).status_code == 401


def test_full_mechanic_flow(client: TestClient, admin_headers: dict[str, str], dispatcher: Dispatcher, catalog: FakeCatalog) -> None:
    enqueue_diagnosis(dispatcher)

    assert post(client, "/jobs/42/diagnosis/start", admin_headers).json()["status"] == "em_diagnostico"

    completed = post(
        client,
        "/jobs/42/diagnosis/complete",
        admin_headers,
        {
            "notes": "Óleo vencido e filtro saturado",
            "services": [{"id": TROCA_OLEO, "quantity": 1}],
            "parts": [{"id": OLEO, "quantity": 3}, {"id": FILTRO, "quantity": 1}, {"id": OLEO, "quantity": 1}],
        },
    )
    assert completed.status_code == 200
    diagnosis = completed.json()["diagnosis"]
    assert (diagnosis["labor_total"], diagnosis["parts_total"], diagnosis["total"]) == (150.0, 205.5, 355.5)
    assert completed.json()["status"] == "diagnostico_concluido"

    dispatcher.handle(command_msg("EnfileirarReparo"))
    assert post(client, "/jobs/42/repair/start", admin_headers).json()["status"] == "em_reparo"
    finished = post(client, "/jobs/42/repair/finish", admin_headers, {"notes": "Troca feita"})
    assert (finished.json()["status"], finished.json()["repair_notes"]) == ("finalizada", "Troca feita")
    assert list(client.get("/jobs/42", headers=admin_headers).json()["status_history"]) == [
        "aguardando_diagnostico", "em_diagnostico", "diagnostico_concluido", "aguardando_reparo", "em_reparo", "finalizada",
    ]

    events = outbox()
    assert [e["type"] for e in events] == [
        "DiagnosticoEnfileirado", "DiagnosticoIniciado", "DiagnosticoConcluido",
        "ReparoEnfileirado", "ReparoIniciado", "ExecucaoFinalizada",
    ]
    assert all((e["saga_id"], e["order_id"]) == ("saga-42", 42) for e in events)
    assert events[2]["payload"] == {
        "notes": "Óleo vencido e filtro saturado",
        "services": [{"service_id": TROCA_OLEO, "name": "Troca de óleo", "quantity": 1, "unit_price": 150.0, "subtotal": 150.0}],
        "parts": [
            {"part_id": OLEO, "name": "Óleo 5W30", "quantity": 4, "unit_price": 45.0, "subtotal": 180.0},
            {"part_id": FILTRO, "name": "Filtro de óleo", "quantity": 1, "unit_price": 25.5, "subtotal": 25.5},
        ],
        "labor_total": 150.0,
        "parts_total": 205.5,
        "total": 355.5,
    }
    assert events[-1]["payload"] == {"notes": "Troca feita"}


def test_queue_lists_active_jobs_in_arrival_order(client: TestClient, admin_headers: dict[str, str], dispatcher: Dispatcher) -> None:
    for order_id in (3, 1, 2):
        enqueue_diagnosis(dispatcher, order_id=order_id)
    post(client, "/jobs/1/diagnosis/start", admin_headers)

    queue = client.get("/jobs", headers=admin_headers).json()
    assert [(j["order_id"], j["status"]) for j in queue] == [
        (3, "aguardando_diagnostico"), (2, "aguardando_diagnostico"), (1, "em_diagnostico"),
    ]
    only_in_diagnosis = client.get("/jobs", params={"status": "em_diagnostico"}, headers=admin_headers).json()
    assert [j["order_id"] for j in only_in_diagnosis] == [1]


def test_invalid_items_are_rejected_without_changing_the_job(
    client: TestClient, admin_headers: dict[str, str], dispatcher: Dispatcher, catalog: FakeCatalog
) -> None:
    enqueue_diagnosis(dispatcher)
    post(client, "/jobs/42/diagnosis/start", admin_headers)

    response = post(
        client, "/jobs/42/diagnosis/complete", admin_headers,
        {"notes": "x", "services": [{"id": "svc-fantasma", "quantity": 1}], "parts": [{"id": PECA_DESATIVADA, "quantity": 1}]},
    )

    assert response.status_code == 422
    assert "serviço svc-fantasma não existe no catálogo" in response.json()["detail"]
    assert "peça Peça antiga está desativada" in response.json()["detail"]
    assert client.get("/jobs/42", headers=admin_headers).json()["status"] == "em_diagnostico"


def test_diagnosis_needs_items(client: TestClient, admin_headers: dict[str, str], dispatcher: Dispatcher, catalog: FakeCatalog) -> None:
    enqueue_diagnosis(dispatcher)
    post(client, "/jobs/42/diagnosis/start", admin_headers)
    assert post(client, "/jobs/42/diagnosis/complete", admin_headers, {"notes": "nada"}).status_code == 422
    bad_quantity = {"notes": "x", "services": [{"id": ALINHAMENTO, "quantity": 0}]}
    assert post(client, "/jobs/42/diagnosis/complete", admin_headers, bad_quantity).status_code == 422


def test_wrong_stage_is_conflict_and_skips_catalog(
    client: TestClient, admin_headers: dict[str, str], dispatcher: Dispatcher, catalog: FakeCatalog
) -> None:
    enqueue_diagnosis(dispatcher)

    complete = post(client, "/jobs/42/diagnosis/complete", admin_headers, {"notes": "x", "services": [{"id": TROCA_OLEO, "quantity": 1}]})
    assert complete.status_code == 409
    assert catalog.calls == 0
    assert post(client, "/jobs/42/repair/start", admin_headers).status_code == 409
    assert post(client, "/jobs/42/repair/finish", admin_headers).status_code == 409


def test_two_mechanics_cannot_take_the_same_job(
    client: TestClient, admin_headers: dict[str, str], dispatcher: Dispatcher, repo: DynamoDBExecutionRepository
) -> None:
    enqueue_diagnosis(dispatcher)
    stale = repo.get(42)  # o segundo mecânico leu antes do primeiro gravar
    assert post(client, "/jobs/42/diagnosis/start", admin_headers).status_code == 200

    from app.execution.application.use_cases import StartDiagnosisUseCase
    from app.shared.exceptions import ConcurrencyError

    class StaleRepo(DynamoDBExecutionRepository):
        def get(self, order_id: int):  # noqa: ANN201
            return stale

    with pytest.raises(ConcurrencyError):
        StartDiagnosisUseCase(StaleRepo(repo._table)).execute(42)
    assert [e["type"] for e in outbox()].count("DiagnosticoIniciado") == 1


def test_not_found(client: TestClient, admin_headers: dict[str, str], catalog: FakeCatalog) -> None:
    assert client.get("/jobs/999", headers=admin_headers).status_code == 404
    for _, path in ROUTES[2:]:
        body = {"notes": "x", "services": [{"id": TROCA_OLEO, "quantity": 1}]}
        assert post(client, path.replace("42", "999"), admin_headers, body).status_code == 404
