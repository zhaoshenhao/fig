"""
安全代码执行工具模块 (Code Exec)

负责在工作流中安全地执行用户配置的代码片段（Python），
返回执行结果供下游节点使用。

安全机制：
1. 受限的 __builtins__：仅暴露白名单中的内置函数
   （reversed、abs、len、sorted、sum、dict、list 等安全函数）
2. 受控的 import：通过 _safe_import 限制可导入的模块白名单
   （json、math、datetime、collections、itertools、re、statistics 等纯计算模块）
3. 禁用的内置函数：open、eval、exec、compile、__import__ 等危险函数不在白名单中
4. 执行超时控制（虽依赖 Python 本身，无强制中断但可配置）
5. stdout 捕获：通过 redirect_stdout 将所有 print 输出重定向到缓冲区

典型配置结构（config dict）：
    {
        "code": "print(sum(data))",
        "language": "python",
        "timeout": 10
    }

代码模板支持占位符：
    - {{query}}: 当前用户查询
    - {{key}}: session.data_map 中的字段值
    - {{chat_id}}: 会话 ID
    - {{_workflow}}: 工作流名称
    - {{long_mem_data}}: 长期记忆数据
"""

from __future__ import annotations

import json

from src.logger import get_logger
from src.session.data import SessionData

_log = get_logger(__name__)


def code(config: dict, session: SessionData) -> dict:
    """
    安全执行一段代码（当前仅支持 Python）。

    流程：
    1. 从 config 获取代码文本、语言和超时配置
    2. 解析代码模板中的占位符
    3. 根据语言选择执行引擎
    4. 在受限环境中执行代码并返回结果

    边界情况处理：
        - code 为空：直接返回错误
        - 语言不是 "python"：返回 "unsupported language" 错误

    Args:
        config (dict): 节点配置字典，包含：
            - code (str): 要执行的 Python 代码文本，支持占位符
            - language (str, 可选): 编程语言，默认 "python"
            - timeout (int, 可选): 超时时间（秒），默认 10
        session (SessionData): 当前会话数据对象

    Returns:
        dict: 包含以下键的字典：
            - text (str): 执行结果文本（stdout 输出或错误信息）
            - stdout (str): 标准输出内容
            - error (str | None): 错误信息，无错误时为 None
    """
    code_text = config.get("code", "")
    language = config.get("language", "python").lower()
    timeout = config.get("timeout", 10)

    if not code_text:
        return {"text": "", "error": "no code specified"}

    # 解析代码模板中的占位符
    code_text = _resolve(code_text, session)

    if language == "python":
        return _run_python(code_text, timeout)
    return {"text": "", "error": f"unsupported language: {language}"}


def _run_python(code_text: str, timeout: int) -> dict:
    """
    在受限的 Python 执行环境中运行代码。

    安全策略：
    1. 使用受限的 __builtins__ 字典，仅包含白名单内置函数
    2. 将所有 print 输出重定向到 StringIO 缓冲区
    3. 捕获所有异常并以友好格式返回

    白名单中包含的内置函数（只有安全无副作用的函数）：
        - 数据类型：bool, dict, float, int, list, set, str, tuple
        - 迭代/函数式：enumerate, filter, map, range, reversed, sorted, zip
        - 聚合计算：all, any, len, max, min, round, sum
        - 数学：abs
        - 输出：print（重定向到缓冲区）
        - 数据处理：json（通过受限 import 导入）
        - 安全的 __import__：由 _safe_import 函数控制，仅允许白名单中的模块

    Args:
        code_text (str): 已解析占位符的 Python 代码
        timeout (int): 超时时间（秒），当前版本为预留参数，不强制中断

    Returns:
        dict: 包含以下键的字典：
            - text (str): 执行结果（stdout 内容或错误消息）
            - stdout (str): 捕获的标准输出
            - error (str | None): 错误信息
    """
    # 定义受限的全局命名空间
    # __builtins__ 被替换为白名单字典，禁止访问 open、eval、exec 等危险函数
    restricted_globals = {
        "__builtins__": {
            "abs": abs, "all": all, "any": any, "bool": bool,
            "dict": dict, "enumerate": enumerate, "filter": filter,
            "float": float, "int": int, "len": len, "list": list,
            "map": map, "max": max, "min": min, "range": range,
            "reversed": reversed, "round": round, "set": set,
            "sorted": sorted, "str": str, "sum": sum, "tuple": tuple,
            "zip": zip, "print": print,
            "json": json,
            # 替换默认 __import__ 为安全的导入函数
            "__import__": _safe_import,
        },
    }
    # 受限的局部命名空间（代码可通过赋值添加新变量）
    restricted_locals: dict = {}

    # 用于捕获标准输出的缓冲区和上下文管理器
    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    error = None
    try:
        # 在受限环境中执行代码，stdout 被重定向到 buf
        with redirect_stdout(buf):
            exec(code_text, restricted_globals, restricted_locals)  # noqa: S102
    except Exception as e:
        # 捕获所有异常（语法错误、运行时错误、ImportError 等）
        error = f"{type(e).__name__}: {e}"
        _log.error("code execution failed", extra={"error": error})

    # 获取 stdout 缓冲区内容
    output = buf.getvalue().strip()
    if error:
        # 有错误时：text 和 error 都返回错误信息，stdout 返回已产生的输出
        return {"text": error, "error": error, "stdout": output}
    # 无错误：text 返回 stdout 内容；如果没有输出，返回成功消息
    return {"text": output or "code executed successfully", "stdout": output, "error": None}


def _safe_import(name, *args, **kwargs):
    """
    安全的模块导入函数，替代内建 __import__。

    仅允许导入白名单中的模块，防止代码通过 import 执行危险操作。
    白名单仅包含纯计算/数据处理模块，排除 os、subprocess、socket、sys 等系统模块。

    允许导入的模块（安全模块白名单）：
        json, math, datetime, collections, itertools, functools,
        re, statistics, decimal, fractions, hashlib, base64,
        uuid, random, string, textwrap

    Args:
        name (str): 模块名称
        *args: 传递给 __import__ 的额外位置参数
        **kwargs: 传递给 __import__ 的关键字参数

    Returns:
        module: 导入的模块对象

    Raises:
        ImportError: 如果模块不在白名单中
    """
    allowed = {
        "json", "math", "datetime", "collections", "itertools",
        "functools", "re", "statistics", "decimal", "fractions",
        "hashlib", "base64", "uuid", "random", "string", "textwrap",
    }
    # 检查模块的顶层名称（对于 "os.path" 只检查 "os"）
    if name.split(".")[0] not in allowed:
        raise ImportError(f"import of '{name}' is not allowed")
    return __import__(name, *args, **kwargs)


def _resolve(template: str, session: SessionData) -> str:
    """
    解析代码模板中的占位符变量。

    支持的占位符：
        - {{query}}: 当前用户查询文本
        - {{key}}: session.data_map 中的字段值
        - {{chat_id}}: 会话 ID
        - {{_workflow}}: 当前工作流名称
        - {{long_mem_data}}: 长期记忆数据

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
    # 替换会话级别的元数据占位符
    for key in ("chat_id", "_workflow", "long_mem_data"):
        val = session.get(key, "")
        if isinstance(val, str):
            result = result.replace(f"{{{{{key}}}}}", val)
    return result
