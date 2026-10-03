from datetime import UTC, datetime

import pytest

from app.shared.exceptions import DomainError, InvalidTransitionError
from app.execution.domain.entities import DiagnosedItem, Diagnosis, ExecutionJob
from app.execution.domain.value_objects import JobStatus

NOW = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)


def job() -> ExecutionJob:
    return ExecutionJob.enqueue_for_diagnosis(1, "saga-1", "Barulho", None, NOW)


def diagnosis() -> Diagnosis:
    return Diagnosis("Pastilhas gastas", [DiagnosedItem("s", "Revisão de freios", 1, 200.0)], [DiagnosedItem("p", "Pastilha", 2, 180.5)])


def test_full_lifecycle_records_when_each_stage_started() -> None:
    execution = job()
    execution.start_diagnosis(NOW)
    execution.complete_diagnosis(diagnosis(), NOW)
    execution.enqueue_for_repair(NOW)
    execution.start_repair(NOW)
    execution.finish("Trocadas as pastilhas", NOW)

    assert execution.status == JobStatus.FINISHED
    assert list(execution.status_history) == list(JobStatus)
    assert execution.repair_notes == "Trocadas as pastilhas"


def test_stages_cannot_be_skipped() -> None:
    execution = job()
    with pytest.raises(InvalidTransitionError, match="aguardando_diagnostico para em_reparo"):
        execution.start_repair(NOW)
    with pytest.raises(InvalidTransitionError):
        execution.complete_diagnosis(diagnosis(), NOW)


def test_finished_job_is_terminal() -> None:
    execution = job()
    execution.status = JobStatus.FINISHED
    with pytest.raises(InvalidTransitionError):
        execution.start_diagnosis(NOW)


def test_diagnosis_totals() -> None:
    result = diagnosis()
    assert (result.labor_total, result.parts_total, result.total) == (200.0, 361.0, 561.0)


def test_diagnosis_needs_at_least_one_item() -> None:
    with pytest.raises(DomainError, match="pelo menos um serviço ou peça"):
        Diagnosis("Nada encontrado", [], [])
