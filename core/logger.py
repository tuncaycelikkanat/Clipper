"""Centralised loguru-based logger for the clipper project.

Usage::

    from core.logger import logger

    logger.info("Processing video: {}", url)
    logger.error("FFmpeg failed: {}", err)
"""

import os
import sys

from loguru import logger as _logger

# ---------------------------------------------------------------------------
# Log file location
# ---------------------------------------------------------------------------
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LOG_DIR = os.path.join(_PROJECT_ROOT, "outputs", "logs")
_LOG_FILE = os.path.join(_LOG_DIR, "clipper.log")

os.makedirs(_LOG_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Configure the default loguru instance
# ---------------------------------------------------------------------------
# Remove the default stderr handler so we can add our own with formatting.
_logger.remove()

# Console handler — coloured, human-readable
_logger.add(
    sys.stderr,
    level="DEBUG",
    colorize=True,
    format=(
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> — "
        "<level>{message}</level>"
    ),
)

# Rotating file handler
_logger.add(
    _LOG_FILE,
    level="DEBUG",
    rotation="10 MB",  # New file once the current one reaches 10 MB
    retention="7 days",  # Delete files older than 7 days
    compression="zip",  # Compress rotated logs
    encoding="utf-8",
    format=("{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} — {message}"),
    enqueue=True,  # Thread-safe async writes
)

# Public symbol
logger = _logger
