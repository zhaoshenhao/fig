"""PostgreSQL 连接池实现 —— 基于 psycopg2 和 Queue 的自研连接池。

与 MySQLPool 的实现差异:
  1. 连接字符串: psycopg2 使用 key=value 空格分隔的 DSN 格式
     (而非 pymysql 的命名参数)
  2. 连接归还: psycopg2 没有 ping 方法，归还时直接 put 回队列
     （psycopg2 连接关闭时会自动检测，复用概率更高）
  3. 字符集: psycopg2 默认 UTF-8，无需显式设置字符集参数

共同点（与 MySQLPool 一致）:
  - 基于 Queue 的线程安全连接池
  - 懒创建策略（需要使用才创建，优先复用）
  - execute 统一返回 [{"col": val}, ...] 格式
  - try/finally 异常安全

依赖:
  psycopg2 (可选依赖，运行时如未安装会给出明确错误提示)
"""

from __future__ import annotations  # 推迟类型注解求值

from queue import Queue  # 线程安全 FIFO 队列
from typing import Any

from src.db.base import DBPool, DBPoolConfig

# ---------------------------------------------------------------------------
# 惰性导入 psycopg2（可选依赖）
# ---------------------------------------------------------------------------

try:
    import psycopg2  # noqa: F401  # 仅用于检测是否安装
except ImportError:  # pragma: no cover
    psycopg2 = None  # type: ignore[assignment]  # 标记为未安装  # pragma: no cover


# ---------------------------------------------------------------------------
# PgPool
# ---------------------------------------------------------------------------

class PgPool(DBPool):
    """PostgreSQL 连接池 —— 基于 Queue 的线程安全连接池实现。

    使用示例:
        cfg = DBPoolConfig(type="postgresql", host="127.0.0.1", port=5432, ...)
        pool = PgPool(cfg)
        rows = pool.execute("SELECT * FROM users WHERE id = %s", (1,))
        pool.close()
    """

    def __init__(self, config: DBPoolConfig):
        """初始化 PostgreSQL 连接池。

        Args:
            config: 连接池配置（host/port/user/password/database/pool_size）

        Raises:
            RuntimeError: psycopg2 未安装
        """
        super().__init__(config)
        if psycopg2 is None:  # pragma: no cover
            raise RuntimeError(  # pragma: no cover
                "psycopg2 not installed; run: pip install psycopg2-binary"
            )
        # 线程安全队列：容量 = config.pool_size
        self._queue: Queue = Queue(maxsize=config.pool_size)
        self._created = 0  # 已创建的连接数（不超过 pool_size）

    def execute(self, sql: str, params: tuple | None = None) -> list[dict[str, Any]]:
        """执行 SQL 查询。

        流程（与 MySQLPool.execute 相同）:
          1. 从连接池获取连接
          2. 执行参数化 SQL（psycopg2 使用 %s 占位符）
          3. 从 cursor.description 提取列名
          4. 将结果转为统一 dict 格式
          5. finally 归还连接

        Args:
            sql:    SQL 语句，占位符使用 %s（psycopg2 风格）
            params: 参数元组

        Returns:
            list[dict]: 查询结果行列表
        """
        conn = self._acquire()
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                # 提取列名（仅查询语句有 description）
                columns = [col[0] for col in cursor.description] if cursor.description else []
                rows = cursor.fetchall()
                return [dict(zip(columns, row)) for row in rows]
        finally:
            self._release(conn)  # 确保连接归还

    def _acquire(self):
        """从连接池获取一个可用连接。

        策略（与 MySQLPool._acquire 相同）:
          1. 非阻塞尝试从队列取值
          2. 队列为空且未达上限 -> 创建新连接
          3. 队列为空且已达上限 -> 阻塞等待

        Postgres 连接通过 key=value DSN 字符串建立，示例:
          "host=localhost port=5432 user=postgres password=xxx dbname=mydb"
        """
        try:
            return self._queue.get(block=False)
        except Exception:
            if self._created < self.config.pool_size:
                # 拼接 psycopg2 的 DSN (Data Source Name) 连接字符串
                dsn = (
                    f"host={self.config.host} port={self.config.port} "
                    f"user={self.config.user} password={self.config.password} "
                    f"dbname={self.config.database}"
                )
                conn = psycopg2.connect(dsn)
                self._created += 1
                return conn
            return self._queue.get(block=True)

    def _release(self, conn) -> None:
        """将连接归还到连接池。

        PostgreSQL 处理:
          psycopg2 连接在关闭时后端会自动回收，且底层 socket 在服务端断开
          时会抛出异常，但连接对象在下次使用时可能已不可用。这里采用
          简单策略：直接放回队列，由 _acquire 时检测（连接失败时自愈）。

        Args:
            conn: psycopg2 connection 连接对象
        """
        try:
            self._queue.put_nowait(conn)
        except Exception:
            pass  # 队列满时忽略（理论上不会发生）

    def close(self) -> None:
        """关闭连接池中的所有连接。

        遍历队列取出所有连接并逐一关闭。
        应在应用关闭阶段单线程调用，确保无连接泄漏。
        """
        while not self._queue.empty():
            try:
                conn = self._queue.get_nowait()
                conn.close()  # 关闭底层 TCP 连接
            except Exception:
                break  # 安全退出
