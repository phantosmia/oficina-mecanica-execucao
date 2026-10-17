# Backend S3 compartilhado pelos repositórios do projeto (criado por
# infra/backend no oficina-mecanica-fiap). O workflow de deploy passa
# bucket, key (<serviço>/<ambiente>/terraform.tfstate), região e tabela de
# lock no `terraform init`.
terraform {
  backend "s3" {}
}
