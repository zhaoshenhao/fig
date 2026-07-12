"""MySQL 连接池实现 —— 基于 PyMySQL 和 Queue 的自研连接池。

实现原理:
  使用 Python 标准 Queue 作为连接池的底层数据结构。
  - Queue(maxsize=N): 最多同时持有 N 个活跃连接
  - _acquire(): 非阻塞获取 -> 容量未满时创建新连接 -> 容量满时阻塞等待
  - _release(): 归还连接到队列（连接健康则放回，异常则丢弃）

技术细节:
  - 客户端字符集: utf8mb4（支持完整的 Unicode，包括 Emoji）
  - 连接复用: 归还前 ping 检测连接存活性
  - 线程安全: Queue 自身保证 get/put 操作的原子性
  - 异常安全: execute 使用 try/finally 确保连接一定归还

依赖:
  pymysql (可选依赖，运行时如未安装会给出明确错误提示)
"""

from __future__ import annotations  # 推迟类型注解求值

from queue import Queue  # 线程安全的 FIFO 队列，作为连接池的实现载体
from typing import Any

from src.db.base import DBPool, DBPoolConfig

# ---------------------------------------------------------------------------
# 惰性导入 PyMySQL（可选依赖）
# ---------------------------------------------------------------------------

try:
    import pymysql
except ImportError:  # pragma: no cover
    pymysql = None  # type: ignore[assignment]  # 标记为未安装  # pragma: no cover


# ---------------------------------------------------------------------------
# MySQLPool
# ---------------------------------------------------------------------------

class MySQLPool(DBPool):
    """MySQL 连接池 —— 基于 Queue 的线程安全连接池实现。

    使用示例:
        cfg = DBPoolConfig(type="mysql", host="127.0.0.1", ...)
        pool = MySQLPool(cfg)
        rows = pool.execute("SELECT * FROM users WHERE id = %s", (1,))
        pool.close()
    """

    def __init__(self, config: DBPoolConfig):
        """初始化 MySQL 连接池。

        Args:
            config: 连接池配置（host/port/user/password/database/pool_size）

        Raises:
            RuntimeError: PyMySQL 未安装
        """
        super().__init__(config)
        if pymysql is None:  # pragma: no cover
            raise RuntimeError(  # pragma: no cover
                "pymysql not installed; run: pip install pymysql"
            )
        # 线程安全队列：容量 = config.pool_size，阻塞式 put/get
        self._queue: Queue = Queue(maxsize=config.pool_size)
        self._created = 0  # 已创建的连接数（不超过 pool_size）

    def execute(self, sql: str, params: tuple | None = None) -> list[dict[str, Any]]:
        """执行 SQL 查询。

        流程:
          1. 从连接池获取一个连接 (_acquire)
          2. 执行参数化 SQL 查询
          3. 通过 cursor.description 获取列名
          4. 将结果转为 [{"col": val}, ...] 格式
          5. finally 中保证归还连接 (_release)

        Args:
            sql:    SQL 语句，占位符使用 %s（PyMySQL 风格）
            params: 参数元组

        Returns:
            list[dict]: 查询结果行列表
        """
        conn = self._acquire()  # 获取连接（可能阻塞）
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                # 提取列名列表（仅 SELECT 查询有 description）
                columns = [col[0] for col in cursor.description] if cursor.description else []
                rows = cursor.fetchall() if cursor.description else []
                # 提交事务，确保 INSERT/UPDATE/DDL 写入持久化（pymysql 默认 autocommit=off）
                conn.commit()
                # 将 (val1, val2) -> {"col1": val1, "col2": val2}
                return [dict(zip(columns, row)) for row in rows]
        finally:
            self._release(conn)  # 确保连接归还（即使异常）

    def _acquire(self):
        """从连接池获取一个可用连接。

        策略（优先创建 -> 阻塞等待）:
          1. 非阻塞尝试从队列取值（Queue.get(block=False)）
          2. 队列为空且未达容量上限 -> 创建新连接并返回
          3. 队列为空且已达容量上限 -> 阻塞等待直到有连接归还

        Returns:
            pymysql.Connection 连接对象
        """
        try:
            # 尝试非阻塞获取空闲连接
            return self._queue.get(block=False)
        except Exception:
            # 队列为空
            if self._created < self.config.pool_size:
                # 未达容量上限：创建新连接
                conn = pymysql.connect(
                    host=self.config.host,
                    port=self.config.port,
                    user=self.config.user,
                    password=self.config.password,
                    database=self.config.database,
                    charset="utf8mb4",  # 完整 Unicode 字符集
                )
                self._created += 1
                return conn
            # 已达容量上限：阻塞等待直到有空闲连接
            return self._queue.get(block=True)

    def _release(self, conn) -> None:
        """将连接归还到连接池。

        归还前通过 ping(reconnect=True) 检测连接是否存活:
          - 连接存活/可重连: 放回队列供后续复用
          - 无法重连: 关闭并丢弃，递减 _created，允许后续按需重建
            （避免把坏连接放回池导致下次取到死连接）

        Args:
            conn: pymysql.Connection 连接对象
        """
        try:
            conn.ping(reconnect=True)  # 检测连接并尝试自动重连
            self._queue.put_nowait(conn)
        except Exception:
            # 连接损坏且无法重连：丢弃而非放回，防止污染连接池
            try:
                conn.close()
            except Exception:
                pass
            self._created -= 1

    def close(self) -> None:
        """关闭连接池中的所有连接。

        遍历队列取出所有连接并逐一关闭。
        注意: 此方法假设调用时没有其他线程正在使用连接，
        应在应用关闭阶段单线程调用。
        """
        while not self._queue.empty():
            try:
                conn = self._queue.get_nowait()
                conn.close()  # 关闭底层 TCP 连接
            except Exception:
                break  # 队列空或连接已关闭，安全退出
