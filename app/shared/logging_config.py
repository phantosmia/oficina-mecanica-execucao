"""Logs estruturados em JSON com correlação entre requisições (mesmo módulo
do OS Service, `oficina-mecanica-fiap`; PDF da Fase 3,
"Monitoramento e Observabilidade" → "Logs estruturados (JSON), incluindo
correlação entre requisições").

Sem isso, cada linha de log é texto solto e não dá pra filtrar/agrupar por
requisição num agregador (New Relic Logs, CloudWatch, etc.) nem cruzar com
os traces da APM (ADR-0007). A abordagem aqui tem duas partes:

1. `RequestIDMiddleware` gera (ou reaproveita, se já vier em `X-Request-ID`)
   um ID por requisição, guardado num `ContextVar` — funciona com o modelo
   assíncrono do FastAPI/Starlette sem precisar passar o ID manualmente por
   toda função.
2. `JSONFormatter` lê esse `ContextVar` (via `_RequestIDFilter`) e injeta
   `request_id` em toda linha de log emitida durante aquela requisição,
   além de `trace.id`/`span.id` do New Relic quando o agente estiver ativo
   (`newrelic.agent.get_linking_metadata()`) — é opcional e não falha se o
   agente não estiver rodando (dev local, testes).
"""

from __future__ import annotations

import contextvars
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

REQUEST_ID_HEADER = "X-Request-ID"

_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    """ID da requisição em andamento no contexto assíncrono atual, se houver."""
    return _request_id.get()


_access_logger = logging.getLogger("app.request")


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Gera/propaga um `X-Request-ID` por requisição e o disponibiliza para o
    `JSONFormatter` correlacionar todos os logs emitidos durante ela."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
        token = _request_id.set(request_id)
        try:
            response = await call_next(request)
        finally:
            _request_id.reset(token)
        response.headers[REQUEST_ID_HEADER] = request_id

        # Logado explicitamente aqui (em vez de depender só do access log do
        # uvicorn.access + ContextVar): o `uvicorn.access` roda fora do
        # escopo assíncrono deste middleware, então o `_RequestIDFilter`
        # nunca via o request_id naquela linha (confirmado no stdout — o
        # campo simplesmente não aparecia). Além disso, o forwarding
        # automático de logs do agente New Relic (`newrelic.source:
        # "logs.APM"`) só encaminha o texto puro de `record.getMessage()` +
        # seu próprio trace.id/span.id — ignora atributos customizados de
        # LogRecord (como o `request_id` que o `JSONFormatter` injeta). Por
        # isso o valor vai embutido no próprio texto da mensagem abaixo, não
        # só como campo estruturado: assim ele sobrevive às duas camadas.
        _access_logger.info(
            "request_id=%s method=%s path=%s status_code=%s",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
        )
        return response


class _RequestIDFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()  # type: ignore[attr-defined]
        return True


class JSONFormatter(logging.Formatter):
    """Formata cada `LogRecord` como uma linha JSON (um objeto por linha)."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        request_id = getattr(record, "request_id", None)
        if request_id:
            payload["request_id"] = request_id

        linking_metadata = _new_relic_linking_metadata()
        if linking_metadata.get("trace.id"):
            payload["trace_id"] = linking_metadata["trace.id"]
        if linking_metadata.get("span.id"):
            payload["span_id"] = linking_metadata["span.id"]

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False)


def _new_relic_linking_metadata() -> dict[str, str]:
    """`trace.id`/`span.id` da transação atual da APM, se o agente estiver
    ativo. Retorna `{}` em dev local/testes (agente não instalado/ativo) —
    nunca deve derrubar o logging por causa de telemetria opcional."""
    try:
        import newrelic.agent

        return newrelic.agent.get_linking_metadata() or {}
    except Exception:
        return {}


def configure_logging(level: str = "INFO") -> None:
    """Substitui a configuração default do `logging` por um handler único que
    emite JSON, aplicado também aos loggers do uvicorn (que por padrão usam
    um formatter de texto simples, próprio)."""
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    handler.addFilter(_RequestIDFilter())

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(level)

    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(logger_name)
        uvicorn_logger.handlers = [handler]
        uvicorn_logger.propagate = False
