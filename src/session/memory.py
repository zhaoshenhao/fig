r"""MemorySessionStore — 基于内存的会话存储实现。

本模块实现了 SessionStore 抽象接口的内存版本，使用进程内字典存储所有会话数据。
适用于开发环境、单进程部署或不需要持久化的场景。

设计决策：
1. **线程安全（threading.Lock）**：所有读写操作均加锁保护，确保多线程并发请求安全
2. **TTL 过期机制**：读取时惰性检查 last_active_at，超过 max_age 则自动删除
3. **容量上限（max_sessions）**：达到上限时驱逐最久未活跃的会话（LRU 风格）
4. **序列化/反序列化**：存储时调用 session.to_dict()，读取时调用 SessionData.from_dict()
5. **后台清理线程**：cleanup_loop 提供周期性过期清理（被动读取 + 主动清理双重保障）

与 RedisSessionStore 的区别：
- 内存存储：零网络开销、数据不持久化（进程重启丢失）
- Redis 存储：多 Worker 共享、持久化、适合生产环境

生命周期：
1. 初始化 → 设置 TTL 和容量上限
2. create() → 新建 SessionData 并存入字典
3. get() → 读取 + TTL 检查（过期则删除返回 None）
4. save() → 更新会话（同时刷新 last_active_at）
5. delete() → 显式删除
6. cleanup_loop() → 后台循环清理过期会话（可选）
"""

from __future__ import annotations

import threading
import time

from src.session.base import SessionStore
from src.session.data import SessionData


class MemorySessionStore(SessionStore):
    """基于进程内存的会话存储实现。

    使用 Python 内置 dict 存储所有会话，通过 threading.Lock 保证线程安全。
    支持 TTL 到期自动清理和容量上限驱逐策略。
    """

    def __init__(self, max_age: int = 3600, max_sessions: int = 2000):
        """初始化内存会话存储。

        Args:
            max_age: 会话最大存活时间（秒），默认 3600（1 小时）。
                     超过此时间未活跃的会话将被视为过期并从存储中移除。
            max_sessions: 最大会话数量，默认 2000。超出时创建新会话会驱逐最旧的会话。
                          设置上限的原因：防止内存无限增长导致 OOM。
        """
        # 会话主存储：{chat_id: session_dict}
        self._sessions: dict[str, dict] = {}
        self._max_age = max_age
        self._max_sessions = max_sessions
        # 线程锁：保护 _sessions 字典的并发读写
        # 使用 threading.Lock（非 RLock），因所有操作都是单一、短暂的临界区
        self._lock = threading.Lock()

    def get(self, chat_id: str) -> SessionData | None:
        """根据会话 ID 获取会话对象。

        返回前检查 TTL：如果会话超时未活跃，则自动删除并返回 None。
        这称为""惰性过期""策略，在读取时顺便清理，减少后台清理线程的负荷。

        Args:
            chat_id: 会话唯一标识

        Returns:
            SessionData 对象（仅当会话存在且未过期），否则 None
        """
        with self._lock:
            raw = self._sessions.get(chat_id)
        if raw is None:
            return None

        # 惰性 TTL 检查：读取时判断是否过期
        if time.time() - raw["last_active_at"] > self._max_age:
            with self._lock:
                # 双重检查：防止竞态条件（获取 raw 后到加锁前可能被其他操作刷新）
                self._sessions.pop(chat_id, None)
            return None

        # 从序列化字典还原为 SessionData 对象
        return SessionData.from_dict(raw)

    def create(self, workflow_name: str, return_mode: str) -> SessionData:
        """创建新的会话对象并存入存储。

        创建前检查容量：若已达 max_sessions 上限，则驱逐最久未活跃的旧会话。
        设计理由：避免内存无限增长导致 OOM，同时优先保留活跃会话。

        Args:
            workflow_name: 所属工作流名称
            return_mode: 返回模式（"full" / "text"）

        Returns:
            新创建的 SessionData 对象
        """
        with self._lock:
            # 容量检查：驱逐最久未活跃的会话（LRU 驱逐策略）
            if len(self._sessions) >= self._max_sessions:
                oldest_id = min(
                    self._sessions,
                    key=lambda cid: self._sessions[cid]["last_active_at"],
                )
                del self._sessions[oldest_id]

            session = SessionData(
                _workflow=workflow_name,
                return_mode=return_mode,
            )
            # 存储时序列化为字典（便于内存和网络传输）
            self._sessions[session.chat_id] = session.to_dict()
        return session

    def save(self, session: SessionData) -> None:
        """保存（更新）会话的状态到存储。

        同时刷新 last_active_at 为当前时间，表示该会话仍在活跃使用中。
        这是 TTL 机制的关键：只有被 save/touch 的会话才会续期。

        Args:
            session: 要保存的 SessionData 对象
        """
        # 刷新活跃时间，这是 TTL 续期的唯一途径
        session.last_active_at = time.time()
        with self._lock:
            self._sessions[session.chat_id] = session.to_dict()

    def delete(self, chat_id: str) -> bool:
        """显式删除指定会话。

        与 TTL 过期不同，这是主动清理操作（如用户主动结束会话）。

        Args:
            chat_id: 要删除的会话 ID

        Returns:
            True 如果会话存在并被删除，False 如果会话不存在
        """
        with self._lock:
            if chat_id in self._sessions:
                del self._sessions[chat_id]
                return True
        return False

    def touch(self, chat_id: str) -> None:
        """刷新会话的最后活跃时间（不修改会话内容）。

        用于活跃检测场景：如心跳检查、定期扫描等只需续期 TTL 的操作。
        相比 save() 更轻量，不需要序列化和重新赋值。

        Args:
            chat_id: 要续期的会话 ID
        """
        with self._lock:
            raw = self._sessions.get(chat_id)
            if raw is not None:
                # 直接修改字典中的值，无需重新赋值给 _sessions
                raw["last_active_at"] = time.time()

    def count(self) -> int:
        with self._lock:
            return len(self._sessions)

    def cleanup_expired(self) -> int:
        """主动清理所有已过期的会话（批量清理）。

        遍历所有会话，删除 last_active_at 超过 max_age 的条目。
        返回清理数量，可用于监控和日志。

        Returns:
            被清理的会话数量
        """
        now = time.time()
        with self._lock:
            # 找出所有过期会话 ID
            expired_ids = [
                cid
                for cid, raw in self._sessions.items()
                if now - raw["last_active_at"] > self._max_age
            ]
            for cid in expired_ids:
                del self._sessions[cid]
        return len(expired_ids)

    def cleanup_loop(self, interval: int, stop_event: threading.Event | None = None) -> None:
        """启动后台循环清理过期会话。

        使用 threading.Event.wait() 实现可中断的间隔循环。
        相比 sleep 的优势：stop_event.set() 可立即唤醒线程退出循环。

        典型用法：
            stop = threading.Event()
            t = threading.Thread(target=store.cleanup_loop, args=(300, stop), daemon=True)
            t.start()
            # ... 应用运行中 ...
            stop.set()  # 信号线程优雅退出

        Args:
            interval: 清理间隔（秒），建议 300（5 分钟）
            stop_event: 停止信号事件，None 则自动创建
        """
        if stop_event is None:
            stop_event = threading.Event()
        # 使用 Event.wait() 而非 time.sleep()：支持 set() 即时响应退出
        while not stop_event.wait(interval):
            self.cleanup_expired()
