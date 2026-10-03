"""Participação da Execução na saga da OS (docs/saga.md e ADR-0010, no
repositório oficina-mecanica-fiap): o orquestrador manda a OS para a fila de
diagnóstico e, depois do pagamento, para a fila de reparo.

Mesmas regras dos outros participantes: idempotência por `message_id`,
comando reenviado devolve a mesma resposta sem repetir o efeito, falha de
negócio vira evento (`EnfileiramentoFalhou`), exceção só para falha técnica.
"""

import logging
from datetime import UTC, datetime

from app.shared.events import Envelope
from app.execution.domain.entities import ExecutionJob, Vehicle
from app.execution.domain.ports import AlreadyProcessedError, IExecutionRepository
from app.execution.domain.value_objects import JobStatus

logger = logging.getLogger(__name__)

# Etapas em que o reparo já foi enfileirado: um EnfileirarReparo repetido só confirma de novo.
_REPAIR_ALREADY_QUEUED = {JobStatus.AWAITING_REPAIR, JobStatus.IN_REPAIR, JobStatus.FINISHED}


def _reply(command: Envelope, event_type: str, payload: dict | None = None) -> Envelope:
    return Envelope(type=event_type, payload=payload or {}, saga_id=command.saga_id, order_id=command.order_id)


def _failure(command: Envelope, stage: str, reason: str) -> Envelope:
    return _reply(command, "EnfileiramentoFalhou", {"etapa": stage, "reason": reason})


class EnqueueDiagnosisUseCase:
    """`EnfileirarDiagnostico`: a OS recém-aberta entra na fila de diagnóstico."""

    def __init__(self, repo: IExecutionRepository) -> None:
        self._repo = repo

    def execute(self, command: Envelope) -> None:
        if self._repo.is_processed(command.message_id):
            return
        try:
            self._handle(command)
        except AlreadyProcessedError:
            logger.info("mensagem já processada message_id=%s", command.message_id)

    def _handle(self, command: Envelope) -> None:
        payload = command.payload
        problem = str(payload.get("problem_description") or "").strip()
        if command.order_id is None or not command.saga_id or not problem:
            self._repo.reply([_failure(command, "diagnostico", "payload_invalido")], command.message_id)
            return

        existing = self._repo.get(command.order_id)
        if existing is not None:
            reply = (
                _reply(command, "DiagnosticoEnfileirado")
                if existing.saga_id == command.saga_id
                else _failure(command, "diagnostico", "os_ja_esta_na_execucao")
            )
            self._repo.reply([reply], command.message_id)
            return

        vehicle_data = payload.get("vehicle") or {}
        vehicle = Vehicle(
            plate=str(vehicle_data["plate"]),
            brand=vehicle_data.get("brand"),
            model=vehicle_data.get("model"),
            year=vehicle_data.get("year"),
        ) if vehicle_data.get("plate") else None
        job = ExecutionJob.enqueue_for_diagnosis(command.order_id, command.saga_id, problem, vehicle, datetime.now(UTC))
        self._repo.save(job, expected_status=None, events=[_reply(command, "DiagnosticoEnfileirado")], message_id=command.message_id)


class EnqueueRepairUseCase:
    """`EnfileirarReparo`: depois do pagamento, a OS diagnosticada entra na fila
    de reparo. É o ponto sem volta da saga (ADR-0010)."""

    def __init__(self, repo: IExecutionRepository) -> None:
        self._repo = repo

    def execute(self, command: Envelope) -> None:
        if self._repo.is_processed(command.message_id):
            return
        try:
            self._handle(command)
        except AlreadyProcessedError:
            logger.info("mensagem já processada message_id=%s", command.message_id)

    def _handle(self, command: Envelope) -> None:
        job = self._repo.get(command.order_id) if command.order_id is not None else None
        if job is None:
            self._repo.reply([_failure(command, "reparo", "os_nao_encontrada")], command.message_id)
            return
        if job.status in _REPAIR_ALREADY_QUEUED:
            self._repo.reply([_reply(command, "ReparoEnfileirado")], command.message_id)
            return
        if job.status != JobStatus.DIAGNOSED:
            self._repo.reply([_failure(command, "reparo", f"status_{job.status.value}")], command.message_id)
            return
        job.enqueue_for_repair(datetime.now(UTC))
        self._repo.save(job, expected_status=JobStatus.DIAGNOSED, events=[_reply(command, "ReparoEnfileirado")], message_id=command.message_id)
