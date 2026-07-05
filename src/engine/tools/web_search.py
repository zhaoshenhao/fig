"""
网页搜索工具模块 (Web Search)

负责在工作流中执行互联网搜索，将搜索结果返回供下游 LLM 节点使用。

目前支持的搜索引擎：
    - DuckDuckGo（默认）：使用 HTML 接口，不需要 API Key
      通过解析 DuckDuckGo HTML 搜索页面获取结果

查询模板支持占位符：
    - {{query}}: 当前用户查询文本
    - {{key}}: session.data_map 中的字段值

典型配置结构（config dict）：
    {
        "query_template": "{{query}}",   # 搜索查询模板
        "limit": 5,                       # 最大结果数
        "engine": "duckduckgo"            # 搜索引擎
    }
"""

from __future__ import annotations

import re

from src.logger import get_logger
from src.session.data import SessionData

_log = get_logger(__name__)


def web_search(config: dict, session: SessionData) -> dict:
    """
    执行一次互联网搜索。

    流程：
    1. 解析查询模板中的占位符，生成最终搜索词
    2. 根据配置的搜索引擎选择对应的搜索实现
    3. 获取搜索结果并格式化为文本

    Args:
        config (dict): 节点配置字典，包含：
            - query_template (str, 可选): 查询模板，默认 "{{query}}"
            - limit (int, 可选): 最大结果数，默认 5
            - engine (str, 可选): 搜索引擎，默认 "duckduckgo"
        session (SessionData): 当前会话数据对象

    Returns:
        dict: 包含以下键的字典：
            - text (str): 格式化的搜索结果文本（markdown 格式）
            - results (list[dict]): 原始搜索结果列表，每个结果包含 title、url、snippet
            错误时：
            - text (str): 错误或空结果描述
            - error (str): 错误信息（有 error 时存在）
            - results (list): 空列表
    """
    # 解析查询模板占位符，生成最终搜索词
    query = _resolve(config.get("query_template", "{{query}}"), session)
    limit = config.get("limit", 5)
    engine = config.get("engine", "duckduckgo")

    if engine == "duckduckgo":
        return _search_duckduckgo(query, limit)
    # 未知搜索引擎，返回错误提示
    return {"text": f"unknown search engine: {engine}", "results": []}


def _search_duckduckgo(query: str, limit: int) -> dict:
    """
    通过 DuckDuckGo HTML 接口执行搜索。

    工作方式：
    1. 向 DuckDuckGo HTML 搜索端点发送 POST 请求
    2. 使用正则表达式解析 HTML 结果页面
    3. 提取每个结果的标题、URL 和摘要片段
    4. 格式化为 markdown 链接列表

    注意：DuckDuckGo HTML 接口可能被限流或返回 CAPTCHA，
    此时返回空结果或错误信息。

    Args:
        query (str): 搜索查询词
        limit (int): 最大结果数，实际返回可能少于该值

    Returns:
        dict: 包含以下键的字典：
            - text (str): 格式化的搜索结果文本
            - results (list[dict]): 结果列表
            错误时：
            - text (str): 空字符串或 "no results found" 消息
            - error (str): 错误描述
            - results (list): 空列表
    """
    import httpx2

    url = "https://html.duckduckgo.com/html/"
    try:
        # 向 DuckDuckGo HTML 端点发送 POST 请求
        # 使用表单编码方式发送查询参数
        resp = httpx2.post(
            url,
            data={"q": query},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15,
        )
    except Exception as e:
        # 网络错误或超时，记录日志并返回错误
        _log.error("web_search failed", extra={"query": query, "error": str(e)})
        return {"text": "", "error": str(e), "results": []}

    html = resp.text
    results = []

    # 使用正则表达式解析 DuckDuckGo HTML 搜索结果
    # result__a 类包含标题和链接，result__snippet 类包含摘要
    # re.DOTALL 使 . 匹配换行符，re.IGNORECASE 忽略 HTML 大小写
    for match in re.finditer(
        r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?'
        r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
        html,
        re.DOTALL | re.IGNORECASE,
    ):
        url_match = match.group(1)
        # group(2) 是标题（可能包含 HTML 标签），用正则去除标签
        title = re.sub(r"<[^>]+>", "", match.group(2)).strip()
        # group(3) 是摘要（可能包含 HTML 标签），同样去除
        snippet = re.sub(r"<[^>]+>", "", match.group(3)).strip()
        # 只添加有标题的结果（过滤无效条目）
        if title:
            results.append({"title": title, "url": url_match, "snippet": snippet})
        # 达到限制数量后提前终止
        if len(results) >= limit:
            break

    # 无结果情况
    if not results:
        return {"text": f"no results found for: {query}", "results": []}

    # 格式化为 markdown 链接格式
    # 每条结果为 "[标题](URL)\n摘要"
    text = "\n\n".join(
        f"[{r['title']}]({r['url']})\n{r['snippet']}" for r in results
    )
    return {"text": text, "results": results}


def _resolve(template: str, session: SessionData) -> str:
    """
    解析搜索查询模板中的占位符变量。

    支持的占位符：
        - {{query}}: 当前用户查询文本
        - {{key}}: session.data_map 中的字段值

    Args:
        template (str): 包含占位符的模板字符串
        session (SessionData): 当前会话数据对象

    Returns:
        str: 替换了所有占位符的字符串
    """
    result = template.replace("{{query}}", session.current_query)
    # 替换 data_map 中的所有字段占位符
    for key, val in session.data_map.items():
        result = result.replace(f"{{{{{key}}}}}", val)
    return result
