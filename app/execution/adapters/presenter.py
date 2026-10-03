from app.execution.domain.entities import DiagnosedItem, ExecutionJob
from app.execution.schemas import DiagnosedItemRead, DiagnosisRead, JobRead, VehicleRead


def _item(item: DiagnosedItem) -> DiagnosedItemRead:
    return DiagnosedItemRead(id=item.item_id, name=item.name, quantity=item.quantity, unit_price=item.unit_price, subtotal=item.subtotal)


def to_response(job: ExecutionJob) -> JobRead:
    diagnosis = job.diagnosis
    return JobRead(
        order_id=job.order_id,
        saga_id=job.saga_id,
        status=job.status,
        status_since=job.status_since,
        problem_description=job.problem_description,
        vehicle=VehicleRead(**job.vehicle.__dict__) if job.vehicle else None,
        diagnosis=(
            DiagnosisRead(
                notes=diagnosis.notes,
                services=[_item(s) for s in diagnosis.services],
                parts=[_item(p) for p in diagnosis.parts],
                labor_total=diagnosis.labor_total,
                parts_total=diagnosis.parts_total,
                total=diagnosis.total,
            )
            if diagnosis
            else None
        ),
        repair_notes=job.repair_notes,
        status_history={status.value: at for status, at in job.status_history.items()},
    )
