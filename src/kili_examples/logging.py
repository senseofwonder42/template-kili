"""Loguru configuration for the project."""

import sys

from loguru import logger

from kili_examples.config import settings


def setup_logging() -> None:
    """Configure the loguru console sink.

    Replaces the default handler with one writing to stdout (so logs appear
    in Docker/Kubernetes logs automatically) at the level given by the
    ``LOG_LEVEL`` setting. Call this ONCE at the start of your program.
    """
    logger.remove()
    logger.add(sys.stdout, level=settings.log_level)
