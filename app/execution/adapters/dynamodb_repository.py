from datetime import datetime
from typing import Any

from botocore.exceptions import ClientError

from app.shared.dynamodb import query_gsi1, to_dynamo_number
from app.shared.events import Envelope
from app.shared.exceptions import ConcurrencyError
from app.shared.outbox import outbox_put
from app.execution.domain.entities import DiagnosedItem, Diagnosis, ExecutionJob, Vehicle
from app.execution.domain.ports import AlreadyProcessedError, IExecutionRepository
from app.execution.domain.value_objects import JobStatus


def _pk(order_id: int) -> str:
    return f"JOB#{order_id}"


def _queue(status: JobStatus) -> str:
    return f"QUEUE#{status.value}"


def _items_to_dynamo(items: list[DiagnosedItem]) -> list[dict[str, Any]]:
    return [
        {"id": i.item_id, "name": i.name, "quantity": i.quantity, "unit_price": to_dynamo_number(i.unit_price)}
        for i in items
    ]


def _items_from_dynamo(items: list[dict[str, Any]]) -> list[DiagnosedItem]:
    return [DiagnosedItem(i["id"], i["name"], int(i["quantity"]), float(i["unit_price"])) for i in items]


def _to_item(job: ExecutionJob) -> dict[str, Any]:
    return {
        "pk": _pk(job.order_id),
        # A fila: OS do mesmo status, na ordem em que entraram nele.
        "gsi1pk": _queue(job.status),
        "gsi1sk": f"{job.status_since.isoformat()}#{job.order_id:012d}",
        "order_id": job.order_id,
        "saga_id": job.saga_id,
        "status": job.status.value,
        "problem_description": job.problem_description,
        "vehicle": (
            {"plate": job.vehicle.plate, "brand": job.vehicle.brand, "model": job.vehicle.model, "year": job.vehicle.year}
            if job.vehicle
            else None
        ),
        "status_history": {status.value: at.isoformat() for status, at in job.status_history.items()},
        "diagnosis": (
            {
                "notes": job.diagnosis.notes,
                "services": _items_to_dynamo(job.diagnosis.services),
                "parts": _items_to_dynamo(job.diagnosis.parts),
            }
            if job.diagnosis
            else None
        ),
        "repair_notes": job.repair_notes,
    }


def _to_entity(item: dict[str, Any]) -> ExecutionJob:
    vehicle = item.get("vehicle")
    diagnosis = item.get("diagnosis")
    return ExecutionJob(
        order_id=int(item["order_id"]),
        saga_id=item["saga_id"],
        problem_description=item["problem_description"],
        vehicle=(
            Vehicle(plate=vehicle["plate"], brand=vehicle.get("brand"), model=vehicle.get("model"),
                    year=int(vehicle["year"]) if vehicle.get("year") is not None else None)
            if vehicle
            else None
        ),
        status=JobStatus(item["status"]),
        # Mapas do DynamoDB não guardam ordem: reordena pela sequência das etapas.
        status_history={
            status: datetime.fromisoformat(item["status_history"][status.value])
            for status in JobStatus
            if status.value in item["status_history"]
        },
        diagnosis=(
            Diagnosis(diagnosis["notes"], _items_from_dynamo(diagnosis["services"]), _items_from_dynamo(diagnosis["parts"]))
            if diagnosis
            else None
        ),
        repair_notes=item.get("repair_notes"),
    )


def _cancellation_codes(error: ClientError) -> list[str]:
    return [reason.get("Code", "None") for reason in error.response.get("CancellationReasons", [])]


class DynamoDBExecutionRepository(IExecutionRepository):
    def __init__(self, table: Any) -> None:
        self._table = table
        self._client = table.meta.client

    def get(self, order_id: int) -> ExecutionJob | None:
        item = self._table.get_item(Key={"pk": _pk(order_id)}).get("Item")
        return _to_entity(item) if item else None

    def list_by_status(self, status: JobStatus) -> list[ExecutionJob]:
        return [_to_entity(i) for i in query_gsi1(self._table, _queue(status))]

    def is_processed(self, message_id: str) -> bool:
        return "Item" in self._table.get_item(Key={"pk": f"MSG#{message_id}"})

    def save(
        self,
        job: ExecutionJob,
        expected_status: JobStatus | None,
        events: list[Envelope],
        message_id: str | None = None,
    ) -> None:
        put: dict[str, Any] = {"TableName": self._table.name, "Item": _to_item(job)}
        if expected_status is None:
            put["ConditionExpression"] = "attribute_not_exists(pk)"
        else:
            put["ConditionExpression"] = "#status = :expected"
            put["ExpressionAttributeNames"] = {"#status": "status"}
            put["ExpressionAttributeValues"] = {":expected": expected_status.value}
        self._transact([{"Put": put}], events, message_id)

    def reply(self, events: list[Envelope], message_id: str) -> None:
        self._transact([], events, message_id)

    def _transact(self, operations: list[dict[str, Any]], events: list[Envelope], message_id: str | None) -> None:
        items = list(operations)
        if message_id is not None:
            # Registro de mensagem processada, com condição: se outra entrega da
            # mesma mensagem já gravou, a transação inteira é cancelada.
            items.append(
                {
                    "Put": {
                        "TableName": self._table.name,
                        "Item": {"pk": f"MSG#{message_id}"},
                        "ConditionExpression": "attribute_not_exists(pk)",
                    }
                }
            )
        items.extend(outbox_put(self._table.name, event) for event in events)
        try:
            self._client.transact_write_items(TransactItems=items)
        except ClientError as error:
            codes = _cancellation_codes(error)

            def failed(index: int) -> bool:
                return index < len(codes) and codes[index] == "ConditionalCheckFailed"

            if message_id is not None and failed(len(operations)):
                raise AlreadyProcessedError(message_id) from error
            if operations and failed(0):
                raise ConcurrencyError("A OS foi alterada por outra operação. Recarregue e tente de novo.") from error
            raise
