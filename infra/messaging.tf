# Mensageria do serviço (RFC-0007, contrato em docs/saga.md do
# oficina-mecanica-fiap): cada serviço cria o próprio tópico de eventos, a
# própria fila de comandos e as filas com que assina tópicos de outros
# serviços. Toda fila tem uma DLQ.

resource "aws_sns_topic" "events" {
  name = "${local.prefix}-execucao-eventos"
}

# Comandos do orquestrador da saga (OS Service). O OS Service envia pela
# API do SQS com a role dos nodes do EKS, na mesma conta: não precisa de
# queue policy.
resource "aws_sqs_queue" "commands_dlq" {
  name                      = "${local.prefix}-execucao-comandos-dlq"
  message_retention_seconds = 1209600
}

resource "aws_sqs_queue" "commands" {
  name = "${local.prefix}-execucao-comandos"

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.commands_dlq.arn
    maxReceiveCount     = var.max_receive_count
  })
}
