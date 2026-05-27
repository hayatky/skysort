from __future__ import annotations

import logging
from pathlib import Path
from logging.handlers import TimedRotatingFileHandler

from .settings import get_settings

_LOGGER_NAMES = ("", "uvicorn", "uvicorn.error", "uvicorn.access", "skysort_api")
_HANDLER_MARKER = "_skysort_file_handler"
_RECORD_MARKER = "_skysort_file_emitted"


def configure_logging() -> None:
    settings = get_settings()
    log_path = settings.log_dir / "app.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    handler = _get_or_create_file_handler(log_path, formatter)

    for logger_name in _LOGGER_NAMES:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.INFO)
        _remove_stale_file_handlers(logger, log_path)
        if handler not in logger.handlers:
            logger.addHandler(handler)


def _get_or_create_file_handler(log_path: Path, formatter: logging.Formatter) -> TimedRotatingFileHandler:
    for logger_name in _LOGGER_NAMES:
        logger = logging.getLogger(logger_name)
        for existing in logger.handlers:
            if _is_skysort_file_handler(existing) and Path(existing.baseFilename) == log_path.resolve():
                existing.setFormatter(formatter)
                _ensure_once_filter(existing)
                return existing

    handler = TimedRotatingFileHandler(log_path, when="midnight", backupCount=30, encoding="utf-8")
    handler.setFormatter(formatter)
    handler.addFilter(_OncePerRecordFilter())
    setattr(handler, _HANDLER_MARKER, True)
    return handler


def _remove_stale_file_handlers(logger: logging.Logger, log_path: Path) -> None:
    for existing in list(logger.handlers):
        if _is_skysort_file_handler(existing) and Path(existing.baseFilename) != log_path.resolve():
            logger.removeHandler(existing)
            existing.close()


def _is_skysort_file_handler(handler: logging.Handler) -> bool:
    return isinstance(handler, TimedRotatingFileHandler) and bool(getattr(handler, _HANDLER_MARKER, False))


def _ensure_once_filter(handler: logging.Handler) -> None:
    if not any(isinstance(existing, _OncePerRecordFilter) for existing in handler.filters):
        handler.addFilter(_OncePerRecordFilter())


class _OncePerRecordFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if getattr(record, _RECORD_MARKER, False):
            return False
        setattr(record, _RECORD_MARKER, True)
        return True
