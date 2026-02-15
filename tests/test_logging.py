"""Tests for coddy.logging (CoddyLogging, level/format from config)."""

import logging

from coddy.config import LoggingConfig
from coddy.logging import (
    DEFAULT_FORMAT,
    DEFAULT_LEVEL,
    LEVELS,
    CoddyLogging,
    _resolve_level,
)


class TestConstants:
    """Module constants and level mapping."""

    def test_levels_has_four_standard_levels(self) -> None:
        """LEVELS maps DEBUG, INFO, WARNING, ERROR to logging constants."""
        assert LEVELS == {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
        }

    def test_default_format_contains_placeholders(self) -> None:
        """DEFAULT_FORMAT is a non-empty string with standard placeholders."""
        assert DEFAULT_FORMAT
        assert "%(levelname)s" in DEFAULT_FORMAT
        assert "%(message)s" in DEFAULT_FORMAT

    def test_default_level_is_info(self) -> None:
        """DEFAULT_LEVEL is INFO."""
        assert DEFAULT_LEVEL == "INFO"


class TestResolveLevel:
    """_resolve_level maps level names to logging constants."""

    def test_known_levels(self) -> None:
        """Known level names return correct logging constant."""
        assert _resolve_level("DEBUG") == logging.DEBUG
        assert _resolve_level("INFO") == logging.INFO
        assert _resolve_level("WARNING") == logging.WARNING
        assert _resolve_level("ERROR") == logging.ERROR

    def test_lowercase_normalized(self) -> None:
        """Level is uppercased before lookup."""
        assert _resolve_level("debug") == logging.DEBUG
        assert _resolve_level("error") == logging.ERROR

    def test_whitespace_stripped(self) -> None:
        """Leading and trailing whitespace is stripped."""
        assert _resolve_level("  INFO  ") == logging.INFO
        assert _resolve_level("\tWARNING\t") == logging.WARNING

    def test_unknown_level_returns_info(self) -> None:
        """Unknown level name falls back to INFO."""
        assert _resolve_level("TRACE") == logging.INFO
        assert _resolve_level("") == logging.INFO


class TestCoddyLogging:
    """CoddyLogging applies LoggingConfig (level + format) to root logger."""

    def test_setup_sets_root_level_from_config(self) -> None:
        """Setup() sets root logger level from config.level."""
        for level_name, expected_num in LEVELS.items():
            cfg = LoggingConfig(level=level_name, format="%(message)s")
            CoddyLogging(cfg).setup()
            assert logging.root.level == expected_num

    def test_unknown_level_falls_back_to_info(self) -> None:
        """Unknown level string falls back to INFO."""
        cfg = LoggingConfig(level="TRACE", format="%(message)s")
        CoddyLogging(cfg).setup()
        assert logging.root.level == logging.INFO

    def test_setup_applies_format(self) -> None:
        """Setup() uses config.format for the root handler."""
        custom = "%(levelname)s || %(message)s"
        cfg = LoggingConfig(level="INFO", format=custom)
        CoddyLogging(cfg).setup()
        root = logging.root
        assert root.handlers
        handler = root.handlers[0]
        assert handler.formatter is not None
        assert handler.formatter._fmt == custom

    def test_get_logger_returns_named_logger(self) -> None:
        """get_logger(name) returns standard logger with that name."""
        cfg = LoggingConfig(level="DEBUG", format="%(message)s")
        coddy_log = CoddyLogging(cfg)
        log = coddy_log.get_logger("coddy.test")
        assert log.name == "coddy.test"
        assert isinstance(log, logging.Logger)

    def test_empty_format_uses_default(self) -> None:
        """When config.format is empty, default format is used."""
        cfg = LoggingConfig(level="INFO", format="")
        CoddyLogging(cfg).setup()
        root = logging.root
        assert root.handlers
        fmt = root.handlers[0].formatter
        assert fmt is not None
        assert fmt._fmt == DEFAULT_FORMAT
