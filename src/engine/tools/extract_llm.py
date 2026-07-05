"""
LLM 信息提取工具模块 (Extract LLM)

负责利用大语言模型从用户输入中提取结构化字段信息，
将提取结果存入会话的 data_map 中供后续节点使用。

与 extract_regex 的对比：
    - extract_llm: 使用 LLM 理解语义、提取复杂信息（如情感、意图、实体关系）
    - extract_regex: 使用正则表达式提取固定模式的信息（如订单号、手机号）

工作流程：
1. 根据配置的提取字段构建 LLM 提示词
2. 调用 LLM 进行语义理解和信息提取
3. 解析 LLM 返回的 JSON 结果
4. 将提取到的字段值存入 session.data_map

典型配置结构（config dict）：
    {
        "llm_provider": "default",    # LLM 供应商名称
        "extract": [
            {
                "key": "order_id",          # 提取的字段名
                "description": "订单编号"    # 字段描述（给 LLM 的提示）
            }
        ]
    }
"""

from __future__ import annotations

import json

from src.config import get_app_config
from src.session.data import SessionData


def extract_llm(config: dict, session: SessionData) -> dict:
    """
    使用 LLM 从用户输入中提取结构化信息。

    流程：
    1. 从 config["extract"] 获取要提取的字段列表
    2. 构建提取提示词（中文），明确要求 LLM 只返回 JSON
    3. 调用 LLM 进行信息提取
    4. 解析 LLM 返回的 JSON，处理可能的 markdown 代码块包装
    5. 将非空的提取结果存入 session.data_map

    边界情况处理：
        - extract 字段为空：直接返回 "extracted 0 fields"
        - LLM 返回的不是有效 JSON：捕获 JSONDecodeError，静默返回提取失败
        - LLM 返回包含 ```json 代码块的文本：_extract_json 自动剥离
        - 提取值为空字符串或 None：不存入 data_map

    Args:
        config (dict): 节点配置字典，包含：
            - llm_provider (str, 可选): LLM 供应商名称
            - extract (list[dict]): 要提取的字段列表，每个字段包含：
                - key (str): 字段名
                - description (str, 可选): 字段描述（给 LLM 的提示）
        session (SessionData): 当前会话数据对象

    Returns:
        dict: 包含以下键的字典：
            - text (str): 提取结果摘要，如 "extracted 2 fields"
            - extracted (list[str]): 成功提取的字段名列表
    """
    # 获取提取字段列表
    fields = config.get("extract", [])
    if not fields:
        # 无提取字段配置，直接返回
        return {"text": "extracted 0 fields", "extracted": []}

    app = get_app_config()
    # 获取 LLM 供应商配置
    provider = app.llm_provider(config.get("llm_provider", ""))

    # 构建字段描述文本，提供给 LLM 作为提取提示
    # 格式: "- field_key: 字段描述"
    field_descs = "\n".join(
        f"- {f['key']}: {f.get('description', f['key'])}"
        for f in fields
    )

    # 构建提取提示词（中文）
    query = session.current_query
    prompt = (
        f"从以下用户输入中提取信息，只返回JSON。\n\n"
        f"用户输入: {query}\n\n"
        f"提取字段:\n{field_descs}\n\n"
        f"只返回JSON对象，key是字段名，value是提取的值。未提取到的字段不包含在JSON中。"
    )

    # 延迟导入 LLMClient，避免循环依赖
    from src.llm.client import LLMClient

    # 创建 LLM 客户端并发送提取请求
    client = LLMClient(
        base_url=provider.base_url,
        api_key=provider.api_key,
        provider_type=provider.type,
    )
    response = client.chat(provider.model, [
        {"role": "system", "content": "你是一个信息提取器。只返回JSON，不要返回其他内容。"},
        {"role": "user", "content": prompt},
    ])
    # 从 OpenAI 兼容格式提取文本内容
    content = response["choices"][0]["message"]["content"]

    # 解析 LLM 返回的 JSON 文本
    try:
        parsed = _extract_json(content)
    except (json.JSONDecodeError, ValueError):
        # JSON 解析失败：可能是 LLM 返回了非 JSON 内容
        # 静默处理，返回提取 0 字段的结果
        return {"text": "extracted 0 fields", "extracted": []}

    # 将提取到的字段值存入 session.data_map
    # 仅存储非空值（非 None 且非空字符串）
    extracted = []
    for f in fields:
        key = f["key"]
        val = parsed.get(key)
        if val is not None and val != "":
            session.data_map[key] = str(val)
            extracted.append(key)

    return {"text": f"extracted {len(extracted)} fields", "extracted": extracted}


def _extract_json(text: str) -> dict:
    """
    从文本中提取 JSON 对象。

    处理逻辑：
    1. 如果文本以 ``` 开头（markdown 代码块），去除首尾的代码块标记行
    2. 使用 json.loads 解析为 Python 字典

    边界情况：
        - 文本为标准 JSON 字符串：直接解析
        - 文本为 ```json ... ``` 包裹的 markdown 格式：自动剥离标记
        - 文本为 ``` ... ```（无语言标识）：同样剥离
        - 文本为无效 JSON：抛出 json.JSONDecodeError，交由调用方处理

    Args:
        text (str): 可能包含 JSON 的文本

    Returns:
        dict: 解析后的 Python 字典

    Raises:
        json.JSONDecodeError: 文本不是有效的 JSON
    """
    text = text.strip()
    # 检测并剥离 markdown 代码块标记（``` 或 ```json）
    if text.startswith("```"):
        lines = text.split("\n")
        # 去除首行 (```json 或 ```)
        if lines[0].startswith("```"):
            lines = lines[1:]
        # 去除尾行 (```)
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines)
    # 解析 JSON 字符串为 Python 字典
    return json.loads(text)
