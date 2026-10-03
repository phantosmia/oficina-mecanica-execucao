import json

import httpx
import pytest

from app.shared.exceptions import CatalogUnavailableError
from app.execution.adapters.http_catalog_gateway import HttpCatalogGateway


def test_lookup_maps_catalog_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/catalog/lookup"
        assert json.loads(request.content) == {"service_ids": ["s1"], "part_ids": ["p1", "p2"]}
        return httpx.Response(200, json={
            "services": [{"id": "s1", "name": "Troca de óleo", "base_price": 150, "active": True, "estimated_minutes": 30}],
            "parts": [{"id": "p1", "name": "Óleo", "unit_price": 45.5, "active": False, "sku": "OLEO"}],
            "missing_service_ids": [],
            "missing_part_ids": ["p2"],
        })

    gateway = HttpCatalogGateway("http://catalogo", 1, transport=httpx.MockTransport(handler))
    result = gateway.lookup(["s1"], ["p1", "p2"])

    assert result.services["s1"].price == 150.0
    assert (result.parts["p1"].price, result.parts["p1"].active) == (45.5, False)
    assert result.missing_part_ids == ["p2"]


@pytest.mark.parametrize(
    "handler",
    [
        lambda request: httpx.Response(500),
        lambda request: (_ for _ in ()).throw(httpx.ConnectTimeout("timeout")),
    ],
)
def test_catalog_failure_becomes_unavailable(handler) -> None:  # noqa: ANN001
    gateway = HttpCatalogGateway("http://catalogo", 1, transport=httpx.MockTransport(handler))
    with pytest.raises(CatalogUnavailableError):
        gateway.lookup(["s1"], [])


def test_catalog_unavailable_is_503_and_nothing_changes(client, admin_headers, dispatcher) -> None:  # noqa: ANN001
    from app.main import app
    from app.execution.controller import get_catalog
    from tests.conftest import enqueue_diagnosis

    enqueue_diagnosis(dispatcher)
    client.post("/jobs/42/diagnosis/start", headers=admin_headers)
    app.dependency_overrides[get_catalog] = lambda: HttpCatalogGateway(
        "http://catalogo", 1, transport=httpx.MockTransport(lambda request: httpx.Response(503))
    )
    try:
        response = client.post(
            "/jobs/42/diagnosis/complete", headers=admin_headers, json={"notes": "x", "services": [{"id": "s1", "quantity": 1}]}
        )
    finally:
        app.dependency_overrides.pop(get_catalog, None)

    assert response.status_code == 503
    assert client.get("/jobs/42", headers=admin_headers).json()["status"] == "em_diagnostico"
