"""Logging configuration for Wealth Builder Pro.

Sets up Python logging with IST timestamps, daily file rotation,
and appropriate log levels for each component.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from logging.handlers import TimedRotatingFileHandler


IST = timezone(timedelta(hours=5, minutes=30))

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DEFAULT_LOG_DIR = "/opt/wealth-builder-pro/logs"
DEFAULT_LOG_FILE = "app.log"


class ISTFormatter(logging.Formatter):
    """Formatter that uses IST (UTC+05:30) for timestamps."""

    converter = None  # disable default converter

    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, tz=IST)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.isoformat()


def setup_logging(
    log_dir: str | None = None,
    log_file: str = DEFAULT_LOG_FILE,
    level: int = logging.INFO,
) -> None:
    """Configure application-wide logging.

    Args:
        log_dir: Directory for log files. Defaults to /opt/wealth-builder-pro/logs.
        log_file: Log filename. Defaults to app.log.
        level: Root log level. Defaults to INFO.
    """
    log_dir = log_dir or DEFAULT_LOG_DIR
    os.makedirs(log_dir, exist_ok=True)

    formatter = ISTFormatter(LOG_FORMAT)

    # File handler with daily rotation
    file_path = os.path.join(log_dir, log_file)
    file_handler = TimedRotatingFileHandler(
        file_path, when="midnight", interval=1, backupCount=30, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)

    # Console handler for immediate feedback
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    # Clear existing handlers to avoid duplicates on re-init
    root_logger.handlers.clear()
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
