r"""DAG 工作流引擎 — 核心调度器。

本模块实现了基于有向无环图（DAG）的工作流执行引擎。工作流由若干节点（node）组成，
每个节点关联一个工具函数（tool），引擎负责按拓扑顺序遍历节点、处理条件分支、
支持并行执行分支，并收集执行指标。

核心概念：
- **node**：工作流中的一个步骤，对应一个 YAML 节点配置文件
- **tool**：节点绑定的工具函数，如 llm、rag_search、router 等
- **next_type**：节点的后继类型，决定执行流的分发策略（one / if-then / switch）
- **parallel**：当 next_type 为 switch 时，可标记为并行执行各分支

设计决策：
- 使用 deque + BFS 风格遍历，天然支持 DAG 拓扑排序
- 并行分支通过 ThreadPoolExecutor 实现，每个分支独立构建节点列表后合并
- 会话状态（session.nodes）记录所有已执行节点的输出，供下游节点引用
- 延迟导入工具模块（_register_builtins），避免循环依赖和启动时的内存开销
"""

from __future__ import annotations

import json
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.config import AppConfig, get_app_config
from src.engine.tool import ToolRegistry
from src.engine.tools.merge import merge_branches
from src.logger import get_logger
from src.session.data import SessionData

# 获取当前模块的日志记录器，用于记录 DAG 执行过程中的关键事件
_log = get_logger(__name__)


def _resolve_session_query(session) -> str:
    """Extract the current user query text from a session (SessionData or dict).

    Works for both SessionData objects (has .current_query property) and
    dict-based dummy sessions used in parallel branch execution.
    """
    if hasattr(session, "current_query"):
        return getattr(session, "current_query", "")
    if isinstance(session, dict):
        for node in reversed(session.get("nodes", [])):
            if node.get("name") == "input":
                return node.get("data", {}).get("text", "")
    return ""


def _find_input_node(session) -> dict | None:
    """Find the 'input' node entry from a session's nodes list."""
    nodes = session.get("nodes", []) if isinstance(session, dict) else []
    for node in reversed(nodes):
        if node.get("name") == "input":
            return dict(node)
    return None


def _create_node_entry(
    name: str,
    pre: str | None,
    data: dict,
    metrics: dict | None = None,
    timestamp: float | None = None,
    **extra: object,
) -> dict:
    """创建一个标准化的节点执行记录条目。

    节点条目包含节点的基本信息、前置节点、执行数据和指标，
    统一附加到 session.nodes 列表中，形成完整的执行追踪链。

    Args:
        name: 节点名称，对应 YAML 配置中的 name 字段
        pre: 前置节点名称，用于还原 DAG 拓扑结构；None 表示根节点
        data: 节点工具函数的输出数据，至少包含 "text" 字段
        metrics: 执行指标字典，如 {"total_ms": 150.5}
        timestamp: 执行时间戳（Unix 时间），None 则取当前时间
        **extra: 额外元数据，如 _tool（工具名）、_input（节点配置）

    Returns:
        标准化节点条目字典
    """
    if metrics is None:
        metrics = {}
    if timestamp is None:
        timestamp = time.time()
    # 构建基础条目结构
    entry: dict = {
        "name": name,
        "pre": pre,
        "timestamp": timestamp,
        "data": data,
        "metrics": metrics,
    }
    # 合并额外元数据（如 _tool, _input 等）
    entry.update(extra)
    return entry


