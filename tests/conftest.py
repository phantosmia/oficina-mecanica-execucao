import os

_ACCOUNT = "123456789012"
os.environ.update(
    {
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_SECURITY_TOKEN": "testing",
        "AWS_SESSION_TOKEN": "testing",
        "AWS_DEFAULT_REGION": "us-east-1",
        "AWS_REGION": "us-east-1",
        "EXECUCAO_TABLE_NAME": "oficina-execucao-test",
        "EXECUCAO_EVENTS_TOPIC_ARN": f"arn:aws:sns:us-east-1:{_ACCOUNT}:execucao-eventos",
        "EXECUCAO_COMMANDS_QUEUE_URL": f"https://sqs.us-east-1.amazonaws.com/{_ACCOUNT}/execucao-comandos",
        "WORKER_WAIT_SECONDS": "0",
        "JWT_SECRET_KEY": "test-secret-key",
        "ADMIN_USERNAME": "admin",
        "CATALOG_BASE_URL": "http://catalogo.test",
    }
)
os.environ.pop("AWS_ENDPOINT_URL", None)

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from moto import mock_aws

from app.main import app
from app.messaging.dispatcher import Dispatcher
from app.shared.dynamodb import get_table, query_gsi1
from app.shared.events import Envelope
from app.shared.outbox import OUTBOX_PARTITION
from app.execution.adapters.dynamodb_repository import DynamoDBExecutionRepository
from app.execution.controller import get_catalog
from app.execution.domain.ports import CatalogItem, CatalogLookup, ICatalogGateway

# IDs no formato do Catálogo (dados de exemplo).
TROCA_OLEO, ALINHAMENTO = "svc-troca-oleo", "svc-alinhamento"
OLEO, FILTRO, PECA_DESATIVADA = "part-oleo", "part-filtro", "part-antiga"


class FakeCatalog(ICatalogGateway):
    def __init__(self) -> None:
        self.services = {
            TROCA_OLEO: CatalogItem(TROCA_OLEO, "Troca de óleo", 150.0, True),
            ALINHAMENTO: CatalogItem(ALINHAMENTO, "Alinhamento", 120.0, True),
        }
        self.parts = {
            OLEO: CatalogItem(OLEO, "Óleo 5W30", 45.0, True),
            FILTRO: CatalogItem(FILTRO, "Filtro de óleo", 25.5, True),
            PECA_DESATIVADA: CatalogItem(PECA_DESATIVADA, "Peça antiga", 10.0, False),
        }
        self.calls = 0

    def lookup(self, service_ids: list[str], part_ids: list[str]) -> CatalogLookup:
        self.calls += 1
        return CatalogLookup(
            services={i: self.services[i] for i in service_ids if i in self.services},
            parts={i: self.parts[i] for i in part_ids if i in self.parts},
            missing_service_ids=[i for i in service_ids if i not in self.services],
            missing_part_ids=[i for i in part_ids if i not in self.parts],
        )


@pytest.fixture(autouse=True)
def aws() -> Iterator[None]:
    with mock_aws():
        from scripts.bootstrap_local import bootstrap

        bootstrap()
        yield


@pytest.fixture
def repo(aws: None) -> DynamoDBExecutionRepository:
    return DynamoDBExecutionRepository(get_table())


@pytest.fixture
def dispatcher() -> Dispatcher:
    return Dispatcher(lambda: DynamoDBExecutionRepository(get_table()))


@pytest.fixture
def catalog() -> Iterator[FakeCatalog]:
    fake = FakeCatalog()
    app.dependency_overrides[get_catalog] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_catalog, None)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def make_token(subject: str = "admin") -> str:
    return jwt.encode({"sub": subject, "exp": datetime.now(UTC) + timedelta(minutes=5)}, "test-secret-key", algorithm="HS256")


@pytest.fixture
def admin_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token()}"}


def command_msg(message_type: str, order_id: int = 42, saga_id: str = "saga-42", **payload: Any) -> Envelope:
    return Envelope(type=message_type, payload=dict(payload), saga_id=saga_id, order_id=order_id)


def enqueue_diagnosis(dispatcher: Dispatcher, order_id: int = 42, saga_id: str | None = None) -> Envelope:
    command = command_msg(
        "EnfileirarDiagnostico",
        order_id=order_id,
        saga_id=saga_id or f"saga-{order_id}",
        problem_description="Barulho no freio dianteiro",
        vehicle={"plate": "ABC1D23", "brand": "Fiat", "model": "Uno", "year": 2015},
    )
    dispatcher.handle(command)
    return command


def outbox() -> list[dict]:
    """Envelopes pendentes na outbox, em ordem de gravação."""
    return [json.loads(i["envelope"]) for i in query_gsi1(get_table(), OUTBOX_PARTITION)]
