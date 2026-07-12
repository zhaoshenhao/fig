"""Metrics 存储工厂 —— 按配置选择 SQLite / MySQL / PostgreSQL 引擎。

默认使用 SQLite（`MetricsStore`）。仅当配置显式设置 engine 为 mysql /
postgresql 时，才使用对应的连接池后端。

配置来源（优先级从高到低）：
  1. 环境变量 KF_METRICS_ENGINE / KF_METRICS_DB_PATH / KF_METRICS_POOL
  2. config/metrics.yaml（若存在，通过 app_config.metrics 提供）
  3. 默认：sqlite, data/metrics.db
"""

from __future__ import annotations

import os
from typing import Any

from src.logger import get_logger
from src.metrics.store import MetricsStore

_log = get_logger(__name__)


def create_metrics_store(metrics_cfg: dict[str, Any] | None = None):
    """根据配置创建 Metrics 存储实例。

    Args:
        metrics_cfg: 可选配置 dict，形如
            {"engine": "sqlite", "path": "data/metrics.db"} 或
            {"engine": "mysql", "pool": "metrics"}。

    Returns:
        MetricsStore | MySQLMetricsStore | PostgresMetricsStore
    """
    cfg = dict(metrics_cfg or {})
    engine = (os.environ.get("KF_METRICS_ENGINE") or cfg.get("engine") or "sqlite").lower()

    if engine in ("sqlite", "", None):
        path = os.environ.get("KF_METRICS_DB_PATH") or cfg.get("path") or "data/metrics.db"
        return MetricsStore(path)

    if engine not in ("mysql", "postgresql", "postgres", "pg"):
        raise ValueError(f"unknown metrics engine: {engine!r}")

    pool_name = os.environ.get("KF_METRICS_POOL") or cfg.get("pool") or "metrics"
    from src.db import get_db_pool

    pool = get_db_pool(pool_name)
    if engine == "mysql":
        from src.metrics.sql_store import MySQLMetricsStore
        _log.info("metrics: using MySQL backend", extra={"pool": pool_name})
        return MySQLMetricsStore(pool)
    from src.metrics.sql_store import PostgresMetricsStore
    _log.info("metrics: using PostgreSQL backend", extra={"pool": pool_name})
    return PostgresMetricsStore(pool)
