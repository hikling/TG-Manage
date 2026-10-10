import logging
import os
import pathlib
from logging.handlers import RotatingFileHandler


class MinLevelFilter(logging.Filter):
    def __init__(self, min_level: int):
        super().__init__()
        self.min_level = min_level

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno >= self.min_level


format_str = (
    "[%(levelname)s] [%(name)s] %(asctime)s %(filename)s %(lineno)s %(message)s"
)
formatter = logging.Formatter(format_str)
_PYROGRAM_HANDLER_MARKER = "_tg_manage_owned_handler"


def _replace_handlers(logger: logging.Logger) -> None:
    """Close handlers before replacing them so files can be rotated or removed."""
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()


def _configure_pyrogram_logger(level_no: int) -> None:
    pyrogram_logger = logging.getLogger("pyrogram")
    owned_handlers = [
        handler for handler in pyrogram_logger.handlers
        if getattr(handler, _PYROGRAM_HANDLER_MARKER, False)
    ]
    if os.environ.get("PYROGRAM_LOG_ON", "0") != "1":
        for handler in owned_handlers:
            pyrogram_logger.removeHandler(handler)
            handler.close()
        return

    pyrogram_logger.setLevel(level_no)
    handler = owned_handlers[0] if owned_handlers else logging.StreamHandler()
    for duplicate in owned_handlers[1:]:
        pyrogram_logger.removeHandler(duplicate)
        duplicate.close()
    setattr(handler, _PYROGRAM_HANDLER_MARKER, True)
    stream = getattr(handler, "stream", None)
    if hasattr(stream, "reconfigure"):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    handler.setFormatter(formatter)
    if not owned_handlers:
        pyrogram_logger.addHandler(handler)


def configure_logger(
    name: str = "tg-manage",
    log_level: str = "INFO",
    log_dir: str | pathlib.Path = "logs",
    log_file: str | pathlib.Path = None,
    max_bytes: int = 1024 * 1024 * 3,
):
    level = log_level.strip().upper()
    level_no = logging.getLevelName(level)

    # 验证日志等级有效性
    if not isinstance(level_no, int):
        logging.warning(f"Invalid log_level '{log_level}', falling back to INFO")
        level_no = logging.INFO

    logger = logging.getLogger(name)
    logger.setLevel(level_no)
    _replace_handlers(logger)
    logger.propagate = False

    console_handler = logging.StreamHandler()
    stream = getattr(console_handler, "stream", None)
    if hasattr(stream, "reconfigure"):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    log_dir = pathlib.Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_file or log_dir / f"{name}.log"
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=10,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # 分级日志文件：warn.log 收 WARNING 及以上（完整问题视图），
    # error.log 收 ERROR 及以上（错误专看）；级别为最小值过滤，
    # 保证 warn.log 不会漏掉 ERROR/CRITICAL 这类更严重的记录
    if level_no <= logging.WARNING:
        warn_file_handler = RotatingFileHandler(
            log_dir / "warn.log",
            maxBytes=max_bytes,
            backupCount=10,
            encoding="utf-8",
        )
        warn_file_handler.setLevel(logging.WARNING)
        warn_file_handler.addFilter(MinLevelFilter(logging.WARNING))
        warn_file_handler.setFormatter(formatter)
        logger.addHandler(warn_file_handler)

    if level_no <= logging.ERROR:
        error_file_handler = RotatingFileHandler(
            log_dir / "error.log",
            maxBytes=max_bytes,
            backupCount=10,
            encoding="utf-8",
        )
        error_file_handler.setLevel(logging.ERROR)
        error_file_handler.addFilter(MinLevelFilter(logging.ERROR))
        error_file_handler.setFormatter(formatter)
        logger.addHandler(error_file_handler)

    _configure_pyrogram_logger(level_no)
    return logger
