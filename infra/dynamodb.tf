# Espelha TABLE_DEFINITION de app/shared/dynamodb.py, a fonte da verdade do
# schema (ADR-0009/ADR-0011 do oficina-mecanica-fiap).
resource "aws_dynamodb_table" "main" {
  name         = "${local.prefix}-execucao"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "gsi1pk"
    type = "S"
  }

  attribute {
    name = "gsi1sk"
    type = "S"
  }

  global_secondary_index {
    name            = "gsi1"
    hash_key        = "gsi1pk"
    range_key       = "gsi1sk"
    projection_type = "ALL"
  }
}
