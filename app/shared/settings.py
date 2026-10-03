from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    app_name: str
    log_level: str
    # JWT de admin: emitido pelo OS Service; este serviço só valida.
    jwt_secret_key: str
    jwt_algorithm: str
    admin_username: str
    # AWS (localmente, AWS_ENDPOINT_URL aponta pro LocalStack)
    aws_region: str
    table_name: str
    events_topic_arn: str
    commands_queue_url: str
    worker_wait_seconds: int
    outbox_poll_interval_seconds: float
    # Catálogo (REST síncrono ao concluir o diagnóstico, ADR-0010)
    catalog_base_url: str
    catalog_timeout_seconds: float


settings = Settings(
    app_name="Oficina Mecânica — Execução",
    log_level=os.getenv("LOG_LEVEL", "INFO"),
    jwt_secret_key=os.getenv("JWT_SECRET_KEY", "change-me-in-production"),
    jwt_algorithm=os.getenv("JWT_ALGORITHM", "HS256"),
    admin_username=os.getenv("ADMIN_USERNAME", "admin"),
    aws_region=os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "us-east-1")),
    table_name=os.getenv("EXECUCAO_TABLE_NAME", "oficina-execucao"),
    events_topic_arn=os.getenv("EXECUCAO_EVENTS_TOPIC_ARN", ""),
    commands_queue_url=os.getenv("EXECUCAO_COMMANDS_QUEUE_URL", ""),
    worker_wait_seconds=int(os.getenv("WORKER_WAIT_SECONDS", "10")),
    outbox_poll_interval_seconds=float(os.getenv("OUTBOX_POLL_INTERVAL_SECONDS", "2")),
    catalog_base_url=os.getenv("CATALOG_BASE_URL", "http://localhost:8001"),
    catalog_timeout_seconds=float(os.getenv("CATALOG_TIMEOUT_SECONDS", "3")),
)
