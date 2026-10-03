from typing import Any

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.shared.dynamodb import get_table

router = APIRouter(tags=["system"])


class HealthStatus(BaseModel):
    status: str


class ReadinessStatus(BaseModel):
    status: str
    table: str
    table_status: str


@router.get("/health", response_model=HealthStatus)
def healthcheck() -> HealthStatus:
    return HealthStatus(status="ok")


@router.get("/ready", response_model=ReadinessStatus)
def readiness(table: Any = Depends(get_table)) -> ReadinessStatus:
    """Readiness separada do /health: o pod só recebe tráfego se alcança a
    tabela DynamoDB (credenciais e nome da tabela corretos)."""
    try:
        table_status = table.table_status
    except (BotoCoreError, ClientError) as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="DynamoDB indisponível.") from error
    return ReadinessStatus(status="ok", table=table.name, table_status=table_status)
