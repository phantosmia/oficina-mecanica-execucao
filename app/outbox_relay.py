"""Processo que publica os eventos da outbox no SNS (ver app/shared/outbox.py).

Roda separado da API (`python -m app.outbox_relay`, Deployment próprio com 1
réplica no Kubernetes): a API escala horizontalmente pelo HPA, e várias
réplicas lendo a mesma outbox só gerariam publicações duplicadas à toa.
"""

import logging
import time

from app.shared.dynamodb import get_table
from app.shared.logging_config import configure_logging
from app.shared.outbox import OutboxRelay
from app.shared.settings import settings
from app.shared.sns_publisher import SnsEventPublisher

logger = logging.getLogger("app.outbox_relay")


def main() -> None:  # pragma: no cover - laço infinito; a lógica testada fica em OutboxRelay
    configure_logging(settings.log_level)
    relay = OutboxRelay(get_table(), SnsEventPublisher(settings.events_topic_arn))
    logger.info("relay da outbox iniciado topic=%s", settings.events_topic_arn)
    while True:
        try:
            if relay.run_once() == 0:
                time.sleep(settings.outbox_poll_interval_seconds)
        except Exception:
            logger.exception("falha ao publicar eventos da outbox; tentando de novo")
            time.sleep(settings.outbox_poll_interval_seconds)


if __name__ == "__main__":  # pragma: no cover
    main()
