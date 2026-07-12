"""
数据库查询工具模块 (DB Query)

负责在工作流中执行数据库查询（SQL），将查询结果格式化为文本供下游 LLM 节点使用。

支持的功能：
- 从全局配置的数据库连接池中选择目标数据库
- SQL 模板中支持占位符（{{query}}、{{key}}、{{data_map}} 等）
- 参数化查询（防 SQL 注入）
- 结果行数限制（limit）
- 格式化输出：表格形式的文本表示

典型配置字段（config dict）：
    - db (str): 目标数据库名称，对应 db.yaml 中配置的连接池 key
    - query (str): SQL 查询模板，支持 {{xxx}} 占位符
    - params (list[str]): SQL 参数值列表，每个元素也支持占位符
    - limit (int): 返回的最大行数，默认 50，为 0 时表示不限制
"""

from __future__ import annotations

from src.db import get_db_pool
from src.logger import get_logger
from src.session.data import SessionData

_log = get_logger(__name__)


def db_query(config: dict, session: SessionData) -> dict:
    """
    执行数据库查询并返回格式化结果。

    流程：
    1. 从 config 中获取目标数据库名、SQL 模板、参数和限制行数
    2. 解析模板中的占位符（{{query}} 等）为实际值
    3. 通过数据库连接池执行参数化查询（防 SQL 注入）
    4. 根据 limit 截断结果行
    5. 格式化为文本返回

    边界情况处理：
        - db 为空：立即返回错误，不执行查询
        - 数据库连接池不存在：返回友好错误消息（提示检查 db.yaml）
        - 查询执行异常：记录错误日志，返回错误信息（不向上抛出，保证工作流继续执行）
        - limit 为 0 或负数：不做截断，返回全部结果
        - 查询结果为空：返回 "0 rows" 的文本

    Args:
        config (dict): 节点配置字典，包含：
            - db (str): 目标数据库名（必填，对应 db.yaml 中的连接池 key）
            - query (str): SQL 查询模板，支持占位符
            - params (list[str], 可选): SQL 参数值列表
            - limit (int, 可选): 最大返回行数，默认 50
        session (SessionData): 当前会话数据

    Returns:
        dict: 包含以下键的字典：
            - text (str): 格式化后的查询结果文本（表格形式）
            - rows (list[dict]): 原始查询结果行，每行是一个 dict
            - db (str): 使用的数据库名称
            错误时返回：
            - text (str): 空字符串
            - rows (list): 空列表
            - error (str): 错误描述信息
    """
    # 获取目标数据库名称
    db_name = config.get("db", "")
    if not db_name:
        # db 名称为空是配置错误，直接返回错误
        return {"text": "", "rows": [], "error": "no db name specified"}

    # 获取 SQL 模板和参数
    query_template = config.get("query", "")
    params = config.get("params", [])
    result_limit = config.get("limit", 50)

    # 解析模板中的占位符（{{query}}、{{key}}、{{data_map}} 等）
    resolved = _resolve_template(query_template, session)
    # 参数值也支持占位符，逐一解析并转为元组（适配参数化查询）
    resolved_params = tuple(
        _resolve_template(str(p), session) for p in params
    )

    # 尝试从全局配置中获取数据库连接池
    try:
        pool = get_db_pool(db_name)
    except KeyError:
        # 指定的数据库名在 db.yaml 中不存在，返回友好提示
        return {
            "text": "",
            "rows": [],
            "error": f"db pool '{db_name}' not found. check config/db.yaml",
        }

    # 执行参数化查询（使用参数化方式防止 SQL 注入）
    try:
        rows = pool.execute(resolved, resolved_params)
    except Exception as e:
        # 查询执行失败：记录详细错误日志（截断 SQL 到前 200 字符，防止日志过长）
        _log.error(
            "db_query failed",
            extra={"db": db_name, "query": resolved[:200], "error": str(e)},
        )
        return {
            "text": "",
            "rows": [],
            "error": str(e),
        }

    # 应用行数限制（limit > 0 时截断，limit 为 0 或 None 时不限制）
    if result_limit and result_limit > 0:
        rows = rows[:result_limit]

    # 格式化为文本输出
    text = _format_rows(rows, db_name)
    return {"text": text, "rows": rows, "db": db_name}


def _resolve_template(template: str, session: SessionData) -> str:
    """解析 SQL 模板中的占位符（委托公共实现 `_template.resolve_template`）。

    支持 {{query}} / {{field}}（节点输出或 data_map）/ {{chat_id}} / {{_workflow}} /
    {{return_mode}} / {{long_mem_data}} / {{data_map}}。
    """
    from src.engine.tools._template import resolve_template
    return resolve_template(template, session)


def _format_rows(rows: list[dict], db_name: str) -> str:
    """
    将数据库查询结果格式化为可读的文本表格。

    输出格式示例：
        [mydb]
        id, name, email
        ---------------
        1, 张三, zhang@example.com
        2, 李四, li@example.com

    边界情况：
        - rows 为空列表：返回 "[db_name] 0 rows"
        - 字段值超过 80 字符：截断到前 80 字符

    Args:
        rows (list[dict]): 查询结果行列表，每行是一个 dict[str, Any]
        db_name (str): 数据库名称（用于表头标识）

    Returns:
        str: 格式化后的表格字符串
    """
    if not rows:
        return f"[{db_name}] 0 rows"

    # 以第一行的键作为表头
    headers = list(rows[0].keys())
    lines = [f"[{db_name}]"]
    # 表头行：用 ", " 连接各列名
    lines.append(", ".join(headers))
    # 分隔线：与表头行等长
    lines.append("-" * len(lines[1]))
    # 数据行：每个值截断到 80 字符，防止长文本破坏表格格式
    for row in rows:
        vals = [str(v)[:80] for v in row.values()]
        lines.append(", ".join(vals))

    return "\n".join(lines)
