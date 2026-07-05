"""结构化日志模块 —— 统一的 JSON 格式日志输出。

核心组件:
  JSONFormatter: 将日志记录序列化为 JSON 行，方便日志采集系统（如 ELK/Loki）解析
  init_logging():  初始化根日志记录器，设置全局日志级别和 JSON 输出格式
  get_logger():    获取命名日志记录器（lazy init 保证在首次使用前自动初始化）

设计决策:
  - 输出到 stdout（符合十二因子应用原则，由容器/Pod 收集）
  - JSON 格式默认包含 time / level / logger / message 四个字段
  - extra 字典中的自定义字段也会合并到 JSON 输出中
"""

from __future__ import annotations  # 推迟类型注解求值

import json
import logging
import os
import sys

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

_LOG_RECORD_ATTRS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
}
# 以上为 LogRecord 内置属性集合；
# JSONFormatter.format() 会排除这些属性，只将非内置的 extra 字段序列化到 JSON 中

_LOG_LEVEL_MAP: dict[str, int] = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}
# 字符串级别名 -> Python logging 整数值的映射


# ---------------------------------------------------------------------------
# JSON 格式化器
# ---------------------------------------------------------------------------

class JSONFormatter(logging.Formatter):
    """JSON 行格式化器 —— 每条日志记录输出为一个单行 JSON 对象。

    输出示例:
        {"time": "2025-06-12T10:30:45.123Z", "level": "INFO",
         "logger": "src.api", "message": "server started on :8080"}
    """

    def format(self, record: logging.LogRecord) -> str:
        """将 LogRecord 格式化为单行 JSON 字符串。

        Args:
            record: Python 标准库的 LogRecord 对象

        Returns:
            JSON 字符串（不确保 ASCII，允许中文输出）
        """
        # 基础字段：时间戳（ISO 8601 兼容）、级别、日志器名、消息
        msg = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S.") + f"{record.msecs:03.0f}Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # 合并 extra 自定义字段（排除 LogRecord 内置属性）
        for key in sorted(set(record.__dict__) - _LOG_RECORD_ATTRS):
            val = getattr(record, key, None)
            if val is not None:
                msg[key] = val

        # ensure_ascii=False 保证中文正常显示
        # default=str 处理不可序列化的类型（如自定义对象）
        return json.dumps(msg, ensure_ascii=False, default=str)


# ---------------------------------------------------------------------------
# 模块内部状态
# ---------------------------------------------------------------------------

_log_initialized = False  # 是否已完成日志系统初始化


# ---------------------------------------------------------------------------
# 初始化逻辑
# ---------------------------------------------------------------------------

def _ensure_initialized(level: str | int | None = None) -> None:
    """懒初始化：确保根日志记录器已配置（幂等调用）。

    只在首次调用时执行实际初始化，后续调用直接返回。
    初始化内容:
        1. 解析日志级别（优先参数，其次 LOG_LEVEL 环境变量，最终默认 INFO）
        2. 清空根记录器的已有 handler
        3. 添加 stdout StreamHandler + JSONFormatter

    Args:
        level: 日志级别，可以是字符串 "DEBUG"/"INFO"/... 或 logging 整数值
    """
    global _log_initialized
    if _log_initialized:
        return

    # 日志级别解析: 参数 > 环境变量 LOG_LEVEL > 默认 INFO
    if level is None:
        level = os.environ.get("LOG_LEVEL", "INFO")

    if isinstance(level, str):
        level = _LOG_LEVEL_MAP.get(level.upper(), logging.INFO)

    # 创建 stdout handler 并应用 JSON 格式化器
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())

    # 配置根日志记录器：清空已有 handler、设置级别、添加新 handler
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)
    root.addHandler(handler)

    _log_initialized = True


# ---------------------------------------------------------------------------
# 公共 API
# ---------------------------------------------------------------------------

def init_logging(level: str | int = "INFO", app_name: str | None = None) -> None:
    """显式初始化日志系统（应用启动时调用）。

    Args:
        level: 日志级别，如 "INFO" / "DEBUG" / "WARNING" / "ERROR" / "CRITICAL"
        app_name: 应用名（如 "fastapi" / "gui" / "cli"），启用文件日志写入 logs/{app_name}.log
    """
    _ensure_initialized(level)

    if app_name:
        _add_file_handler(app_name)


def _add_file_handler(app_name: str) -> None:
    """Add a daily-rotating file handler for the given app name.

    Creates logs/{app_name}.log with daily rotation (keeps 7 backups).
    Uses a custom _BaseRotatingHandler to work reliably on Windows
    (avoids TimedRotatingFileHandler file-locking issues).

    Args:
        app_name: 应用名，用于生成日志文件名
    """
    from logging.handlers import RotatingFileHandler
    from pathlib import Path

    log_cfg = None
    try:
        from src.config import get_app_config
        log_cfg = get_app_config().logging.file
    except (RuntimeError, ImportError):
        pass

    log_dir = Path(log_cfg.dir if log_cfg else "logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    filepath = str(log_dir / f"{app_name}.log")
    max_bytes = 10 * 1024 * 1024
    backup_count = log_cfg.keep if log_cfg else 7

    handler = RotatingFileHandler(
        filename=filepath,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    handler.setFormatter(JSONFormatter())

    root = logging.getLogger()
    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """获取命名日志记录器，调用前自动确保日志系统已初始化。

    这是一个便捷函数，等价于:
        init_logging()  # 仅首次调用执行
        logging.getLogger(name)

    Args:
        name: 日志器名称，通常使用 __name__ 或 "src.<module>"

    Returns:
        标准库 logging.Logger 实例
    """
    _ensure_initialized()  # 懒初始化保证首次使用前完成配置
    return logging.getLogger(name)
