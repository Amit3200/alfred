"""Persistent LangGraph SQLite checkpoint."""

from __future__ import annotations

import atexit
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_saver: Any | None = None
_cm: Any | None = None
_db_path: Path | None = None


def get_langgraph_checkpointer(data_dir: Path):
    """Return a process-wide SqliteSaver for LangGraph thread state."""
    global _saver, _cm, _db_path
    if _saver is not None:
        return _saver

    from langgraph.checkpoint.sqlite import SqliteSaver

    data_dir.mkdir(parents=True, exist_ok=True)
    _db_path = data_dir / "langgraph_checkpoints.db"
    conn_str = str(_db_path.resolve())
    _cm = SqliteSaver.from_conn_string(conn_str)
    _saver = _cm.__enter__()
    _saver.setup()
    atexit.register(close_langgraph_checkpointer)
    logger.info("LangGraph SQLite checkpoint at %s", _db_path)
    return _saver


def close_langgraph_checkpointer() -> None:
    global _saver, _cm
    if _cm is not None:
        try:
            _cm.__exit__(None, None, None)
        except Exception:
            logger.debug("LangGraph checkpoint close failed", exc_info=True)
    _saver = None
    _cm = None


def checkpoint_db_path(data_dir: Path) -> Path:
    return data_dir / "langgraph_checkpoints.db"
