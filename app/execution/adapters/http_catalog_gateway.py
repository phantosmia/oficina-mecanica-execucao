import httpx

from app.shared.exceptions import CatalogUnavailableError
from app.execution.domain.ports import CatalogItem, CatalogLookup, ICatalogGateway


class HttpCatalogGateway(ICatalogGateway):
    """Cliente do `POST /catalog/lookup` do serviço de Catálogo.

    Timeout curto de propósito: é uma chamada síncrona no meio da ação do
    mecânico. Se o Catálogo não responder, a conclusão do diagnóstico falha
    com 503 e nada é gravado (o mecânico tenta de novo)."""

    def __init__(self, base_url: str, timeout_seconds: float, transport: httpx.BaseTransport | None = None) -> None:
        self._client = httpx.Client(base_url=base_url, timeout=timeout_seconds, transport=transport)

    def lookup(self, service_ids: list[str], part_ids: list[str]) -> CatalogLookup:
        try:
            response = self._client.post("/catalog/lookup", json={"service_ids": service_ids, "part_ids": part_ids})
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise CatalogUnavailableError("Catálogo indisponível; tente concluir o diagnóstico de novo.") from error
        body = response.json()
        return CatalogLookup(
            services={s["id"]: CatalogItem(s["id"], s["name"], float(s["base_price"]), bool(s["active"])) for s in body["services"]},
            parts={p["id"]: CatalogItem(p["id"], p["name"], float(p["unit_price"]), bool(p["active"])) for p in body["parts"]},
            missing_service_ids=list(body["missing_service_ids"]),
            missing_part_ids=list(body["missing_part_ids"]),
        )
