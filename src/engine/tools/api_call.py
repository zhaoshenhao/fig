"""
外部 API 调用工具模块 (API Call)

负责在工作流中发起 HTTP 请求调用外部 REST API，
将响应内容返回供下游节点使用。

功能特性：
- 支持 GET / POST / PUT / DELETE 等 HTTP 方法
- 请求 URL 和 headers 支持占位符（{{query}}、{{key}}、{{chat_id}} 等）
- 可配置超时时间
- 支持 JSON body
- 自动错误处理和日志记录

典型配置结构（config dict）：
    {
        "url": "https://api.example.com/order/{{order_id}}",
        "method": "GET",
        "headers": {"Authorization": "Bearer {{token}}"},
        "body": {"status": "pending"},
        "timeout": 30
    }
"""

from __future__ import annotations

from src.logger import get_logger
from src.session.data import SessionData

_log = get_logger(__name__)


def api_call(config: dict, session: SessionData) -> dict:
    """
    执行一次外部 HTTP API 调用。

    流程：
    1. 从 config 获取 URL、HTTP 方法、请求头、请求体和超时配置
    2. 解析 URL 和 headers 中的占位符变量
    3. 使用 httpx2 发起请求
    4. 检查响应状态码，非 2xx 抛出异常
    5. 返回响应文本（截断到 5000 字符）

    边界情况处理：
        - url 为空：直接返回错误，不发起请求
        - 请求异常（网络错误、超时、非 2xx）：记录错误日志，返回错误信息
        - 响应体过长：截断到前 5000 字符

    Args:
        config (dict): 节点配置字典，包含：
            - url (str, 必填): 目标 API URL，支持 {{query}} 等占位符
            - method (str, 可选): HTTP 方法，默认 "GET"
            - headers (dict, 可选): HTTP 请求头，支持占位符
            - body (dict, 可选): JSON 请求体
            - timeout (int, 可选): 请求超时秒数，默认 30
        session (SessionData): 当前会话数据对象

    Returns:
        dict: 包含以下键的字典：
            - text (str): API 响应文本（截断到 5000 字符）
            - status_code (int): HTTP 响应状态码
            - url (str): 最终解析后的请求 URL
            错误时返回：
            - text (str): 空字符串
            - error (str): 错误描述
            - url (str): 请求的 URL
    """
    url = config.get("url", "")
    if not url:
        return {"text": "", "error": "no url specified"}

    method = config.get("method", "GET").upper()
    headers = config.get("headers", {})
    body = config.get("body")
    timeout = config.get("timeout", 30)

    # 解析请求头中的占位符（如 {{token}}、{{chat_id}}）
    headers = {
        k: _resolve(v, session) for k, v in (headers or {}).items()
    }
    # 解析 URL 中的占位符（如 {{order_id}}、{{query}}）
    resolved_url = _resolve(url, session)

    import httpx2

    try:
        # 使用 httpx2 发起 HTTP 请求
        resp = httpx2.request(
            method, resolved_url, headers=headers, json=body, timeout=timeout,
        )
        # 检查 HTTP 状态码，非 2xx 自动抛出异常
        resp.raise_for_status()
        # 截断响应体到 5000 字符，防止超大响应占用过多内存
        result = resp.text[:5000]
        return {"text": result, "status_code": resp.status_code, "url": resolved_url}
    except Exception as e:
        # 请求失败：记录详细日志并返回错误信息
        _log.error("api_call failed", extra={"url": resolved_url, "error": str(e)})
        return {"text": "", "error": str(e), "url": resolved_url}


def _resolve(template: str, session: SessionData) -> str:
    """解析字符串模板中的占位符（委托公共实现 `_template.resolve_template`）。"""
    from src.engine.tools._template import resolve_template
    return resolve_template(template, session)
