"""DB 模块导出 —— 数据库连接池的统一入口。

本模块对外暴露的核心 API:
  create_pool():    根据 DBPoolConfig 创建指定类型的连接池
  get_db_pool():    按名称获取已创建的连接池
  close_all_pools(): 关闭所有连接池（应用关闭时调用）

内部管理一个全局 _pools 字典，key 为连接池名称，value 为 DBPool 实例。

使用示例:
    from src.db import create_pool, get_db_pool
    from src.db.base import DBPoolConfig

    config = DBPoolConfig(type="mysql", host="127.0.0.1", database="mydb", ...)
    create_pool("default", config)

    pool = get_db_pool("default")
    rows = pool.execute("SELECT * FROM users")
"""

from __future__ import annotations  # 推迟类型注解求值

from src.db.base import DBConfig, DBPool, DBPoolConfig
from src.db.mysql_pool import MySQLPool
from src.db.pg_pool import PgPool

# 公开 API 清单（IDE 友好）
__all__ = ["DBConfig", "DBPoolConfig", "DBPool", "create_pool", "get_db_pool", "close_all_pools"]

# ---------------------------------------------------------------------------
# 模块级连接池注册表
# ---------------------------------------------------------------------------

_pools: dict[str, DBPool] = {}  # {pool_name: DBPool instance} 全局连接池注册表


# ---------------------------------------------------------------------------
# 公共 API
# ---------------------------------------------------------------------------

def create_pool(name: str, config: DBPoolConfig) -> DBPool:
    """根据配置创建数据库连接池并注册到全局表中。

    支持的数据库类型:
      - "mysql"       -> MySQLPool (pymysql)
      - "postgresql"  -> PgPool (psycopg2)

    同名连接池会被覆盖（先关闭旧池再创建新池）。

    Args:
        name:   连接池唯一名称（如 "default", "analytics"）
        config: 连接池配置对象

    Returns:
        创建的 DBPool 实例

    Raises:
        ValueError: 不支持的数据库类型
    """
    if config.type == "mysql":
        pool = MySQLPool(config)
    elif config.type == "postgresql":
        pool = PgPool(config)
    else:
        raise ValueError(f"unsupported db type: {config.type}")
    _pools[name] = pool  # 注册到全局表
    return pool


def get_db_pool(name: str) -> DBPool:
    """按名称获取已创建的连接池。

    必须先调用 create_pool() 创建连接池后，此函数才能正常工作。

    Args:
        name: 连接池名称

    Returns:
        DBPool 实例

    Raises:
        KeyError: 指定名称的连接池不存在
    """
    if name not in _pools:
        raise KeyError(f"db pool '{name}' not found. call create_pool() first.")
    return _pools[name]


def close_all_pools() -> None:
    """关闭所有已注册的连接池并清空注册表。

    应在应用优雅关闭（shutdown）阶段调用，确保:
      - 所有数据库连接正常关闭
      - 无连接泄漏（TCP 连接正常断开）
      - 队列资源被释放

    实现细节:
      遍历 _pools 副本（list(_pools.items())）避免在迭代时修改字典，
      逐一调用 pool.close() 后清空 _pools。
    """
    for name, pool in list(_pools.items()):
        pool.close()
    _pools.clear()
