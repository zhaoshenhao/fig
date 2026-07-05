r"""session 包 — 会话管理模块。

本模块提供智能客服系统的会话生命周期管理，包括：

- **SessionData**：会话核心数据模型，承载对话状态、历史、节点执行轨迹
- **SessionStore**：会话存储抽象接口（定义 get/create/save/delete/touch 规范）
- **MemorySessionStore**：基于内存的会话存储实现（开发/单进程）
- **RedisSessionStore**：基于 Redis 的会话存储实现（生产/多 Worker 共享）

导出列表：
    SessionStore：抽象基类
    SessionData：数据模型
    MemorySessionStore：内存实现
    RedisSessionStore：Redis 实现

工厂函数：
    create_session_store(config)：根据配置字典创建对应的存储实例

使用示例：
    >>> from src.session import create_session_store, SessionData, MemorySessionStore
    >>> store = create_session_store({"store": "memory", "max_age": 3600})
    >>> session = store.create("default_workflow", "full")
    >>> session.add_turn("你好", "你好！有什么可以帮您？")
    >>> store.save(session)
"""

from src.session.base import SessionStore
from src.session.data import SessionData
from src.session.memory import MemorySessionStore
from src.session.redis_store import RedisSessionStore

# 模块对外导出的公共 API
__all__ = ["SessionStore", "SessionData", "MemorySessionStore", "RedisSessionStore"]


def create_session_store(config: dict) -> SessionStore:
    """根据配置字典创建会话存储实例（工厂函数）。

    根据 config["store"] 的值选择存储后端：
    - "redis"：创建 RedisSessionStore（多 Worker 共享，持久化存储）
    - "memory" 或未指定：创建 MemorySessionStore（单进程，零依赖）

    Args:
        config: 配置字典，支持以下顶层键：
            - store (str): 存储类型，可选 "redis" 或 "memory"（默认 "memory"）
            - max_age (int): 会话 TTL（秒），默认 3600
            - redis (dict): Redis 专项配置（仅 store="redis" 时生效）
                - url (str): Redis 连接 URL
                - prefix (str): key 前缀
            - memory (dict): 内存存储专项配置（仅 store="memory" 时生效）
                - max_sessions (int): 最大会话数

    Returns:
        SessionStore 实例（MemorySessionStore 或 RedisSessionStore）
    """
    store_type = config.get("store", "memory")

    if store_type == "redis":
        # 提取 Redis 配置并创建 Redis 存储实例
        redis_cfg = config.get("redis", {})
        max_age = config.get("max_age", 3600)
        return RedisSessionStore(
            url=redis_cfg.get("url", "redis://localhost:6379/0"),
            prefix=redis_cfg.get("prefix", "kf:sess:"),
            max_age=max_age,
        )

    # 默认：内存存储
    memory_cfg = config.get("memory", {})
    max_age = config.get("max_age", 3600)
    return MemorySessionStore(
        max_age=max_age,
        max_sessions=memory_cfg.get("max_sessions", 2000),
    )
