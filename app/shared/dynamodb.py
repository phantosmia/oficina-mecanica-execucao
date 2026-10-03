"""Acesso à tabela DynamoDB da Execução (ADR-0009, em oficina-mecanica-fiap).

*Single-table design*, o mesmo formato de chave do Catálogo:

| Item                   | pk                    | gsi1pk           | gsi1sk                        |
|------------------------|-----------------------|------------------|-------------------------------|
| OS na execução         | `JOB#<order_id>`      | `QUEUE#<status>` | `<entrou_no_status>#<order>`  |
| Mensagem processada    | `MSG#<message_id>`    | —                | —                             |
| Outbox                 | `OUTBOX#<message_id>` | `OUTBOX`         | `<occurred_at>#<message_id>`  |

Cada OS é um documento só, com o diagnóstico (itens e preços), as notas do
mecânico e o horário de cada etapa. O GSI1 é a fila: lista as OS de um
status na ordem em que chegaram nele. A mudança de status, a resposta na
outbox e o registro da mensagem processada vão numa única
`TransactWriteItems`.

`TABLE_DEFINITION` é a fonte da verdade do schema para o LocalStack e para os
testes (moto); o Terraform do serviço (`infra/`) precisa espelhá-la.
"""

from decimal import Decimal
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key

from app.shared.settings import settings

GSI1_NAME = "gsi1"

TABLE_DEFINITION: dict[str, Any] = {
    "AttributeDefinitions": [
        {"AttributeName": "pk", "AttributeType": "S"},
        {"AttributeName": "gsi1pk", "AttributeType": "S"},
        {"AttributeName": "gsi1sk", "AttributeType": "S"},
    ],
    "KeySchema": [{"AttributeName": "pk", "KeyType": "HASH"}],
    "GlobalSecondaryIndexes": [
        {
            "IndexName": GSI1_NAME,
            "KeySchema": [
                {"AttributeName": "gsi1pk", "KeyType": "HASH"},
                {"AttributeName": "gsi1sk", "KeyType": "RANGE"},
            ],
            "Projection": {"ProjectionType": "ALL"},
        }
    ],
    "BillingMode": "PAY_PER_REQUEST",
}


def get_dynamodb_client() -> Any:
    return boto3.client("dynamodb", region_name=settings.aws_region)


def get_table() -> Any:
    return boto3.resource("dynamodb", region_name=settings.aws_region).Table(settings.table_name)


def create_table_if_missing(table_name: str) -> None:
    """Cria a tabela com `TABLE_DEFINITION` se ainda não existir (LocalStack/testes)."""
    client = get_dynamodb_client()
    if table_name in client.list_tables()["TableNames"]:
        return
    client.create_table(TableName=table_name, **TABLE_DEFINITION)
    client.get_waiter("table_exists").wait(TableName=table_name)


def to_dynamo_number(value: float | int) -> Decimal:
    """O DynamoDB não aceita `float` (só `Decimal`); `str()` evita herdar o
    erro de representação binária do float (ex.: 0.1 → 0.1000000000000000055)."""
    return Decimal(str(value))


def query_gsi1(table: Any, partition: str) -> list[dict[str, Any]]:
    """Todos os itens de uma partição do GSI1, já ordenados por `gsi1sk`, seguindo a paginação."""
    items: list[dict[str, Any]] = []
    kwargs: dict[str, Any] = {
        "IndexName": GSI1_NAME,
        "KeyConditionExpression": Key("gsi1pk").eq(partition),
    }
    while True:
        response = table.query(**kwargs)
        items.extend(response["Items"])
        if "LastEvaluatedKey" not in response:
            return items
        kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
