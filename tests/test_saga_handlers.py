from app.messaging.dispatcher import Dispatcher
from app.execution.adapters.dynamodb_repository import DynamoDBExecutionRepository
from app.execution.domain.value_objects import JobStatus
from tests.conftest import command_msg, enqueue_diagnosis, outbox


def test_enqueue_diagnosis_creates_job_and_replies(dispatcher: Dispatcher, repo: DynamoDBExecutionRepository) -> None:
    command = enqueue_diagnosis(dispatcher)

    job = repo.get(42)
    assert (job.status, job.saga_id, job.problem_description) == (JobStatus.AWAITING_DIAGNOSIS, "saga-42", "Barulho no freio dianteiro")
    assert (job.vehicle.plate, job.vehicle.year) == ("ABC1D23", 2015)
    [reply] = outbox()
    assert (reply["type"], reply["saga_id"], reply["order_id"]) == ("DiagnosticoEnfileirado", command.saga_id, 42)


def test_redelivery_is_ignored(dispatcher: Dispatcher) -> None:
    command = enqueue_diagnosis(dispatcher)
    dispatcher.handle(command)
    assert len(outbox()) == 1


def test_resent_command_repeats_reply(dispatcher: Dispatcher) -> None:
    enqueue_diagnosis(dispatcher)
    enqueue_diagnosis(dispatcher)  # novo message_id, mesma saga
    assert [m["type"] for m in outbox()] == ["DiagnosticoEnfileirado", "DiagnosticoEnfileirado"]


def test_order_already_in_execution_for_another_saga_fails(dispatcher: Dispatcher) -> None:
    enqueue_diagnosis(dispatcher)
    enqueue_diagnosis(dispatcher, saga_id="outra-saga")

    failure = outbox()[-1]
    assert failure["type"] == "EnfileiramentoFalhou"
    assert failure["payload"] == {"etapa": "diagnostico", "reason": "os_ja_esta_na_execucao"}


def test_invalid_payload_fails(dispatcher: Dispatcher, repo: DynamoDBExecutionRepository) -> None:
    dispatcher.handle(command_msg("EnfileirarDiagnostico", problem_description="  "))
    assert outbox()[-1]["payload"] == {"etapa": "diagnostico", "reason": "payload_invalido"}
    assert repo.get(42) is None


def test_vehicle_is_optional(dispatcher: Dispatcher, repo: DynamoDBExecutionRepository) -> None:
    dispatcher.handle(command_msg("EnfileirarDiagnostico", problem_description="Luz do motor acesa"))
    assert repo.get(42).vehicle is None


def test_enqueue_repair_requires_completed_diagnosis(dispatcher: Dispatcher) -> None:
    dispatcher.handle(command_msg("EnfileirarReparo"))
    assert outbox()[-1]["payload"] == {"etapa": "reparo", "reason": "os_nao_encontrada"}

    enqueue_diagnosis(dispatcher)
    dispatcher.handle(command_msg("EnfileirarReparo"))
    assert outbox()[-1]["payload"] == {"etapa": "reparo", "reason": "status_aguardando_diagnostico"}


def test_enqueue_repair_after_diagnosis(dispatcher: Dispatcher, repo: DynamoDBExecutionRepository) -> None:
    from tests.test_api import diagnose  # mesma preparação usada pelos testes da API

    diagnose(repo)
    command = command_msg("EnfileirarReparo")
    dispatcher.handle(command)
    dispatcher.handle(command)  # reentrega
    dispatcher.handle(command_msg("EnfileirarReparo"))  # reenvio

    assert repo.get(42).status == JobStatus.AWAITING_REPAIR
    assert [m["type"] for m in outbox()][-2:] == ["ReparoEnfileirado", "ReparoEnfileirado"]


def test_unknown_message_type(dispatcher: Dispatcher) -> None:
    assert dispatcher.handle(command_msg("Desconhecido")) is False
