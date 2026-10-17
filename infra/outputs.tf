output "cluster_name" {
  description = "Cluster EKS onde o serviço é implantado."
  value       = data.terraform_remote_state.kubernetes.outputs.cluster_name
}

output "ecr_repository_url" {
  description = "Repositório ECR da imagem do serviço."
  value       = aws_ecr_repository.service.repository_url
}

output "events_topic_arn" {
  description = "Tópico SNS de eventos do serviço."
  value       = aws_sns_topic.events.arn
}

output "commands_queue_url" {
  description = "Fila SQS de comandos da saga."
  value       = aws_sqs_queue.commands.url
}

output "table_name" {
  description = "Tabela DynamoDB do serviço."
  value       = aws_dynamodb_table.main.name
}
