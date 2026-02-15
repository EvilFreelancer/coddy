"""Logging from config and env.

Levels (inclusive):
- ERROR: critical errors only
- WARNING: non-critical issues and ERROR
- INFO: service messages, WARNING, and ERROR
- DEBUG: debugging and all levels above

Configure via config.yaml (logging.level, logging.format) or env (LOGGING_LEVEL, LOGGING_FORMAT).
"""

import logging

from coddy.config import LoggingConfig

# Supported levels only (DEBUG, INFO, WARNING, ERROR)
LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
}

DEFAULT_LEVEL = "INFO"
DEFAULT_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


def _resolve_level(level: str) -> int:
    """Map level name to logging constant.

    Falls back to INFO if unknown.
    """
    return LEVELS.get(level.upper().strip(), logging.INFO)


class CoddyLogging:
    """Configures root logger from LoggingConfig (YAML + env LOGGING_*)."""

    def __init__(self, config: LoggingConfig) -> None:
        """Store logging config (level and format)."""
        self._level = _resolve_level(config.level)
        self._format = config.format or DEFAULT_FORMAT

    def setup(self) -> None:
        """Apply level and format to the root logger."""
        logging.basicConfig(
            level=self._level,
            format=self._format,
            force=True,
        )

    def get_logger(self, name: str) -> logging.Logger:
        """Return a logger with the given name (uses root config)."""
        return logging.getLogger(name)
