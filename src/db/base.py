"""数据库连接池基类 —— 定义数据库抽象的通用接口和配置数据类。

模块架构:
  DBConfig       —— 数据库全局配置（多个连接池的集合）
  DBPoolConfig   —— 单个连接池的配置（类型/主机/端口/用户/密码/库名/池大小）
  DBPool (ABC)   —— 连接池抽象基类（定义 execute / close 接口）

多数据库策略:
  一个应用实例可同时管理多个数据库连接池（MySQL + PostgreSQL 异构并存），
  每个 pool 由唯一的 name 标识，通过 DBConfig.get(name) 获取对应配置。

设计原则 (依赖倒置):
  上层代码只依赖 DBPool 接口，不直接依赖具体实现（MySQLPool / PgPool），
  新增数据库类型只需添加新的 DBPool 子类，无需修改调用方代码。
"""

from __future__ import annotations  # 推迟类型注解求值

from abc import ABC, abstractmethod  # 抽象基类基础设施
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# 配置数据类
# ---------------------------------------------------------------------------

@dataclass
class DBConfig:
    """数据库全局配置 —— 管理多个连接池的集合。

    字段:
        default: 默认连接池名称（空字符串表示必须显式指定）
        pools:   {"name": DBPoolConfig} 连接池配置映射，key 为连接池唯一名称
    """
    default: str = ""
    pools: dict[str, DBPoolConfig] = field(default_factory=dict)

    def get(self, name: str = "") -> DBPoolConfig:
        """按名称获取连接池配置，name 为空时使用 default。

        Args:
            name: 连接池名称

        Returns:
            对应的 DBPoolConfig 实例

        Raises:
            KeyError: 指定名称的连接池不存在
        """
        key = name or self.default
        if key not in self.pools:
            raise KeyError(f"db pool '{key}' not found")
        return self.pools[key]


@dataclass
class DBPoolConfig:
    """单个数据库连接池的配置参数。

    字段:
        type:     数据库类型，支持 "mysql" / "postgresql"
        host:     主机地址，默认 localhost
        port:     端口号，MySQL 默认 3306，PostgreSQL 默认 5432
        user:     数据库用户名
        password: 数据库密码
        database: 目标数据库名
        pool_size: 连接池最大连接数，默认 5
    """
    type: str
    host: str = "localhost"
    port: int = 3306
    user: str = ""
    password: str = ""
    database: str = ""
    pool_size: int = 5


# ---------------------------------------------------------------------------
# 抽象基类: DBPool
# ---------------------------------------------------------------------------

class DBPool(ABC):
    """数据库连接池抽象基类 —— 定义统一的数据访问接口。

    所有数据库实现必须继承此类并实现 execute / close 两个抽象方法。
    上层业务代码只依赖此接口，不感知底层数据库类型。

    线程安全:
      execute 方法应由子类保证线程安全（如使用连接池队列）。
    """

    def __init__(self, config: DBPoolConfig):
        """初始化连接池。

        Args:
            config: 连接池配置对象（主机/端口/用户名/密码/库名/池大小）
        """
        self.config = config  # 保存配置引用，子类可通过 self.config 访问

    @abstractmethod
    def execute(self, sql: str, params: tuple | None = None) -> list[dict[str, Any]]:
        """执行 SQL 查询并返回结果集。

        子类实现要求:
          - 支持参数化查询（防 SQL 注入）
          - 返回值统一为 [{"column_name": value}, ...] 格式
          - 自动管理连接获取与归还

        Args:
            sql:    待执行的 SQL 语句（可使用 %s / ? 占位符）
            params: 查询参数元组，用于参数化填充占位符

        Returns:
            查询结果列表，每行为一个 dict，key 为列名，value 为字段值
        """
        ...

    @abstractmethod
    def close(self) -> None:
        """关闭连接池中的所有连接并释放资源。

        应在应用优雅关闭时调用，确保不存在连接泄漏。
        实现应幂等 —— 重复调用不应报错。
        """
        ...
