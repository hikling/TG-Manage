"""
测试日志系统优化相关功能

本测试模块覆盖日志系统优化提交中修改的关键函数：
1. safe_traceback_preview - traceback 脱敏和格式化
2. _configure_backend_logging - 后端日志配置
3. configure_logger - 签名器日志配置
4. run_id 错误日志格式
"""

import io
import logging
import os
from pathlib import Path

import pytest

# 导入待测试的函数
from tg_manage.log_utils import safe_traceback_preview


class TestSafeTracebackPreview:
    """测试 safe_traceback_preview 函数"""

    def test_basic_traceback_redaction(self):
        """测试基本的 traceback 脱敏功能"""
        tb = """
Traceback (most recent call last):
  File "test.py", line 10, in <module>
    api_key = "sk-1234567890abcdef"
  File "test.py", line 20, in connect
    session_string = "1234567890:ABCDefghijk"
ValueError: Invalid credentials
"""
        result = safe_traceback_preview(tb, max_lines=10, max_line_chars=200)

        # 应该包含文件名和行号
        assert "test.py" in result
        assert "line 10" in result or "line 20" in result

        # 敏感信息应该被脱敏
        assert "sk-1234567890abcdef" not in result
        assert "1234567890:ABCDefghijk" not in result
        assert "[REDACTED]" in result

    def test_preserve_indentation(self):
        """测试保留行首缩进"""
        tb = """
Traceback (most recent call last):
  File "test.py", line 10, in func
    result = calculate()
    File "test.py", line 20, in calculate
      return x + y
ValueError: invalid literal
"""
        result = safe_traceback_preview(tb, max_lines=10, max_line_chars=200)
        lines = result.splitlines()

        # 检查缩进是否保留
        indented_lines = [line for line in lines if line.startswith("  ")]
        assert len(indented_lines) > 0, "应该保留缩进行"

    def test_max_lines_limit(self):
        """测试最大行数限制"""
        tb = "\n".join([f"Line {i}" for i in range(20)])
        result = safe_traceback_preview(tb, max_lines=5, max_line_chars=200)
        lines = result.splitlines()

        # 应该只返回最后 5 行
        assert len(lines) == 5
        assert "Line 19" in result  # 最后一行

    def test_line_truncation(self):
        """测试单行截断"""
        long_line = "x" * 300
        tb = f"Traceback (most recent call last):\n  {long_line}"
        result = safe_traceback_preview(tb, max_lines=10, max_line_chars=100)

        # 长行应该被截断
        for line in result.splitlines():
            # 去除缩进后检查长度
            content = line.lstrip()
            assert len(content) <= 103, f"行长度超限: {len(content)}"  # 100 + "..."

    def test_empty_traceback(self):
        """测试空 traceback"""
        result = safe_traceback_preview("", max_lines=10, max_line_chars=200)
        assert result == ""

        result = safe_traceback_preview("NoneType: None\n", max_lines=10, max_line_chars=200)
        assert result == ""

    def test_whitespace_folding(self):
        """测试空白折叠行为（新行为）"""
        tb = "Traceback:\n  File 'test.py',  line   10,    in    func"
        result = safe_traceback_preview(tb, max_lines=10, max_line_chars=200)

        # safe_text_preview 会折叠连续空白
        # 这是预期的新行为
        # 检查每行的内容部分（去除行首缩进后）不应有连续空格
        for line in result.splitlines():
            content = line.lstrip()
            assert "  " not in content, f"行内容部分不应有连续空格: {line!r}"


@pytest.fixture
def isolated_loggers(monkeypatch):
    """Restore global Pyrogram state and close every test-owned handler."""
    from tg_manage.logger import configure_logger

    monkeypatch.setenv("PYROGRAM_LOG_ON", "0")
    configured = []
    pyrogram_logger = logging.getLogger("pyrogram")
    original_handlers = pyrogram_logger.handlers[:]
    original_level = pyrogram_logger.level
    original_propagate = pyrogram_logger.propagate

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
        for handler in pyrogram_logger.handlers[:]:
            if handler not in original_handlers:
                pyrogram_logger.removeHandler(handler)
                handler.close()
        pyrogram_logger.handlers[:] = original_handlers
        pyrogram_logger.setLevel(original_level)
        pyrogram_logger.propagate = original_propagate


