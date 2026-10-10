"""Level-specific log filtering with deterministic file-handler cleanup."""

import logging
from pathlib import Path

import pytest

from tg_manage.logger import MinLevelFilter, configure_logger


@pytest.fixture
def isolated_loggers(monkeypatch):
    """Close handlers owned by these tests before tmp_path cleanup."""
    monkeypatch.setenv("PYROGRAM_LOG_ON", "0")
    configured = []

    def configure(**kwargs):
        logger = logging.getLogger(kwargs["name"])
        configured.append(logger)
        return configure_logger(**kwargs)

    try:
        yield configure
    finally:
        for logger in configured:
            for handler in logger.handlers[:]:
                logger.removeHandler(handler)
                handler.close()


class TestLevelFileFiltering:
    def test_warn_log_contains_warning_and_above(self, isolated_loggers, tmp_path):
        logger = isolated_loggers(name="level-file-info", log_level="INFO", log_dir=tmp_path)
        logger.info("info-line")
        logger.warning("warn-line")
        logger.error("error-line")
        logger.critical("critical-line")
        for handler in logger.handlers:
            handler.flush()

        warn_lines = _read_lines(tmp_path / "warn.log")
        assert any("warn-line" in line for line in warn_lines)
        assert any("error-line" in line for line in warn_lines)
        assert any("critical-line" in line for line in warn_lines)
        assert not any("info-line" in line for line in warn_lines)

        error_lines = _read_lines(tmp_path / "error.log")
        assert any("error-line" in line for line in error_lines)
        assert any("critical-line" in line for line in error_lines)
        assert not any("warn-line" in line for line in error_lines)
        assert not any("info-line" in line for line in error_lines)

    def test_error_level_skips_warn_file(self, isolated_loggers, tmp_path):
        isolated_loggers(name="level-file-error", log_level="ERROR", log_dir=tmp_path)
        assert not (tmp_path / "warn.log").exists()
        assert (tmp_path / "error.log").exists()

    def test_info_level_creates_grade_files(self, isolated_loggers, tmp_path):
        isolated_loggers(name="level-file-create", log_level="INFO", log_dir=tmp_path)
        assert (tmp_path / "warn.log").exists()
        assert (tmp_path / "error.log").exists()


class TestMinLevelFilter:
    def test_filters_below_min_level(self):
        level_filter = MinLevelFilter(logging.WARNING)
        assert level_filter.filter(_record(logging.INFO)) is False
        assert level_filter.filter(_record(logging.WARNING)) is True
        assert level_filter.filter(_record(logging.ERROR)) is True


def _read_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8").splitlines()


def _record(level: int) -> logging.LogRecord:
    return logging.LogRecord(
        name="t", level=level, pathname=__file__, lineno=1,
        msg="x", args=(), exc_info=None,
    )
