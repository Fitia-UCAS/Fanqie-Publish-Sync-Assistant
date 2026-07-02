from __future__ import annotations


import logging

from backend.paths import LOG_FILE, ensure_data_directories

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def setup_logging() -> None:
    ensure_data_directories()
    logging.basicConfig(
        level=logging.INFO,
        format=LOG_FORMAT,
        handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8")],
        force=True,
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