class TestConfigureLogger:
    """Logger configuration must release resources and remain idempotent."""

    def test_invalid_log_level_fallback(self, isolated_loggers, tmp_path):
        logger = isolated_loggers(
            name="test-invalid", log_level="INVALID_LEVEL", log_dir=tmp_path,
        )
        assert logger.level == logging.INFO

    def test_warn_log_creation(self, isolated_loggers, tmp_path):
        isolated_loggers(name="test-warn", log_level="WARNING", log_dir=tmp_path)
        assert (tmp_path / "warn.log").exists()

    def test_error_log_creation(self, isolated_loggers, tmp_path):
        isolated_loggers(name="test-error", log_level="ERROR", log_dir=tmp_path)
        assert not (tmp_path / "warn.log").exists()
        assert (tmp_path / "error.log").exists()

    def test_reconfiguration_closes_previous_file_handles(self, isolated_loggers, tmp_path):
        first_dir = tmp_path / "first"
        logger = isolated_loggers(name="test-reconfigure", log_dir=first_dir)
        logger.warning("first-directory")
        previous_handlers = logger.handlers[:]
        previous_streams = [
            handler.stream for handler in previous_handlers
            if isinstance(handler, logging.FileHandler)
        ]
        reconfigured = isolated_loggers(name="test-reconfigure", log_dir=tmp_path / "second")
        assert reconfigured is logger
        assert len(logger.handlers) == len(previous_handlers)
        assert all(stream.closed for stream in previous_streams)
        assert all(handler not in logger.handlers for handler in previous_handlers)
        # Windows refuses unlink while any old FileHandler still owns the file.
        for old_log in first_dir.iterdir():
            old_log.unlink()
        first_dir.rmdir()
        logger.warning("second-directory")
        for handler in logger.handlers:
            handler.flush()
        contents = (tmp_path / "second" / "test-reconfigure.log").read_text(encoding="utf-8")
        assert contents.count("second-directory") == 1

    def test_pyrogram_handler_no_duplicate(self, isolated_loggers, tmp_path, monkeypatch):
        monkeypatch.setenv("PYROGRAM_LOG_ON", "1")
        output = io.StringIO()
        monkeypatch.setattr("sys.stderr", output)
        pyrogram_logger = logging.getLogger("pyrogram")
        pyrogram_logger.propagate = False
        external_handler = logging.NullHandler()
        pyrogram_logger.addHandler(external_handler)
        before = pyrogram_logger.handlers[:]
        isolated_loggers(name="test-pyrogram-1", log_level="INFO", log_dir=tmp_path)
        first_handlers = pyrogram_logger.handlers[:]
        added = [handler for handler in first_handlers if handler not in before]
        assert len(added) == 1
        isolated_loggers(name="test-pyrogram-2", log_level="DEBUG", log_dir=tmp_path)
        assert pyrogram_logger.handlers == first_handlers
        assert pyrogram_logger.level == logging.DEBUG
        assert external_handler in pyrogram_logger.handlers
        pyrogram_logger.warning("single-pyrogram-output")
        assert output.getvalue().count("single-pyrogram-output") == 1

    def test_disabled_pyrogram_preserves_external_configuration(
        self, isolated_loggers, tmp_path,
    ):
        pyrogram_logger = logging.getLogger("pyrogram")
        external_handler = logging.NullHandler()
        pyrogram_logger.addHandler(external_handler)
        pyrogram_logger.setLevel(logging.CRITICAL)
        before = pyrogram_logger.handlers[:]
        isolated_loggers(name="test-pyrogram-disabled", log_level="DEBUG", log_dir=tmp_path)
        assert pyrogram_logger.handlers == before
        assert pyrogram_logger.level == logging.CRITICAL

    def test_disabling_pyrogram_removes_only_owned_handler(
        self, isolated_loggers, tmp_path, monkeypatch,
    ):
        pyrogram_logger = logging.getLogger("pyrogram")
        external_handler = logging.NullHandler()
        pyrogram_logger.addHandler(external_handler)
        before = pyrogram_logger.handlers[:]
        monkeypatch.setenv("PYROGRAM_LOG_ON", "1")
        isolated_loggers(name="test-pyrogram-enable", log_level="WARNING", log_dir=tmp_path)
        owned_handler = next(handler for handler in pyrogram_logger.handlers if handler not in before)
        monkeypatch.setenv("PYROGRAM_LOG_ON", "0")
        isolated_loggers(name="test-pyrogram-disable", log_level="DEBUG", log_dir=tmp_path)
        assert pyrogram_logger.handlers == before
        assert pyrogram_logger.level == logging.WARNING
        assert owned_handler._closed

