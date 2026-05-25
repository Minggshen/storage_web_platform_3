import logging
import os
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

_file_handler = None  # singleton shared across all loggers


def _default_log_dir() -> Path:
    raw = os.getenv("LOG_DIR", "")
    if raw.strip():
        return Path(raw.strip())
    return Path("logs")


def _get_shared_file_handler(fmt: logging.Formatter) -> TimedRotatingFileHandler | None:
    """Return the singleton TimedRotatingFileHandler, creating it on first call.

    A single handler instance shared across all loggers prevents Windows
    PermissionError during log rotation: if each named logger creates its own
    TimedRotatingFileHandler, they all hold separate file handles to
    solver.log, and os.rename() fails when any other handle is still open.
    """
    global _file_handler
    if _file_handler is not None:
        return _file_handler
    try:
        log_dir = _default_log_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        _file_handler = TimedRotatingFileHandler(
            str(log_dir / "solver.log"),
            when="midnight",
            backupCount=30,
            encoding="utf-8",
        )
        _file_handler.setFormatter(fmt)
    except Exception:
        _file_handler = False  # sentinel: creation failed, don't retry
    return _file_handler


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(_level())

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # stdout handler
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(fmt)
    logger.addHandler(stdout_handler)

    # file handler (daily rotation) — shared singleton
    fh = _get_shared_file_handler(fmt)
    if fh and fh is not False:
        logger.addHandler(fh)

    return logger


def _level() -> int:
    raw = os.getenv("LOG_LEVEL", "INFO").strip().upper()
    return getattr(logging, raw, logging.INFO)
