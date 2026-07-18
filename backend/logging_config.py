"""File + console logging for Alfred."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from backend.paths import log_path

_configured = False


def setup_logging(data_dir: Path | None = None, *, console_level: int = logging.INFO) -> Path:
    """Configure root logger: DEBUG → file, INFO → stderr. Idempotent per process."""
    global _configured
    path = log_path(data_dir)
    if _configured:
        return path

    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        path,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)
    console_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(file_handler)
    root.addHandler(console_handler)

    for name in ("httpx", "httpcore", "uvicorn.access"):
        logging.getLogger(name).setLevel(logging.WARNING)
    for name in (
        "duckduckgo_search",
        "primp",
        "hyper",
        "hyper_util",
        "h2",
        "rustls",
        "hickory_proto",
        "hickory_net",
        "cookie_store",
    ):
        logging.getLogger(name).setLevel(logging.WARNING)
    logging.getLogger("slack_sdk").setLevel(logging.INFO)

    _configured = True
    logging.getLogger(__name__).info("Logging to %s", path)
    return path
