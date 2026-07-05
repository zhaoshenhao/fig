r"""会话数据模型 — SessionData + TurnRecord 定义。

本模块定义了智能客服系统中与会话（Session）相关的核心数据结构：

- **TurnRecord**：单轮对话记录，包含用户输入、助手输出及时间戳
- **SessionData**：完整会话状态，包含历史对话、数据映射、节点执行轨迹等

设计决策：
- 使用 dataclass 实现，享受自动 __init__/__repr__/__eq__ 和 asdict 序列化
- SessionData 实现类字典协议（__getitem__/__setitem__/get/setdefault），方便工具函数统一存取
- history 使用 list[TurnRecord] 存储完整对话历史，支持按轮次/字符数裁剪
- 所有字段均有默认值（mutable 类型使用 field(default_factory=...)），确保无参构造可用
- from_dict / to_dict 方法提供与内存/Redis 存储之间的序列化桥梁
- trim_or_compress 支持 TTL 裁剪 + LLM 摘要压缩两阶段策略
"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any


def _new_chat_id() -> str:
    """生成全局唯一的会话 ID。

    格式：chat_ + 20 位十六进制随机字符串（uuid4 前 20 位）。
    使用 uuid4 而非自增 ID，避免分布式环境下的冲突。

    Returns:
        格式为 "chat_xxxxxxxxxxxxxxxxxxxx" 的唯一标识符
    """
    return f"chat_{uuid.uuid4().hex[:20]}"


@dataclass
class TurnRecord:
    """单轮对话记录。

    记录一次完整的 ""用户输入 → 助手输出"" 问答对及其时间戳。
    用于构建多轮对话的历史上下文。

    Attributes:
        input: 用户输入文本
        output: 助手/系统输出文本
        input_timestamp: 用户输入时间戳（Unix 时间）
        output_timestamp: 助手输出时间戳（Unix 时间）
    """
    input: str
    output: str
    input_timestamp: float
    output_timestamp: float


@dataclass
class SessionData:
    """完整会话状态数据模型。

    智能客服系统的核心会话对象，承载单次对话生命周期中的所有状态信息。
    包含以下功能分区：

    1. **标识信息**：chat_id、turn_id
    2. **时间信息**：created_at、last_active_at（用于 TTL 过期判断）
    3. **工作流信息**：_workflow（所属工作流）、return_mode（返回模式）
    4. **对话历史**：history（list[TurnRecord]）
    5. **数据映射**：data_map（节点间传递的键值对数据）
    6. **长记忆**：long_mem_data（跨会话持久化记忆）
    7. **执行追踪**：nodes（工作流节点执行记录列表）
    """

    # ---- 标识 ----
    # 使用 uuid4 生成全局唯一 ID，避免 Multi-worker 环境下的冲突
    chat_id: str = field(default_factory=_new_chat_id)
    # 当前对话轮次计数器，每轮 add_turn 后自增
    turn_id: int = 0

    # ---- 时间 ----
    # 会话创建时间，用于统计会话总时长
    created_at: float = field(default_factory=time.time)
    # 最后活跃时间，用于 TTL 过期判断（MemorySessionStore / RedisSessionStore）
    last_active_at: float = field(default_factory=time.time)

    # ---- 工作流 ----
    # 所属工作流名称（私有字段，通过 set/get 访问）
    _workflow: str = ""
    # 返回模式："full"（完整会话）|| "text"（仅文本）
    return_mode: str = "full"

    # ---- 对话历史 ----
    # 按时间顺序存储所有问答轮次，用于构建 LLM 上下文
    history: list[TurnRecord] = field(default_factory=list)

    # ---- 数据映射 ----
    # 节点间传递的临时键值对数据，如提取的实体、中间结果等
    data_map: dict[str, str] = field(default_factory=dict)

    # ---- 长记忆 ----
    # 跨会话持久化的记忆文本（如用户画像、偏好等）
    long_mem_data: str = ""

    # ---- 执行追踪 ----
    # 本次对话中所有工作流节点的执行记录（input → node1 → ... → output）
    nodes: list[dict] = field(default_factory=list)

    # ---- 类字典协议实现 ----
    # 实现以下方法使 SessionData 可像字典一样被工具函数统一存取，
    # 简化工具接口设计

    def __getitem__(self, key: str) -> Any:
        """通过 key 获取字段值（类字典访问）。

        Args:
            key: 字段名

        Returns:
            字段值
        """
        return getattr(self, key)

    def __setitem__(self, key: str, value: Any) -> None:
        """通过 key 设置字段值（类字典访问）。

        Args:
            key: 字段名
            value: 新值
        """
        setattr(self, key, value)

    def get(self, key: str, default: Any = None) -> Any:
        """获取字段值，不存在时返回默认值（类字典安全读取）。

        Args:
            key: 字段名
            default: 默认值

        Returns:
            字段值或默认值
        """
        return getattr(self, key, default)

    def __contains__(self, key: str) -> bool:
        """判断字段是否存在（支持 `"field" in session` 语法）。

        Args:
            key: 字段名

        Returns:
            True 如果字段存在
        """
        return hasattr(self, key)

    def setdefault(self, key: str, default: Any = None) -> Any:
        """设置默认值（类似 dict.setdefault），key 不存在时才赋值。

        Args:
            key: 字段名
            default: 默认值

        Returns:
            字段的当前值（原值或新设置的默认值）
        """
        if not hasattr(self, key):
            setattr(self, key, default)
        return getattr(self, key)

    def keys(self) -> set[str]:
        """返回所有 dataclass 字段名的集合。

        Returns:
            字段名集合（如 {"chat_id", "turn_id", "history", ...}）
        """
        return {f.name for f in self.__dataclass_fields__.values()}

    def to_dict(self) -> dict:
        """将 SessionData 序列化为纯字典（用于存储和传输）。

        使用 dataclasses.asdict() 进行深度转换，包括 history 中的 TurnRecord 列表。

        Returns:
            会话数据的字典表示
        """
        raw = asdict(self)
        return raw

    @classmethod
    def from_dict(cls, data: dict) -> SessionData:
        """从字典反序列化恢复 SessionData 对象。

        特别处理 history 字段：将字典列表自动转换为 TurnRecord 列表。
        支持从 Redis JSON（dict 形式）或内存存储恢复历史数据。

        Args:
            data: 会话数据的字典表示（通常来自 to_dict() 或存储层）

        Returns:
            重建的 SessionData 对象
        """
        # 弹出 history 字段单独处理，避免直接传入 TurnRecord 列表给构造函数
        history_raw = data.pop("history", [])
        instance = cls(**data)
        instance.history = []
        for item in history_raw:
            if isinstance(item, TurnRecord):
                # 已经是 TurnRecord（可能来自内存，未经过 JSON 序列化）
                instance.history.append(item)
            else:
                # JSON 反序列化后的 dict 形式，手动还原为 TurnRecord
                instance.history.append(TurnRecord(
                    input=item.get("input") or item.get("content", ""),
                    output=item.get("output", ""),
                    input_timestamp=item.get("input_timestamp", 0.0),
                    output_timestamp=item.get("output_timestamp", 0.0),
                ))
        return instance

    def add_turn(self, query_text: str, answer_text: str) -> None:
        """追加一轮问答到历史记录中。

        将用户问题和系统回答打包为 TurnRecord 并追加到 history 末尾，
        同时将 turn_id 自增 1。

        Args:
            query_text: 用户本次输入的文本
            answer_text: 系统本次输出的文本
        """
        now = time.time()
        self.history.append(TurnRecord(
            input=query_text,
            output=answer_text,
            input_timestamp=now,
            output_timestamp=now,
        ))
        self.turn_id += 1

    def trim_or_compress(
        self,
        max_turns: int | None = None,
        max_chars: int | None = None,
        keep: int = 20,
        compress_max_words: int = 1000,
        summary_base_url: str = "",
        summary_api_key: str = "",
        summary_model: str = "",
        summary_system_prompt: str = "",
    ) -> None:
        """对对话历史进行裁剪或 LLM 摘要压缩（二阶段策略）。

        阶段一（裁剪）：当历史轮次数或总字符数超过阈值时，丢弃超出部分（保留最近 keep 轮）。
        阶段二（摘要）：如果配置了 LLM 摘要服务（summary_base_url + summary_model），
        对被裁剪的旧轮次调用 LLM 生成压缩摘要，插入到保留历史的头部。

        设计理由：保留最近 keep 轮完整对话以保证上下文连贯性，对更早的轮次进行摘要压缩，
        在限定 token 预算的前提下尽可能保留历史信息。

        Args:
            max_turns: 最大允许的对话轮次数，超过则触发裁剪；None 表示不限
            max_chars: 最大允许的字符总数（input + output），超过则触发裁剪；None 表示不限
            keep: 裁剪后至少保留的最近轮次数（默认 20）
            compress_max_words: LLM 摘要的最大字数（默认 1000）
            summary_base_url: LLM 摘要服务的 API 地址
            summary_api_key: API 密钥
            summary_model: 摘要使用的模型名称
            summary_system_prompt: 摘要的系统提示词模板，支持 {max_words} 占位符
        """
        # 未设置任何限制，跳过
        if max_turns is None and max_chars is None:
            return
        if not self.history:
            return

        total_turns = len(self.history)
        total_chars = sum(len(t.input) + len(t.output) for t in self.history)
        keep = max(keep, 1)  # 至少保留 1 轮

        # 判断是否触发裁剪条件
        trigger_turns = max_turns is not None and total_turns > max_turns
        trigger_chars = max_chars is not None and total_chars > max_chars

        if not trigger_turns and not trigger_chars:
            return

        # 计算需要移除的轮次数 = 总轮次 - 保留轮次
        excess = total_turns - keep
        if excess <= 0:
            return

        # 分离出旧轮次（将被丢弃/压缩）和新轮次（将被保留）
        old_turns = self.history[:excess]
        self.history = self.history[excess:]

        # 如果配置了 LLM 摘要服务，生成摘要并插入到保留历史的头部
        if summary_base_url and summary_model:
            try:
                summary_text = _generate_summary(
                    old_turns,
                    base_url=summary_base_url,
                    api_key=summary_api_key,
                    model=summary_model,
                    max_words=compress_max_words,
                    system_prompt=summary_system_prompt,
                )
            except Exception:
                # 摘要生成失败时静默处理，不中断主流程
                summary_text = ""
        else:
            summary_text = ""

        if summary_text:
            # 将摘要作为特殊的 TurnRecord 插入历史头部
            self.history.insert(0, TurnRecord(
                input=f"[前{len(old_turns)}轮摘要]",
                output=summary_text,
                input_timestamp=old_turns[-1].input_timestamp,
                output_timestamp=old_turns[-1].output_timestamp,
            ))

    # ---- 便捷属性 ----

    @property
    def current_query(self) -> str:
        """获取当前轮次的用户查询文本。

        反向遍历 nodes 列表，找到最后一个名为 "input" 的节点的 text 内容。

        Returns:
            当前查询文本，若不存在则返回 ""
        """
        for node in reversed(self.nodes):
            if node["name"] == "input":
                return node["data"].get("text", "")
        return ""

    @property
    def current_context(self) -> str:
        """获取当前轮次的上下文文本（最近的非 input 节点的输出）。

        反向遍历 nodes 列表，找到第一个非 input 节点的 text 内容。

        Returns:
            当前上下文文本，若不存在则返回 ""
        """
        for node in reversed(self.nodes):
            text = node["data"].get("text", "")
            if text and node["name"] != "input":
                return text
        return ""

    @property
    def completed_turns(self) -> int:
        """返回已完成的对话轮次数。

        Returns:
            history 列表的长度
        """
        return len(self.history)


def _generate_summary(
    turns: list[TurnRecord],
    base_url: str,
    api_key: str,
    model: str,
    max_words: int,
    system_prompt: str,
) -> str:
    """调用 LLM 将多轮对话压缩为摘要文本。

    将 TurnRecord 列表拼接为对话文本，通过 LLMClient 调用大模型进行摘要生成。
    与主流程解耦（独立函数 + 延迟导入），避免循环依赖。

    Args:
        turns: 需要摘要的对话轮次列表
        base_url: LLM API 地址
        api_key: API 密钥
        model: 模型名称
        max_words: 摘要最大字数
        system_prompt: 系统提示词模板，支持 {max_words} 占位符

    Returns:
        LLM 生成的摘要文本
    """
    # 延迟导入 LLMClient，避免循环依赖
    from src.llm.client import LLMClient  # noqa: PLC0415

    # 将多轮对话拼接为纯文本格式
    conversation = "\n\n".join(
        f"User: {t.input}\nAssistant: {t.output}"
        for t in turns
    )
    # 构建摘要提示词：使用自定义模板或默认模板
    prompt = (
        system_prompt.replace("{max_words}", str(max_words))
        if system_prompt
        else f"请将以下对话压缩为{max_words}字以内的摘要，保留关键信息、用户意图和已确认的事实。"
    )

    client = LLMClient(base_url=base_url, api_key=api_key)
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": f"请压缩以下对话记录：\n\n{conversation}"},
    ]
    response = client.chat(model, messages)
    return response["choices"][0]["message"]["content"]