class DAGEngine:
    """DAG 工作流执行引擎。

    负责加载工作流配置、按拓扑顺序调度节点执行、处理条件分支与并行分支、
    收集执行指标，并在会话中记录完整的执行轨迹。

    生命周期：
    1. 初始化：注册工具函数，绑定应用配置和指标存储
    2. run()：接收用户查询，创建/复用会话，遍历工作流节点
    3. _traverse() / _walk()：BFS 遍历节点图
    4. _finish()：生成输出节点并返回完整会话
    """

    def __init__(
        self,
        tools: ToolRegistry | None = None,
        app_config: AppConfig | None = None,
        metrics_store: object | None = None,
    ):
        """初始化 DAG 引擎。

        Args:
            tools: 工具注册表，None 则自动创建并注册内置工具
            app_config: 应用配置对象，None 则调用 get_app_config()
            metrics_store: 指标存储后端（如 PostgreSQL），None 则不启用指标采集
        """
        if tools is None:
            tools = ToolRegistry()
            _register_builtins(tools)  # 注册 llm、rag_search、router 等内置工具
        self._tools = tools
        self._app_config = app_config or get_app_config()
        self._metrics_store = metrics_store

    def update_app_config(self, cfg: object) -> None:
        """热重载：更新引用的 AppConfig（由 reload 回调触发）。"""
        self._app_config = cfg

    def run(
        self,
        workflow_name: str,
        query: dict,
        session: SessionData | None = None,
    ) -> dict:
        """执行一次完整的工作流运行。

        这是引擎的主入口，负责创建/复用会话、执行节点遍历、
        生成输出、记录指标，并更新会话历史。

        Args:
            workflow_name: 工作流标识名，对应 workflow.yaml 中的 key
            query: 用户查询数据，需包含 "query" 字段
            session: 已有会话对象（多轮对话场景），None 则新建

        Returns:
            完整会话状态字典（session.to_dict()），包含所有节点执行记录

        Raises:
            KeyError: 指定工作流不存在
        """
        # 1. 查找工作流配置
        wf = self._app_config.workflows.get(workflow_name)
        if wf is None:
            raise KeyError(f"workflow '{workflow_name}' not found")

        query_text = query.get("query", "")
        product = wf.get("_product", workflow_name)

        # 2. 创建或复用会话
        if session is None:
            session = SessionData()
            session._workflow = workflow_name
            session.return_mode = wf.get("return_mode", "full")

        # 记录当前轮次 ID，用于后续指标关联
        current_turn_id = session.turn_id

        _log.info(
            "dag start",
            extra={
                "workflow": workflow_name,
                "chat_id": session.chat_id,
                "turn_id": current_turn_id,
            },
        )

        # 3. 创建输入节点：将用户查询录入会话节点列表
        input_entry = _create_node_entry(
            "input", None, {"text": query_text, **query},
            _tool="", _input={"query": query_text},
        )
        session.nodes.append(input_entry)

        nodes = wf.get("nodes", [])
        return_mode = session.return_mode

        # 4. 遍历工作流节点图
        if nodes:
            self._traverse(session, nodes, product)

        # 5. 构建最终输出
        result = self._finish(session, return_mode)

        # 6. 获取最后一个节点的输出文本，作为本轮回答
        output_node = session.nodes[-1]
        answer_text = output_node["data"].get("text", "")

        # 7. 收集执行指标（如启用）—— 显式传入本轮 query/answer，
        #    避免依赖 history（此时尚未 add_turn，会导致 query/reply 记为空或错位）
        self._collect_metrics(
            session, workflow_name, current_turn_id,
            query=query_text, reply=answer_text,
        )

        # 8. 将本轮问答追加到会话历史
        session.add_turn(query_text, answer_text)

        # 9. 按配置对历史进行裁剪或摘要压缩
        sc = self._app_config.session
        if sc:
            session.trim_or_compress(
                max_turns=sc.max_turns,
                max_chars=sc.max_chars,
                keep=sc.keep,
                compress_max_words=sc.compress_max_words,
                summary_base_url=sc.summary.base_url,
                summary_api_key=sc.summary.api_key,
                summary_model=sc.summary.model,
                summary_system_prompt=sc.summary.system_prompt,
            )

        return result

    def _traverse(self, session: dict, nodes: list[dict], product: str) -> None:
        """遍历工作流节点图。

        构建节点名称→定义的映射，确定起始节点后调用 _walk 进行 BFS 遍历。

        Args:
            session: 会话状态字典（session.nodes 等）
            nodes: 工作流节点定义列表
            product: 产品线标识，用于定位节点 YAML 配置
        """
        # 构建 name → node_def 快速查找映射
        node_map = {n["name"]: n for n in nodes}
        # 起始节点默认为节点列表的第一个
        start_nodes = [nodes[0]["name"]]
        self._walk(session, node_map, start_nodes, product)

    def _walk(
        self,
        session: dict,
        node_map: dict[str, dict],
        current_names: list[str],
        product: str = "",
    ) -> None:
        """BFS 广度优先遍历 DAG 节点。

        使用 deque 实现队列式遍历。对每个节点：
        1. 加载其 YAML 配置文件
        2. 查找并调用对应的工具函数
        3. 记录执行结果和指标到 session.nodes
        4. 根据 next_type 决定下一个要执行的节点

        支持的 next_type 类型：
        - "one": 单一后继，直接入队
        - "if-then": 条件分支，根据输出中的 branch 字段选择入队节点
        - "switch": 多分支，若标记 parallel 则并行执行，否则顺序入队

        Args:
            session: 会话状态（支持 __getitem__ / __setitem__ 的类字典对象）
            node_map: 节点名称→节点定义映射
            current_names: 起始节点名称列表
            product: 产品线标识
        """
        queue = deque(current_names)

        while queue:
            # 从队列头部取出待执行节点
            node_name = queue.popleft()
            if not node_name:
                continue

            node_def = node_map.get(node_name)
            if not node_def:
                continue

            # 加载节点的 YAML 配置（如 llm_node.yaml）
            try:
                node_config = self._app_config.node_config(f"{product}:{node_name}")
            except KeyError:
                raise KeyError(
                    f"node config '{node_name}.yaml' not found "
                    f"in config/workflows/{product}/nodes/"
                )

            tool_name = node_config.get("tool", "")
            tool_fn = self._tools.get(tool_name)
            if not tool_fn:
                raise ValueError(
                    f"unknown tool '{tool_name}' for node '{node_name}'"
                )

            result, tool_data, elapsed_ms = self._run_tool(
                tool_name, tool_fn, node_config, session, node_name,
            )
            metrics = {"total_ms": elapsed_ms}

            pre_name = self._find_pre(session, node_name, node_map)
            entry = _create_node_entry(
                node_name, pre_name, result, metrics,
                _tool=tool_name, _input=node_config, _tool_data=[tool_data],
            )
            session["nodes"].append(entry)

            # ---- 决定下一个执行的节点 ----
            nt = node_def.get("next_type", "one")
            nxt = node_def.get("next", "")

            if nt == "one":
                # 单一后继：只有一个下一个节点
                if nxt:
                    queue.append(nxt)
            elif nt == "if-then":
                # 条件分支：根据输出中的 branch 值选择路径
                if isinstance(nxt, list):
                    branch = result.get("branch", "") if isinstance(result, dict) else result
                    if branch in nxt:
                        queue.append(branch)
                    elif "default" in node_config.get("router", {}):
                        # 若指定的分支不在列表中，回退到 router 配置的 default
                        queue.append(node_config["router"]["default"])
            elif nt == "switch":
                # 多分支：可能并行或顺序执行
                if isinstance(nxt, list):
                    if node_def.get("parallel"):
                        # 并行模式：使用线程池同时执行所有分支
                        self._walk_parallel(session, node_map, nxt, node_name, product)
                    else:
                        # 顺序模式：所有分支依次入队
                        for branch in nxt:
                            queue.append(branch)

    def _walk_parallel(
        self,
        session: dict,
        node_map: dict[str, dict],
        branches: list[str],
        switch_node_name: str,
        product: str = "",
    ) -> None:
        """并行执行 switch 节点的所有分支。

        使用 ThreadPoolExecutor 并发执行各分支（最多 4 个线程），
        每个分支独立构建节点列表，完成后由 merge_branches 合并到主会话。

        Args:
            session: 主会话状态
            node_map: 节点名称→节点定义映射
            branches: 要并行执行的分支名称列表
            switch_node_name: switch 节点的名称（用于合并定位）
            product: 产品线标识
        """
        # 记录 switch 节点在 nodes 列表中的索引位置（用于后续合并）
        switch_node_index = len(session["nodes"]) - 1
        branch_sessions: dict[str, list[dict]] = {}

        input_node = _find_input_node(session)

        # 最多 4 个并发线程，避免过度占用资源
        with ThreadPoolExecutor(max_workers=min(len(branches), 4)) as executor:
            futures = {}
            for branch_name in branches:
                future = executor.submit(
                    self._walk_branch, branch_name, node_map, product, input_node
                )
                futures[future] = branch_name

            # 收集所有分支的执行结果
            for future in as_completed(futures):
                branch_name = futures[future]
                branch_nodes = future.result()
                branch_sessions[branch_name] = branch_nodes

        # 将各分支的结果合并到主会话中
        merge_branches(session, switch_node_index, branch_sessions)

    def _walk_branch(
        self,
        start_name: str,
        node_map: dict[str, dict],
        product: str = "",
        input_node: dict | None = None,
    ) -> list[dict]:
        """在独立上下文中执行一个分支的节点序列。

        与主 _walk 方法类似，但使用独立的节点列表（result_nodes），
        不修改主会话的 session.nodes，仅在分支内部追踪执行状态。

        Args:
            start_name: 分支起始节点名称
            node_map: 节点名称→节点定义映射
            product: 产品线标识
            input_node: 父会话的 input 节点（用于分支内工具读取查询文本）

        Returns:
            分支内所有节点的执行记录列表
        """
        result_nodes: list[dict] = []
        if input_node:
            result_nodes.append(input_node)
        queue = deque([start_name])

        while queue:
            node_name = queue.popleft()
            if not node_name:
                continue

            node_def = node_map.get(node_name)
            if not node_def:
                continue

            try:
                node_config = self._app_config.node_config(f"{product}:{node_name}")
            except KeyError:
                raise KeyError(
                    f"node config '{node_name}.yaml' not found "
                    f"in config/workflows/{product}/nodes/"
                )

            tool_name = node_config.get("tool", "")
            tool_fn = self._tools.get(tool_name)
            if not tool_fn:
                raise ValueError(f"unknown tool '{tool_name}' for node '{node_name}'")

            dummy_session = {"nodes": list(result_nodes)}
            result, tool_data, elapsed_ms = self._run_tool(
                tool_name, tool_fn, node_config, dummy_session, node_name,
            )

            metrics = {"total_ms": elapsed_ms}

            entry = _create_node_entry(
                node_name, None, result, metrics,
                _tool=tool_name, _input=node_config, _tool_data=[tool_data],
            )
            result_nodes.append(entry)

            nt = node_def.get("next_type", "one")
            nxt = node_def.get("next", "")

            if nt == "one" and nxt:
                queue.append(nxt)
            elif nt == "if-then" and isinstance(nxt, list):
                # 条件分支：按 router 输出的 branch 选择单一路径（与主 _walk 一致）
                branch = result.get("branch", "") if isinstance(result, dict) else result
                if branch in nxt:
                    queue.append(branch)
                elif "default" in node_config.get("router", {}):
                    queue.append(node_config["router"]["default"])
            elif nt == "switch" and isinstance(nxt, list):
                # 多分支：全部顺序执行
                for b in nxt:
                    queue.append(b)

        return result_nodes

    def _find_pre(
        self,
        session: dict,
        node_name: str,
        node_map: dict[str, dict],
    ) -> str | None:
        """查找指定节点的前置节点名称。

        先在 node_map 中搜索引用 node_name 的节点定义（精确匹配），
        若未找到则回退：取 session.nodes 中最后一个 != node_name 的节点。

        Args:
            session: 会话状态
            node_name: 要查找前置的节点名称
            node_map: 节点名称→节点定义映射

        Returns:
            前置节点名称，未找到则返回 None
        """
        # 策略一：在 DAG 定义中查找直接引用当前节点的前置节点
        for node_def in node_map.values():
            nt = node_def.get("next_type", "one")
            nxt = node_def.get("next", "")
            if nt == "one" and nxt == node_name:
                return node_def["name"]
            if nt in ("if-then", "switch") and isinstance(nxt, list) and node_name in nxt:
                return node_def["name"]

        # 策略二：回退到 session 中最近的非自身节点
        for n in reversed(session["nodes"]):
            if n["name"] != node_name:
                return n["name"]
        return None

    def _finish(self, session: dict, return_mode: str) -> dict:
        """生成输出节点并返回最终会话状态。

        在已有节点列表末尾追加一个 "output" 节点，其内容为最后一个节点的输出文本。
        同时设置会话的 return_mode。

        Args:
            session: 会话状态
            return_mode: 返回模式（"full" 返回完整会话，"text" 仅返回文本等）

        Returns:
            完整会话状态字典
        """
        # 取最后一个节点的输出文本
        last_node = session["nodes"][-1]
        output_data = {"text": last_node["data"].get("text", "")}
        output_entry = _create_node_entry(
            "output", last_node["name"], output_data,
            _tool="", _input={"return_mode": return_mode},
        )
        session["nodes"].append(output_entry)
        session["return_mode"] = return_mode
        return session

    def _run_tool(
        self, tool_name: str, tool_fn, node_config: dict, session, node_name: str,
    ) -> tuple[dict, dict, float]:
        """执行工具函数并捕获执行数据。

        Returns:
            (result, tool_data, elapsed_ms)
        """
        t0 = time.time()
        error_message = None
        try:
            result = tool_fn(node_config, session)
        except Exception as exc:  # noqa: BLE001 - 节点级错误隔离
            error_message = f"{type(exc).__name__}: {exc}"
            _log.error(
                "node tool failed",
                extra={"node": node_name, "tool": tool_name, "error": error_message},
                exc_info=exc,
            )
            result = {
                "text": f"[节点 {node_name} 执行失败]",
                "error": error_message,
                "branch": "",
            }
        elapsed_ms = (time.time() - t0) * 1000
        if isinstance(result, str):
            result = {"text": result, "branch": result}

        effective_input = dict(node_config)
        query_text = _resolve_session_query(session)
        if query_text:
            effective_input["_query"] = query_text

        tool_data = {
            "tool_name": tool_name,
            "input_params": json.dumps(effective_input, ensure_ascii=False, default=str),
            "output_result": json.dumps(result, ensure_ascii=False, default=str),
            "duration_ms": round(elapsed_ms, 2),
            "status": "error" if error_message else "ok",
            "error_message": error_message,
        }
        return result, tool_data, round(elapsed_ms, 2)

    def _collect_metrics(
        self, session: SessionData, workflow_name: str, turn_id: int,
        query: str | None = None, reply: str | None = None,
    ) -> None:
        if not self._metrics_store:
            return

        # 优先使用显式传入的本轮 query/reply；否则回退到 history（向后兼容）
        if query is None or reply is None:
            query = query or ""
            reply = reply or ""
            if session.history:
                last = session.history[-1]
                query = query or last.input
                reply = reply or last.output

        total_ms = sum(
            n.get("metrics", {}).get("total_ms", 0)
            for n in session.nodes
        )

        def _node_error(node: dict) -> str | None:
            for td in node.get("_tool_data", []):
                if td.get("status") == "error":
                    return td.get("error_message") or "error"
            return None

        run_error = next(
            (_node_error(n) for n in session.nodes if _node_error(n)), None
        )

        # 汇总 token 用量（来自 llm 节点的 usage 字段）
        prompt_tokens = 0
        completion_tokens = 0
        for n in session.nodes:
            usage = (n.get("data") or {}).get("usage")
            if isinstance(usage, dict):
                prompt_tokens += int(usage.get("prompt_tokens", 0) or 0)
                completion_tokens += int(usage.get("completion_tokens", 0) or 0)

        # Prometheus 节点/工具级指标
        try:
            from src.metrics.prometheus import record_node_metric, record_workflow_run
            record_workflow_run(workflow_name, "error" if run_error else "ok")
            for n in session.nodes:
                nerr = _node_error(n)
                record_node_metric(
                    n.get("name", ""), n.get("_tool", ""),
                    "error" if nerr else "ok",
                    n.get("metrics", {}).get("total_ms", 0),
                )
        except Exception as e:  # noqa: BLE001 - 指标失败不影响主流程
            _log.warning("prometheus metrics recording failed",
                         extra={"error": f"{type(e).__name__}: {e}"})

        run_id = self._metrics_store.insert_run(
            chat_id=session.chat_id,
            turn_id=turn_id,
            workflow_name=workflow_name,
            query=query,
            reply=reply,
            node_count=len(session.nodes),
            duration_ms=round(total_ms, 2),
            status="error" if run_error else "ok",
            error_message=run_error,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

        for node in session.nodes:
            node_name = node.get("name", "")
            tool_name = node.get("_tool", "")
            inp = node.get("_input")
            _query = _resolve_session_query(session)
            rich_input: dict[str, object] = {}
            if inp is not None:
                rich_input["config"] = inp
            if _query:
                rich_input["query"] = _query
            input_data = (
                json.dumps(rich_input, ensure_ascii=False, default=str)
                if rich_input else None
            )
            node_data = node.get("data")
            if node_data:
                output_text = json.dumps(node_data, ensure_ascii=False, default=str)
            else:
                output_text = ""
            _log.info(
                "metrics node",
                extra={
                    "node": node_name,
                    "tool": tool_name,
                    "data_keys": list(node_data.keys()) if node_data else [],
                    "output_len": len(output_text),
                },
            )
            dur = node.get("metrics", {}).get("total_ms", 0)

            node_err = _node_error(node)
            node_log_id = self._metrics_store.insert_node_log(
                run_id=run_id,
                chat_id=session.chat_id,
                turn_id=turn_id,
                node_name=node_name,
                tool_name=tool_name,
                input_data=input_data,
                output_text=output_text,
                duration_ms=dur,
                status="error" if node_err else "ok",
                error_message=node_err,
            )

            for td in node.get("_tool_data", []):
                self._metrics_store.insert_tool_log(
                    node_log_id=node_log_id,
                    run_id=run_id,
                    chat_id=session.chat_id,
                    turn_id=turn_id,
                    node_name=node_name,
                    tool_name=td["tool_name"],
                    input_params=td["input_params"],
                    output_result=td["output_result"],
                    duration_ms=td["duration_ms"],
                    status=td.get("status", "ok"),
                    error_message=td.get("error_message"),
                )

            # RAG 检索详情入库（仅 rag_search 节点）
            if tool_name == "rag_search":
                try:
                    result_data = node.get("data") or {}
                    results = result_data.get("results", [])
                    collections = result_data.get("_collections") or [""]
                    collections = collections if isinstance(collections, list) else [str(collections)]
                    default_col = collections[0] if collections else ""
                    for rr in results:
                        if not isinstance(rr, dict):
                            continue
                        payload = rr.get("payload") or {}
                        self._metrics_store.insert_rag_retrieval(
                            run_id=run_id, chat_id=session.chat_id,
                            turn_id=turn_id, collection=default_col,
                            score=float(rr.get("score", 0) or 0),
                            source=str(payload.get("source", "") or ""),
                            chunk_preview=(str(payload.get("text", "") or ""))[:500],
                        )
                except Exception:
                    pass  # RAG 详情入库失败不影响主流程


def _register_builtins(registry: ToolRegistry) -> None:
    """向工具注册表中注册所有内置工具函数。

    使用延迟导入（函数内 import）以避免启动时加载所有工具模块，
    降低模块初始化开销和循环依赖风险。

    Args:
        registry: 工具注册表实例
    """
    # 延迟导入各工具模块，避免启动时的循环依赖和内存开销
    from src.engine.tools import (  # noqa: PLC0415
        api_call,
        code,
        db_query,
        extract_llm,
        extract_regex,
        llm_tool,
        rag_search,
        router,
        web_search,
    )

    registry.register("llm", llm_tool)
    registry.register("rag_search", rag_search)
    registry.register("router", router)
    registry.register("db_query", db_query)
    registry.register("extract_llm", extract_llm)
    registry.register("extract_regex", extract_regex)
    registry.register("api_call", api_call)
    registry.register("web_search", web_search)
    registry.register("code", code)
