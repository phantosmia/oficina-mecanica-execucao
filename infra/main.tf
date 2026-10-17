locals {
  service = "execucao"
  prefix  = "oficina-${var.environment}"

  common_tags = {
    Project     = "oficina-mecanica-fiap"
    Service     = local.service
    Environment = var.environment
    ManagedBy   = "Terraform"
    Course      = "FIAP"
  }
}

# Plataforma compartilhada: o cluster EKS (oficina-mecanica-infra-kubernetes)
# é aplicado antes deste repositório; o nome do cluster vira output para o
# workflow de deploy.
data "terraform_remote_state" "kubernetes" {
  backend = "s3"

  config = {
    bucket = var.tf_state_bucket
    key    = "kubernetes/${var.environment}/terraform.tfstate"
    region = var.tf_state_region
  }
}

# Imagem do serviço. Um repositório por ambiente, para que destruir um
# ambiente não apague as imagens de outro.
resource "aws_ecr_repository" "service" {
  name                 = "${local.prefix}-${local.service}"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "service" {
  repository = aws_ecr_repository.service.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Mantém as 10 imagens mais recentes"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 10
      }
      action = { type = "expire" }
    }]
  })
}