class TestBackendLoggingConfig:
    """测试后端日志配置（需要 import backend.main）"""

    def test_configure_backend_logging_function_exists(self):
        """测试 _configure_backend_logging 函数存在"""
        # 这个测试只检查函数是否可导入
        # 实际运行需要完整的 backend 环境
        try:
            from backend.main import _configure_backend_logging
            assert callable(_configure_backend_logging)
        except ImportError as e:
            pytest.skip(f"无法导入 backend.main: {e}")

    def test_bot_token_urls_are_not_logged_at_info_or_debug(self, monkeypatch):
        """httpx/httpcore must not log Bot API URLs containing the token."""
        try:
            from backend.main import _configure_backend_logging
        except ImportError as e:
            pytest.skip(f"无法导入 backend.main: {e}")

        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        names = ("", "backend", "uvicorn", "uvicorn.access", "httpx", "httpcore")
        loggers = {name: logging.getLogger(name) for name in names}
        previous = {
            name: (logger.level, list(logger.handlers), list(logger.filters), logger.disabled, logger.propagate)
            for name, logger in loggers.items()
        }
        try:
            _configure_backend_logging()
            assert loggers["httpx"].getEffectiveLevel() >= logging.WARNING
            assert loggers["httpcore"].getEffectiveLevel() >= logging.WARNING
        finally:
            for name, logger in loggers.items():
                level, handlers, filters, disabled, propagate = previous[name]
                logger.setLevel(level)
                logger.handlers[:] = handlers
                logger.filters[:] = filters
                logger.disabled = disabled
                logger.propagate = propagate

    def test_log_level_env_var(self):
        """测试 LOG_LEVEL 环境变量读取"""
        original_value = os.environ.get("LOG_LEVEL")

        try:
            # 设置测试环境变量
            os.environ["LOG_LEVEL"] = "DEBUG"

            # 验证可以读取
            level = os.environ.get("LOG_LEVEL", "INFO").upper()
            assert level == "DEBUG"

            level_no = logging.getLevelName(level)
            assert isinstance(level_no, int)
            assert level_no == logging.DEBUG

        finally:
            if original_value is None:
                os.environ.pop("LOG_LEVEL", None)
            else:
                os.environ["LOG_LEVEL"] = original_value


# 运行测试的辅助函数
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])


class TestNoBarePrintInProduction:
    """生产模块不得残留 bare print() 调试语句。

    print 走 stdout，会绕过 LOG_LEVEL 过滤与结构化日志，
    在 Docker 生产环境丢失日志层级。统一改用 logging.getLogger。
    """

    # 待扫描的生产模块文件路径（相对项目根）
    _TARGETS = [
        "backend/scheduler/__init__.py",
        "backend/utils/storage.py",
        "backend/api/routes/accounts.py",
        "backend/api/routes/ops.py",
        "tg_manage/core/client.py",
    ]

    @pytest.mark.parametrize("rel_path", _TARGETS)
    def test_no_bare_print_statement(self, rel_path):
        # 直接读源码文本做静态扫描，避免 import 触发预存的链式 NameError
        path = Path(rel_path)
        assert path.is_file(), f"扫描目标不存在（请更新 _TARGETS）: {rel_path}"
        src = path.read_text(encoding="utf-8")
        offending = [
            f"{i+1}: {line.strip()}"
            for i, line in enumerate(src.splitlines())
            if line.strip().startswith("print(")
        ]
        assert offending == [], (
            f"{rel_path} 残留 bare print() 调试语句: {offending}"
        )
