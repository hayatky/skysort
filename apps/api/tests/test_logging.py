from __future__ import annotations

import logging

from skysort_api.infra.logging import configure_logging


def test_configure_logging_writes_uvicorn_logs_to_app_log(isolated_runtime) -> None:
    configure_logging()

    try:
        raise RuntimeError("boom")
    except RuntimeError:
        logging.getLogger("uvicorn.error").exception("ASGI failure sample")
    logging.getLogger("uvicorn.access").info('127.0.0.1:62050 - "GET /api/ai/health HTTP/1.1" 500')

    for logger_name in ("", "uvicorn", "uvicorn.error", "uvicorn.access", "skysort_api"):
        for handler in logging.getLogger(logger_name).handlers:
            handler.flush()

    log_text = (isolated_runtime / "logs" / "app.log").read_text(encoding="utf-8")
    assert "ERROR [uvicorn.error] ASGI failure sample" in log_text
    assert "RuntimeError: boom" in log_text
    assert 'INFO [uvicorn.access] 127.0.0.1:62050 - "GET /api/ai/health HTTP/1.1" 500' in log_text


def test_configure_logging_is_idempotent(isolated_runtime) -> None:
    configure_logging()
    configure_logging()

    for logger_name in ("", "uvicorn", "uvicorn.error", "uvicorn.access", "skysort_api"):
        marked_handlers = [
            handler
            for handler in logging.getLogger(logger_name).handlers
            if getattr(handler, "_skysort_file_handler", False)
        ]
        assert len(marked_handlers) == 1
