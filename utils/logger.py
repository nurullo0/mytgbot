"""
Configures application-wide logging: console output plus a rotating
file handler so log files don't grow unbounded in production.
"""

import logging
import sys
from logging.handlers import RotatingFileHandler

from config import config


def setup_logging() -> None:
    level = getattr(logging, config.log_level.upper(), logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    file_handler = RotatingFileHandler(
        "bot.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    # Quiet down noisy third-party loggers.
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)
