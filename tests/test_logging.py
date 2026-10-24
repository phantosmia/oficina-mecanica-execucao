import json
import logging

from app.shared.logging_config import JSONFormatter, _RequestIDFilter, saga_log_context


def _formatted(msg: str) -> dict:
    record = logging.LogRecord(
        name="app.teste", level=logging.INFO, pathname=__file__, lineno=1, msg=msg, args=(), exc_info=None
    )
    _RequestIDFilter().filter(record)
    return json.loads(JSONFormatter().format(record))


def test_saga_log_context_inclui_saga_id_e_order_id_nos_logs() -> None:
    with saga_log_context("saga-1", 42):
        payload = _formatted("dentro da saga")

    assert payload["saga_id"] == "saga-1"
    assert payload["order_id"] == "42"


def test_saga_log_context_omite_valores_ausentes_e_e_desfeito_ao_sair() -> None:
    with saga_log_context(saga_id="saga-1"):
        dentro = _formatted("só a saga")
    fora = _formatted("fora da saga")

    assert dentro["saga_id"] == "saga-1"
    assert "order_id" not in dentro
    assert "saga_id" not in fora and "order_id" not in fora
