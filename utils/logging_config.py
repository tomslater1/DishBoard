"""Application logging configuration."""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler

from utils.paths import get_data_dir

_CONFIGURED = False


def setup_logging(level: int = logging.INFO) -> None:
    """Configure console + rotating file logging once per process."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    root = logging.getLogger()
    root.setLevel(level)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(formatter)
    root.addHandler(console)

    log_path = os.path.join(get_data_dir(), "dishboard.log")
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=1_500_000,
        backupCount=4,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    # Reduce log noise from HTTP client internals.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    _CONFIGURED = True

