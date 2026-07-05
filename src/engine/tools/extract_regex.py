"""
正则表达式提取工具模块 (Extract Regex)

负责使用正则表达式从用户输入中提取结构化信息，
将匹配结果存入会话的 data_map 中供后续节点使用。

与 extract_llm 的对比：
    - extract_llm: 使用 LLM 语义理解，适合提取意图、情感等复杂信息
    - extract_regex: 使用正则表达式，适合提取固定模式的信息（如手机号、订单号、日期等）

工作流程：
1. 遍历配置的提取字段，每个字段包含 key 和正则 pattern
2. 对用户查询执行 re.findall（全文本全局匹配）
3. 单次匹配直接存储值，多次匹配存储 JSON 数组

典型配置结构（config dict）：
    {
        "extract": [
            {
                "key": "phone",          # 提取的字段名
                "pattern": "1[3-9]\\d{9}" # 正则表达式模式
            }
        ]
    }
"""

from __future__ import annotations

import json
import re

from src.session.data import SessionData


def extract_regex(config: dict, session: SessionData) -> dict:
    """
    使用正则表达式从用户输入中提取结构化信息。

    流程：
    1. 从 config["extract"] 获取要提取的字段列表
    2. 遍历每个字段，使用 re.findall 执行全局匹配
    3. 根据匹配数量决定存储方式：
        - 1 次匹配：直接存储为字符串
        - 多次匹配：存储为 JSON 数组字符串

    边界情况处理：
        - extract 字段为空：直接返回 "matched 0 fields"
        - key 或 pattern 为空：跳过该字段
        - 正则表达式有语法错误（re.error）：跳过该字段，不影响其他字段的提取
        - 无匹配结果：跳过该字段
        - 单次匹配 vs 多次匹配：自动区分，确保 data_map 中存储格式一致

    Args:
        config (dict): 节点配置字典，包含：
            - extract (list[dict]): 要提取的字段列表，每个字段包含：
                - key (str): 字段名，用于 data_map 的键
                - pattern (str): 正则表达式模式字符串
        session (SessionData): 当前会话数据对象

    Returns:
        dict: 包含以下键的字典：
            - text (str): 匹配结果摘要，如 "matched 2 fields"
            - extracted (list[str]): 成功匹配的字段名列表
    """
    # 获取提取字段列表
    fields = config.get("extract", [])
    if not fields:
        return {"text": "matched 0 fields", "extracted": []}

    # 获取用户查询文本
    query = session.current_query
    extracted = []

    for f in fields:
        key = f.get("key", "")
        pattern = f.get("pattern", "")
        # 跳过配置不完整的字段（缺少 key 或 pattern）
        if not key or not pattern:
            continue

        # 执行正则匹配，捕获 re.error 异常（无效正则表达式）
        try:
            matches = re.findall(pattern, query)
        except re.error:
            # 正则表达式语法错误，跳过该字段
            continue

        # 无匹配结果，跳过该字段
        if not matches:
            continue

        # 根据匹配次数决定存储格式
        if len(matches) == 1:
            # 单次匹配：直接存储匹配到的字符串
            session.data_map[key] = str(matches[0])
        else:
            # 多次匹配：存储为 JSON 数组字符串，方便后续解析
            session.data_map[key] = json.dumps(
                [str(m) for m in matches], ensure_ascii=False
            )

        extracted.append(key)

    return {"text": f"matched {len(extracted)} fields", "extracted": extracted}
