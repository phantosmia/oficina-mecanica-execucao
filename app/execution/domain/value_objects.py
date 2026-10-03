from enum import StrEnum

from app.shared.exceptions import InvalidTransitionError


class JobStatus(StrEnum):
    """Etapas de uma OS dentro da Execução (ADR-0010: diagnóstico antes do
    orçamento, reparo depois do pagamento)."""

    AWAITING_DIAGNOSIS = "aguardando_diagnostico"
    IN_DIAGNOSIS = "em_diagnostico"
    DIAGNOSED = "diagnostico_concluido"   # aguardando orçamento, aprovação e pagamento (fora daqui)
    AWAITING_REPAIR = "aguardando_reparo"
    IN_REPAIR = "em_reparo"
    FINISHED = "finalizada"


ALLOWED_TRANSITIONS: dict[JobStatus, JobStatus | None] = {
    JobStatus.AWAITING_DIAGNOSIS: JobStatus.IN_DIAGNOSIS,
    JobStatus.IN_DIAGNOSIS: JobStatus.DIAGNOSED,
    JobStatus.DIAGNOSED: JobStatus.AWAITING_REPAIR,
    JobStatus.AWAITING_REPAIR: JobStatus.IN_REPAIR,
    JobStatus.IN_REPAIR: JobStatus.FINISHED,
    JobStatus.FINISHED: None,
}


def ensure_transition(current: JobStatus, target: JobStatus) -> None:
    if ALLOWED_TRANSITIONS[current] != target:
        raise InvalidTransitionError(f"Não é possível passar a OS de {current.value} para {target.value}.")
