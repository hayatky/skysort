from __future__ import annotations

import logging
from logging.handlers import TimedRotatingFileHandler

from .settings import get_settings


def configure_logging() -> None:
    settings = get_settings()
    log_path = settings.log_dir / "app.log"
    handler = TimedRotatingFileHandler(log_path, when="midnight", backupCount=30, encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not any(isinstance(existing, TimedRotatingFileHandler) for existing in root.handlers):
        root.addHandler(handler)
