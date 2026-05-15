import logging
import os
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path


def _default_log_dir() -> Path:
    raw = os.getenv("LOG_DIR", "")
    if raw.strip():
        return Path(raw.strip())
    return Path("logs")


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

    # file handler (daily rotation)
    try:
        log_dir = _default_log_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = TimedRotatingFileHandler(
            str(log_dir / "solver.log"),
            when="midnight",
            backupCount=30,
            encoding="utf-8",
        )
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)
    except Exception:
        pass  # file logging is best-effort

    return logger


def _level() -> int:
    raw = os.getenv("LOG_LEVEL", "INFO").strip().upper()
    return getattr(logging, raw, logging.INFO)
