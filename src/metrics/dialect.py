"""SQL 方言定义 —— 支持 Metrics 存储在 SQLite / MySQL / PostgreSQL 间切换。

设计：所有 SQL 逻辑集中在 `SQLMetricsStore` 基类中，用占位符 token 与方言片段
参数化差异部分。各引擎子类只需提供：连接获取、占位符风格、自增/时间/聚合函数片段。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Dialect:
    """描述某数据库引擎的 SQL 方言差异。"""

    name: str
    paramstyle: str            # "qmark" (?) 或 "format" (%s)
    autoincrement: str         # 自增主键列定义
    text_type: str             # 大文本列类型（query/reply 等）
    varchar_type: str          # 短字符串列类型（id/name/status 等，MySQL 索引/默认值友好）
    creation_ts_type: str      # created_at/updated_at 列类型（MySQL 需 DATETIME，SQLite/PostgreSQL 可用 TEXT）
    ts_default: str            # created_at 默认时间（UTC）
    group_concat: str          # 去重字符串聚合函数名，用于 workflow_names
    supports_ilike: bool = False

    def ph(self, n: int = 1) -> str:
        """返回 n 个占位符，逗号分隔。"""
        token = "?" if self.paramstyle == "qmark" else "%s"
        return ", ".join([token] * n)

    def one(self) -> str:
        return "?" if self.paramstyle == "qmark" else "%s"

    def convert(self, sql: str) -> str:
        """将以 '?' 编写的 SQL 转为该方言的占位符风格。"""
        if self.paramstyle == "qmark":
            return sql
        return sql.replace("?", "%s")

    def group_concat_expr(self, col: str) -> str:
        if self.group_concat == "string_agg":
            return f"string_agg(DISTINCT {col}, ',')"
        return f"GROUP_CONCAT(DISTINCT {col})"


SQLITE = Dialect(
    name="sqlite",
    paramstyle="qmark",
    autoincrement="INTEGER PRIMARY KEY AUTOINCREMENT",
    text_type="TEXT",
    varchar_type="TEXT",
    creation_ts_type="TEXT",
    ts_default="(datetime('now'))",
    group_concat="group_concat",
)

MYSQL = Dialect(
    name="mysql",
    paramstyle="format",
    autoincrement="BIGINT AUTO_INCREMENT PRIMARY KEY",
    text_type="TEXT",
    varchar_type="VARCHAR(255)",
    creation_ts_type="DATETIME",
    ts_default="CURRENT_TIMESTAMP",
    group_concat="group_concat",
)

POSTGRES = Dialect(
    name="postgresql",
    paramstyle="format",
    autoincrement="BIGSERIAL PRIMARY KEY",
    text_type="TEXT",
    varchar_type="VARCHAR(255)",
    creation_ts_type="TEXT",
    ts_default="(now() at time zone 'utc')",
    group_concat="string_agg",
    supports_ilike=True,
)
