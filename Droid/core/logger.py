"""Logging system with per-module rotating file output."""
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Dict


def _make_console_handler() -> logging.StreamHandler:
    """Return a StreamHandler that always writes UTF-8 to the console.

    On Windows the default console codec is cp1252, which rejects characters
    like \u2713 (checkmark) and box-drawing glyphs.  Opening the raw stderr
    file-descriptor with explicit UTF-8 + 'replace' avoids that entirely
    without touching sys.stderr itself.
    """
    try:
        # closefd=False: we don't own the fd, so don't close it on GC.
        # buffering=1:   line-buffered so every log line flushes immediately.
        stream = open(
            sys.stderr.fileno(),
            mode='w',
            encoding='utf-8',
            errors='replace',
            closefd=False,
            buffering=1,
        )
        return logging.StreamHandler(stream)
    except Exception:
        return logging.StreamHandler()  # safe fallback


class LoggerManager:
    """Centralized logger with caching and rotating file output."""

    _loggers: Dict[str, logging.Logger] = {}
    _log_dir: str = "logs"
    _initialized: bool = False

    @classmethod
    def init(cls, log_dir: str = "logs") -> None:
        """Initialize the log directory. Safe to call multiple times."""
        if cls._initialized:
            return
        cls._log_dir = log_dir
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        cls._initialized = True

    @classmethod
    def get_logger(cls, name: str) -> logging.Logger:
        """Return a cached logger, creating it if needed."""
        if name in cls._loggers:
            return cls._loggers[name]

        if not cls._initialized:
            cls.init()

        log = logging.getLogger(name)

        if not log.handlers:
            fmt = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                datefmt="%H:%M:%S",
            )

            # Console — INFO and above, UTF-8 safe on all platforms
            ch = _make_console_handler()
            ch.setLevel(logging.INFO)
            ch.setFormatter(fmt)

            # File — DEBUG and above, rotating at 5 MB
            log_file = os.path.join(cls._log_dir, f"{name}.log")
            fh = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=3)
            fh.setLevel(logging.DEBUG)
            fh.setFormatter(fmt)

            log.setLevel(logging.DEBUG)
            log.addHandler(ch)
            log.addHandler(fh)

        cls._loggers[name] = log
        return log


# Module-level singleton
logger = LoggerManager
