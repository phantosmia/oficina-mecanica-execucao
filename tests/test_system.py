import boto3
from fastapi.testclient import TestClient

from app.shared.settings import settings


def test_health_and_ready(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/ready").json()["table_status"] == "ACTIVE"
    boto3.client("dynamodb", region_name="us-east-1").delete_table(TableName=settings.table_name)
    assert client.get("/ready").status_code == 503
