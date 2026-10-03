"""Propagação do *trace context* do New Relic através das mensagens (RFC-0007).

O evento é gravado na outbox durante a requisição HTTP, mas só é publicado
depois, pelo relay, fora daquela transação da APM. Para o trace não se partir
no meio, os cabeçalhos de *distributed tracing* são capturados no momento da
gravação (`current_trace_headers`) e viajam junto com o item da outbox até
virarem `MessageAttributes` da mensagem SNS.

Sem o agente ativo (dev local, testes), tudo vira no-op.
"""

from collections.abc import Iterator
from contextlib import contextmanager


def current_trace_headers() -> dict[str, str]:
    try:
        import newrelic.agent

        headers: list[tuple[str, str]] = []
        newrelic.agent.insert_distributed_trace_headers(headers)
        return dict(headers)
    except Exception:
        return {}


@contextmanager
def consume_trace(name: str, message_attributes: dict[str, str]) -> Iterator[None]:
    """Processa uma mensagem como uma transação do New Relic que continua o
    trace de quem a publicou (cabeçalhos vindos dos `MessageAttributes`).
    Sem o agente ativo, só executa o bloco."""
    try:
        import newrelic.agent

        application = newrelic.agent.application()
    except Exception:
        yield
        return
    with newrelic.agent.BackgroundTask(application, name=name, group="Message/SQS"):
        newrelic.agent.accept_distributed_trace_headers(message_attributes, transport_type="Queue")
        yield
