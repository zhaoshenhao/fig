"""
LLM 调用工具模块

负责通过配置的大语言模型提供商（LLM Provider）发起对话请求，
将会话上下文和历史记录组装为消息列表，发送给模型并返回生成的文本内容。

主要功能：
- 从会话数据中提取当前查询和历史对话
- 解析系统提示词中的占位符（如 {{context}}、{{query}} 等）
- 通过统一的 LLMClient 调用指定模型
- 记录 LLM 调用次数到 Prometheus 监控指标

典型配置字段（config dict）：
    - llm_provider (str): 使用的 LLM 供应商名称（对应 auth.yaml 中的 provider key）
    - system_prompt (str): 系统提示词模板，支持 {{context}}、{{query}}、{{data_map}}、
      {{long_mem}}、{{history}} 等占位符
"""

import json

from src.config import get_app_config
from src.metrics.prometheus import llm_calls_total
from src.session.data import SessionData

_llm_clients: dict[str, object] = {}


def _get_llm_client(provider) -> object:
    from src.llm.client import LLMClient

    key = f"{provider.type}:{provider.base_url}:{provider.api_key[:8]}"
    if key not in _llm_clients:
        _llm_clients[key] = LLMClient(
            base_url=provider.base_url,
            api_key=provider.api_key,
            provider_type=provider.type,
        )
    return _llm_clients[key]


def llm_tool(config: dict, session: SessionData) -> dict:
    """
    执行一次 LLM 对话调用。

    工作流程：
    1. 从全局配置中根据 config["llm_provider"] 获取 LLM 供应商配置
    2. 解析系统提示词模板中的占位符变量
    3. 组装完整的消息列表：[系统提示词] + [历史对话轮次] + [当前用户查询]
    4. 通过 LLMClient 发送请求并解析响应
    5. 记录调用指标

    Args:
        config (dict): 节点配置字典，包含以下字段：
            - llm_provider (str, 可选): LLM 供应商名称，为空时使用默认供应商
            - system_prompt (str, 可选): 系统提示词模板字符串
        session (SessionData): 当前会话数据对象，包含：
            - current_query (str): 当前用户输入
            - current_context (str): 当前上下文（来自上游 RAG 检索等）
            - history (list[HistoryTurn]): 对话历史轮次列表
            - data_map (dict): 工具提取的结构化数据映射
            - long_mem_data (str): 长期记忆文本

    Returns:
        dict: 包含以下键的字典：
            - text (str): LLM 生成的文本回复内容
            - model (str): 使用的模型名称
    """
    # 获取全局应用配置
    app = get_app_config()
    # 根据配置中的 llm_provider 字段获取具体的 LLM 供应商配置对象
    # config.get("llm_provider", "") 返回空字符串时，app.llm_provider("") 返回默认供应商
    provider = app.llm_provider(config.get("llm_provider", ""))

    # 获取系统提示词模板和会话数据
    system_prompt = config.get("system_prompt", "")
    query = session.current_query
    context_text = session.current_context

    # 解析系统提示词中的占位符，将 {{context}}、{{query}} 等替换为实际值
    system_prompt = _resolve_placeholders(
        system_prompt, session, context_text, query
    )

    # 组装消息列表：以系统提示词开头
    messages = [{"role": "system", "content": system_prompt}]

    # 将历史对话轮次追加到消息列表中（user/assistant 交替）
    for turn in session.history:
        messages.append({"role": "user", "content": turn.input})
        messages.append({"role": "assistant", "content": turn.output})

    # 最后追加当前用户查询
    messages.append({"role": "user", "content": query})

    client = _get_llm_client(provider)

    stream_cb = getattr(session, "stream_callback", None)
    if stream_cb:
        full_text_parts: list[str] = []
        for token in client.stream_chat(provider.model, messages):
            full_text_parts.append(token)
            stream_cb(token)
        content = "".join(full_text_parts)
    else:
        response = client.chat(provider.model, messages)
        content = response["choices"][0]["message"]["content"]

    # 增加 LLM 调用计数器（Prometheus 指标），按模型名打标签
    llm_calls_total.inc({"model": provider.model})

    return {"text": content, "model": provider.model}


def _resolve_placeholders(
    template: str, session: SessionData, context: str, query: str
) -> str:
    """
    解析提示词模板中的占位符变量。

    支持的占位符：
        - {{context}}: 当前上下文文本（来自 RAG 检索或上游节点输出）
        - {{query}}: 当前用户查询文本
        - {{data_map}}: 已提取的结构化数据，以 JSON 字符串形式替换
        - {{long_mem}}: 长期记忆数据文本
        - {{history}}: 历史对话的格式化文本，每轮格式为 "用户: ...\n客服: ..."

    Args:
        template (str): 包含占位符的模板字符串
        session (SessionData): 当前会话数据，提供 data_map、long_mem_data、history
        context (str): 当前上下文字符串
        query (str): 当前用户查询

    Returns:
        str: 替换了所有占位符后的字符串
    """
    # 替换上下文和查询占位符（最简单的直接替换）
    result = template.replace("{{context}}", context)
    result = result.replace("{{query}}", query)

    # 替换 data_map 占位符：将结构化数据转为 JSON 字符串
    # ensure_ascii=False 确保中文字符不被转义为 \uXXXX
    result = result.replace(
        "{{data_map}}", json.dumps(session.data_map, ensure_ascii=False)
    )

    # 替换长期记忆占位符
    result = result.replace("{{long_mem}}", session.long_mem_data)

    # 替换历史对话占位符
    # 仅在模板中存在 {{history}} 时才进行格式化，避免不必要计算
    if "{{history}}" in result:
        history_text = "\n".join(
            f"用户: {t.input}\n客服: {t.output}"
            for t in session.history
        )
        result = result.replace("{{history}}", history_text)
    return result
