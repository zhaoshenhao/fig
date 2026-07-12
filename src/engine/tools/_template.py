"""工具占位符解析公共模块（W4-4）。

统一各工具（api_call / web_search / db_query / code_exec）的模板占位符替换逻辑，
消除重复实现、保证行为一致。

支持的占位符（超集）：
    {{query}}          当前用户查询文本
    {{<field>}}        节点输出字段（session.nodes[*].data）或 data_map 字段
    {{chat_id}}        会话 ID
    {{_workflow}}      当前工作流名称
    {{return_mode}}    返回模式
    {{long_mem_data}}  长期记忆数据
    {{data_map}}       整个 data_map 的 JSON 字符串
"""

from __future__ import annotations

import json

from src.session.data import SessionData

_META_KEYS = ("chat_id", "_workflow", "return_mode", "long_mem_data")


def resolve_template(template: str, session: SessionData) -> str:
    """将模板中的占位符替换为会话中的实际值。

    快速路径：模板不含 "{{" 时直接返回。

    替换来源优先级（后者覆盖前者）：
      1. 节点输出字段（session.nodes[*].data）
      2. data_map 字段
      3. 会话元数据（chat_id / _workflow / return_mode / long_mem_data）

    Args:
        template: 含占位符的字符串
        session:  当前会话

    Returns:
        替换后的字符串
    """
    if not template or "{{" not in template:
        return template

    result = template.replace("{{query}}", session.current_query or "")

    # 节点输出字段（后续节点覆盖前序同名字段）
    for node in getattr(session, "nodes", []) or []:
        for key, value in (node.get("data") or {}).items():
            if isinstance(value, str):
                result = result.replace(f"{{{{{key}}}}}", value)

    # data_map 提取字段
    for key, val in session.data_map.items():
        if isinstance(val, str):
            result = result.replace(f"{{{{{key}}}}}", val)

    # 会话级元数据
    for key in _META_KEYS:
        val = session.get(key, "")
        if isinstance(val, str):
            result = result.replace(f"{{{{{key}}}}}", val)

    # 整个 data_map 的 JSON
    if "{{data_map}}" in result:
        result = result.replace(
            "{{data_map}}", json.dumps(session.data_map, ensure_ascii=False)
        )

    return result
