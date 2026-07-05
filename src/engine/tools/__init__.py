"""
工具包 (Engine Tools)

该包汇集了工作流引擎中所有可用的工具函数，每个工具对应工作流 DAG 中的一个节点类型。

工具清单：
    - rag_search (RAG 向量检索): 在 Qdrant 中执行混合搜索，返回相关文档片段
    - router (条件路由): 根据上游节点输出决定下游分支走向
    - db_query (数据库查询): 执行参数化 SQL，返回格式化表格
    - extract_regex (正则提取): 用正则表达式从用户输入提取结构化信息
    - extract_llm (LLM 信息提取): 用 LLM 从用户输入提取结构化信息
    - api_call (外部 API 调用): 发起 HTTP 请求调用外部 REST API
    - web_search (网页搜索): 通过搜索引擎获取互联网信息
    - code (安全代码执行): 在受限沙箱中执行用户配置的 Python 代码
    - llm_tool (LLM 调用): 调用大语言模型进行对话生成
    - merge_branches (并行分支合并): 合并并行分支节点到主执行序列

注：llm_tool、extract_llm、web_search 通过延迟导入包装函数暴露，
    避免在工作流加载时即产生不必要的外部依赖导入。
"""

# 直接导入（无循环依赖风险的工具）
from .api_call import api_call
from .code_exec import code
from .db_query import db_query
from .extract_regex import extract_regex
from .rag_search import rag_search
from .router import router

# __all__ 定义了该包的公开 API，供外部通过 `from engine.tools import *` 使用
__all__ = [
    "rag_search", "router", "db_query",
    "extract_regex",
    "api_call", "web_search", "code",
    "llm_tool", "extract_llm",
]


def llm_tool(config: dict, session) -> dict:
    """
    LLM 调用工具的延迟导入包装器。

    使用延迟导入的原因：llm_tool 模块的顶层导入可能引入 LLMClient、
    全局配置等，在工作流初始化阶段尚未就绪。延迟导入确保只有在实际
    执行时才加载这些依赖。

    Args:
        config (dict): 节点配置字典
        session: 当前会话数据对象

    Returns:
        dict: LLM 调用的返回结果（参见 llm_tool.llm_tool 的文档）
    """
    from .llm_tool import llm_tool as _fn
    return _fn(config, session)


def extract_llm(config: dict, session) -> dict:
    """
    LLM 信息提取工具的延迟导入包装器。

    延迟导入原因同 llm_tool。

    Args:
        config (dict): 节点配置字典
        session: 当前会话数据对象

    Returns:
        dict: 提取结果的字典（参见 extract_llm.extract_llm 的文档）
    """
    from .extract_llm import extract_llm as _fn
    return _fn(config, session)


def web_search(config: dict, session) -> dict:
    """
    网页搜索工具的延迟导入包装器。

    延迟导入原因：web_search 模块依赖 httpx2 和外部搜索服务，
    在工作流初始化阶段无需加载。

    Args:
        config (dict): 节点配置字典
        session: 当前会话数据对象

    Returns:
        dict: 搜索结果字典（参见 web_search.web_search 的文档）
    """
    from .web_search import web_search as _fn
    return _fn(config, session)
