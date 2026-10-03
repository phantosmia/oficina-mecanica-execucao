import json

import boto3

from app.messaging.dispatcher import Dispatcher, parse_body
from app.messaging.sqs_consumer import SqsConsumer
from app.shared.dynamodb import get_table
from app.shared.outbox import OutboxRelay
from app.shared.settings import settings
from app.shared.sns_publisher import SnsEventPublisher
from tests.conftest import command_msg


def test_command_round_trip(dispatcher: Dispatcher) -> None:
    sqs, sns = boto3.client("sqs", region_name="us-east-1"), boto3.client("sns", region_name="us-east-1")
    orchestrator = sqs.create_queue(QueueName="os-saga-eventos")["QueueUrl"]
    arn = sqs.get_queue_attributes(QueueUrl=orchestrator, AttributeNames=["QueueArn"])["Attributes"]["QueueArn"]
    sns.subscribe(TopicArn=settings.events_topic_arn, Protocol="sqs", Endpoint=arn, Attributes={"RawMessageDelivery": "true"})

    command = command_msg("EnfileirarDiagnostico", order_id=7, saga_id="saga-7", problem_description="Não liga")
    sqs.send_message(QueueUrl=settings.commands_queue_url, MessageBody=json.dumps(command.to_dict()))

    consumer = SqsConsumer([settings.commands_queue_url], dispatcher, wait_seconds=0)
    assert consumer.poll_once() == 1
    assert OutboxRelay(get_table(), SnsEventPublisher(settings.events_topic_arn)).run_once() == 1

    [received] = sqs.receive_message(QueueUrl=orchestrator, MessageAttributeNames=["All"])["Messages"]
    assert json.loads(received["Body"])["type"] == "DiagnosticoEnfileirado"
    assert received["MessageAttributes"]["order_id"]["StringValue"] == "7"


def test_malformed_message_stays_in_queue(dispatcher: Dispatcher) -> None:
    sqs = boto3.client("sqs", region_name="us-east-1")
    sqs.send_message(QueueUrl=settings.commands_queue_url, MessageBody="{}")
    assert SqsConsumer([settings.commands_queue_url], dispatcher, wait_seconds=0).poll_once() == 0


def test_parse_body_unwraps_sns_notification() -> None:
    inner = command_msg("EnfileirarReparo").to_dict()
    assert parse_body(json.dumps({"Type": "Notification", "Message": json.dumps(inner)})).to_dict() == inner
