variable "environment" {
  description = "Ambiente (homologacao, producao). Entra no nome de todos os recursos e nas keys dos states lidos da plataforma."
  type        = string
}

variable "aws_region" {
  description = "Região AWS dos recursos."
  type        = string
  default     = "us-east-1"
}

variable "tf_state_bucket" {
  description = "Bucket S3 do state remoto, o mesmo dos repositórios de plataforma (lido via terraform_remote_state)."
  type        = string
}

variable "tf_state_region" {
  description = "Região do bucket do state remoto."
  type        = string
  default     = "us-east-1"
}

variable "max_receive_count" {
  description = "Tentativas de processamento de uma mensagem antes de ela ir para a DLQ (RFC-0007)."
  type        = number
  default     = 5
}
