"""Logging configuration, loaded from logging.ini at startup if present."""
import logging
import logging.config
from pathlib import Path

LOGGING_INI_PATH = Path(__file__).resolve().parent.parent.parent / "logging.ini"


def configure_logging(log_level: str = "INFO") -> None:
    if LOGGING_INI_PATH.exists():
        logging.config.fileConfig(LOGGING_INI_PATH, disable_existing_loggers=False)
    else:
        logging.basicConfig(level=log_level)
    logging.getLogger("app").setLevel(log_level)
