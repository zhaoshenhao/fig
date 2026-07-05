import json
import os
import sys
from datetime import datetime

import httpx2
import streamlit as st
import streamlit.components.v1 as components

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

try:
    from src.config import load_app_config
    from src.rag.qdrant import QdrantSearch
    HAS_SRC = True
except ImportError:
    HAS_SRC = False

st.set_page_config(page_title="KF - 智能客服", layout="wide")
st.title("智能客服 - Knowledge Forge")

API_BASE = os.environ.get("KF_API_URL")
if not API_BASE and HAS_SRC:
    API_BASE = load_app_config().gui.api_url
if not API_BASE:
    API_BASE = "http://localhost:9000"

with st.sidebar:
    st.subheader("API 连接")

    if "api_key" not in st.session_state:
        st.session_state.api_key = os.environ.get("KF_API_KEY", "")

    api_key = st.text_input(
        "API Key", value=st.session_state.api_key, type="password",
        key="sidebar_api_key_input",
    )
    st.session_state.api_key = api_key

    if api_key:
        auth_headers = {"X-API-Key": api_key}
        try:
            resp = httpx2.get(
                f"{API_BASE}/health", headers=auth_headers, timeout=5,
            )
            if resp.status_code == 200:
                st.success("已认证 - 已连接")
            else:
                st.warning(f"已认证 - API 返回 {resp.status_code}")
        except Exception:
            st.error("已认证 - 已断开")
    else:
        try:
            resp = httpx2.get(f"{API_BASE}/health", timeout=5)
            if resp.status_code == 200:
                st.info("未认证 - 已连接")
            else:
                st.warning(f"未认证 - API 返回 {resp.status_code}")
        except Exception:
            st.error("未认证 - 已断开")

    st.divider()
    st.subheader("会话信息")

    chat_id = st.session_state.get("chat_id", "")
    chat_turn = st.session_state.get("chat_turn", 0)
    if chat_id:
        st.caption(f"Chat ID: `{chat_id[:16]}...`")
        st.caption(f"Turn: {chat_turn}")
    else:
        st.caption("暂无活跃会话")

tabs = st.tabs(["聊天", "知识库浏览", "工作流状态", "文档管理", "运行指标"])


def _pretty_display(text: str, max_len: int = 5000):
    """Display text as formatted JSON if parseable, otherwise as plain text."""
    if not text or not text.strip():
        return
    try:
        data = json.loads(text)
        if isinstance(data, (dict, list)):
            st.json(data)
            return
    except (json.JSONDecodeError, ValueError, TypeError):
        pass
    st.text(text[:max_len])


# ── Tab 0: Chat ──────────────────────────────────────────────
with tabs[0]:
    st.header("多轮对话")

    if not HAS_SRC:
        st.warning("无法加载 src 模块，请确认虚拟环境配置正确。")
    else:
        app_cfg = load_app_config()
        wf_names = list(app_cfg.workflows.keys())

        if not wf_names:
            st.info("暂无已注册的工作流。")
        else:
            col_a, col_b = st.columns([2, 1])
            with col_a:
                wf_choice = st.selectbox("选择工作流", wf_names, key="chat_wf")
            with col_b:
                if st.button("清空会话", key="chat_clear"):
                    cid = st.session_state.get("chat_id", "")
                    if cid:
                        try:
                            _h = {"X-API-Key": api_key} if api_key else {}
                            httpx2.delete(f"{API_BASE}/sessions/{cid}", headers=_h)
                        except Exception:
                            pass
                    st.session_state.pop("chat_id", None)
                    st.session_state.pop("chat_messages", None)
                    st.session_state.pop("chat_turn", None)
                    st.rerun()

            if "chat_messages" not in st.session_state:
                st.session_state.chat_messages = []
                st.session_state.chat_turn = 0

            for msg in st.session_state.chat_messages:
                ts = msg.get("timestamp", "")
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])
                    if ts:
                        st.caption(ts)

            if st.session_state.pop("_focus_input", False):
                components.html("""
                <script>
                setTimeout(function() {
                    var el = parent.document.querySelector(
                        '[data-testid="stChatInput"] textarea, [data-testid="stChatInput"] input'
                    );
                    if (el) { el.focus(); }
                }, 100);
                </script>
                """, height=0)

            pending = st.session_state.pop("_pending_query", None)
            if pending:
                with st.spinner("思考中..."):
                    payload = {"query": pending}
                    chat_id_val = st.session_state.get("chat_id", "")
                    if chat_id_val:
                        payload["chat_id"] = chat_id_val

                    _headers = {"X-API-Key": api_key} if api_key else {}
                    reply_ts = datetime.now().strftime("%H:%M:%S")

                    try:
                        resp = httpx2.post(
                            f"{API_BASE}/workflows/{wf_choice}/run",
                            json=payload,
                            headers=_headers,
                            timeout=60,
                        )
                        if resp.status_code == 200:
                            data = resp.json()
                            reply = data.get("reply", "")
                            st.session_state.chat_id = data.get("chat_id", "")
                            st.session_state.chat_turn = data.get("turn_id", 0)
                            st.session_state.chat_messages.append(
                                {"role": "assistant", "content": reply, "timestamp": reply_ts}
                            )
                        else:
                            st.session_state.chat_messages.append(
                                {"role": "assistant",
                                 "content": f"**错误 {resp.status_code}**\n\n{resp.text}",
                                 "timestamp": reply_ts}
                            )
                    except Exception as e:
                        st.session_state.chat_messages.append(
                            {"role": "assistant",
                             "content": f"**连接失败**\n\n{str(e)}",
                             "timestamp": reply_ts}
                            )

                st.session_state._focus_input = True
                st.rerun()

            user_input = st.chat_input("输入消息...", key="chat_input")
            if user_input:
                now_ts = datetime.now().strftime("%H:%M:%S")
                st.session_state.chat_messages.append(
                    {"role": "user", "content": user_input, "timestamp": now_ts}
                )
                st.session_state._pending_query = user_input
                st.rerun()

            if st.session_state.get("chat_id"):
                st.caption(
                    f"chat_id: `{st.session_state['chat_id']}` | "
                    f"turn: {st.session_state.get('chat_turn', 0)}"
                )

# ── Tab 1: Knowledge Browser ──────────────────────────────────
with tabs[1]:
    col_h1, col_r1 = st.columns([5, 1])
    with col_h1:
        st.header("知识库浏览")
    with col_r1:
        if st.button("刷新", key="kb_refresh"):
            st.rerun()

    @st.cache_resource
    def get_qdrant():
        host = os.environ.get("QDRANT_HOST", "localhost")
        port = int(os.environ.get("QDRANT_PORT", "6334"))
        try:
            return QdrantSearch(host=host, port=port)
        except Exception:
            return None

    qdrant = get_qdrant()

    if qdrant is None:
        st.warning("无法连接 Qdrant (localhost:6334)。请启动 Qdrant 服务。")
    else:
        try:
            collections = sorted(
                c.name for c in qdrant._client.get_collections().collections
            )
        except Exception:
            collections = []

        if not collections:
            st.info("暂无集合。请先构建知识库（文档管理 Tab）。")
        else:
            col1, col2, col3 = st.columns([2, 1, 1])
            with col1:
                selected = st.selectbox("选择集合", collections, key="kb_collection")
            with col2:
                per_page = st.selectbox(
                    "每页条数", [10, 20, 50, 100], index=1, key="kb_per_page"
                )
            with col3:
                sort_order = st.selectbox(
                    "排序", ["ID 正序", "ID 倒序"], key="kb_sort"
                )

            search_query = st.text_input("搜索", placeholder="输入关键词过滤...", key="kb_search")

            if "kb_page" not in st.session_state:
                st.session_state.kb_page = 1

            try:
                total = qdrant._client.count(selected).count
            except Exception:
                total = 0

            max_page = max(1, (total + per_page - 1) // per_page)

            if search_query:
                try:
                    provider = None
                    if HAS_SRC:
                        app_cfg = load_app_config()
                        provider = app_cfg.embed_provider()
                    if provider:
                        from src.llm.client import LLMClient
                        client = LLMClient(
                            base_url=provider.base_url, api_key=provider.api_key
                        )
                        vectors = client.embed(provider.model, search_query)
                        vector = vectors[0]
                        results = qdrant.search(
                            collection=selected,
                            vector=vector,
                            query_text=search_query,
                            limit=per_page,
                            offset=(st.session_state.kb_page - 1) * per_page,
                        )
                        st.caption(f"搜索 '{search_query}' 找到 {len(results)} 条结果")
                        for r in results:
                            with st.expander(f"ID: {r['id']}  |  分数: {r.get('score', 0):.4f}"):
                                st.json(r.get("payload", {}))
                except Exception as e:
                    st.error(f"搜索失败: {e}")
            else:
                offset_val = (st.session_state.kb_page - 1) * per_page

                c1, c2, c3 = st.columns([1, 2, 1])
                with c1:
                    if st.button("上一页") and st.session_state.kb_page > 1:
                        st.session_state.kb_page -= 1
                        st.rerun()
                with c2:
                    st.markdown(
                        f"**第 {st.session_state.kb_page} / {max_page} 页**"
                        f"（共 {total} 条）"
                    )
                with c3:
                    if st.button("下一页") and st.session_state.kb_page < max_page:
                        st.session_state.kb_page += 1
                        st.rerun()

                try:
                    records, _next = qdrant.scroll(
                        collection=selected,
                        limit=per_page,
                        offset=offset_val,
                    )
                    for r in records:
                        with st.expander(f"ID: {r['id']}"):
                            st.json(r.get("payload", {}))
                except Exception as e:
                    st.error(f"加载失败: {e}")

# ── Tab 2: Workflow Status ────────────────────────────────────
with tabs[2]:
    col_h2, col_r2 = st.columns([5, 1])
    with col_h2:
        st.header("工作流状态")
    with col_r2:
        if st.button("刷新", key="wf_refresh"):
            st.rerun()

    if not HAS_SRC:
        st.error("无法加载 src 模块，请确认虚拟环境配置正确。")
    else:
        try:
            app_cfg = load_app_config()

            st.subheader("已注册工作流")
            for name, wf in app_cfg.workflows.items():
                with st.expander(f"{name} — {wf.get('description', '')}"):
                    st.markdown(f"**Collections:** `{wf.get('collections', ['default'])}`")
                    st.markdown(f"**Return Mode:** `{wf.get('return_mode', 'full')}`")
                    st.markdown("**节点链：**")
                    nodes = wf.get("nodes", [])
                    for i, n in enumerate(nodes):
                        nxt = n.get("next", "")
                        nxt_type = n.get("next_type", "one")
                        badge = ""
                        if nxt_type == "if-then":
                            badge = " [if-then]"
                        elif nxt_type == "switch":
                            parallel = "[parallel]" if n.get("parallel") else "[serial]"
                            badge = f" [switch {parallel}]"
                        arrow = f" → `{nxt}`" if nxt else ""
                        st.markdown(f"  {i+1}. `{n['name']}`{badge}{arrow}")

            st.divider()
            st.subheader("LLM 供应商")
            if app_cfg.llm:
                st.write(f"默认: `{app_cfg.llm.default}`")
                for pname, p in app_cfg.llm.providers.items():
                    st.caption(f"  {pname}: {p.type} / {p.model} @ {p.base_url}")

            st.subheader("Embedding 供应商")
            if app_cfg.embed:
                st.write(f"默认: `{app_cfg.embed.default}`")
                for pname, p in app_cfg.embed.providers.items():
                    st.caption(f"  {pname}: {p.type} / {p.model} ({p.dims}d) @ {p.base_url}")

        except Exception as e:
            st.error(f"加载配置失败: {e}")

# ── Tab 3: Document Management ────────────────────────────────
with tabs[3]:
    col_h3, col_r3 = st.columns([5, 1])
    with col_h3:
        st.header("文档管理")
    with col_r3:
        if st.button("刷新", key="doc_refresh"):
            st.rerun()

    if not HAS_SRC:
        st.warning("无法加载 src 模块，请确认虚拟环境配置正确。")
    else:
        st.subheader("上传文档")
        uploaded_file = st.file_uploader(
            "选择文件（.txt / .md）",
            type=["txt", "md"],
            key="doc_upload",
        )
        col1, col2 = st.columns(2)
        with col1:
            upload_collection = st.text_input(
                "目标集合", value="default", key="upload_collection"
            )
        with col2:
            upload_chunk_size = st.number_input(
                "分块大小（词）", value=512, min_value=64, max_value=4096,
                key="upload_chunk_size",
            )

        if uploaded_file and st.button("上传并构建"):
            with st.spinner("正在处理..."):
                import tempfile
                from pathlib import Path

                tmp = Path(tempfile.gettempdir()) / uploaded_file.name
                tmp.write_bytes(uploaded_file.getvalue())

                try:
                    import os

                    from src.config import load_app_config
                    from src.ingestion.builder import build_document
                    from src.llm.client import LLMClient
                    from src.rag.qdrant import QdrantSearch

                    app_cfg = load_app_config()
                    embed_provider = app_cfg.embed_provider()
                    embed_model = embed_provider.model
                    qdrant_host = os.environ.get("QDRANT_HOST", "localhost")
                    qdrant_port = int(os.environ.get("QDRANT_PORT", "6334"))

                    qdrant = QdrantSearch(host=qdrant_host, port=qdrant_port)
                    embed_client = LLMClient(
                        base_url=embed_provider.base_url,
                        api_key=embed_provider.api_key,
                    )
                    count = build_document(
                        tmp, upload_collection, qdrant, embed_client,
                        embed_model, chunk_size=int(upload_chunk_size),
                    )
                    st.success(f"构建完成！{count} 个分块已入库 `{upload_collection}`")
                except Exception as e:
                    st.error(f"构建失败: {e}")

        st.divider()
        st.subheader("扫描目录")
        col_a, col_b = st.columns(2)
        with col_a:
            scan_dir = st.text_input(
                "目录路径", value="data/documents", key="scan_dir"
            )
        with col_b:
            scan_collection = st.text_input(
                "目标集合", value="default", key="scan_collection"
            )

        if st.button("扫描并构建"):
            with st.spinner(f"正在扫描 `{scan_dir}`..."):
                try:
                    import os

                    from src.config import load_app_config
                    from src.ingestion.builder import build_directory
                    from src.llm.client import LLMClient
                    from src.rag.qdrant import QdrantSearch

                    app_cfg = load_app_config()
                    embed_provider = app_cfg.embed_provider()
                    embed_model = embed_provider.model
                    qdrant_host = os.environ.get("QDRANT_HOST", "localhost")
                    qdrant_port = int(os.environ.get("QDRANT_PORT", "6334"))

                    qdrant = QdrantSearch(host=qdrant_host, port=qdrant_port)
                    embed_client = LLMClient(
                        base_url=embed_provider.base_url,
                        api_key=embed_provider.api_key,
                    )
                    count = build_directory(
                        scan_dir, scan_collection, qdrant, embed_client,
                        embed_model,
                    )
                    st.success(f"扫描完成！{count} 个分块已入库 `{scan_collection}`")
                except Exception as e:
                    st.error(f"扫描失败: {e}")

# ── Tab 4: Metrics / Session Explorer ──────────────────────────
with tabs[4]:
    col_h4, col_r4 = st.columns([3, 1])
    with col_h4:
        st.header("运行指标")
    with col_r4:
        interval_options = [1, 5, 10, 15]
        interval_labels = ["1 分钟", "5 分钟", "10 分钟", "15 分钟"]
        if "metrics_interval_min" not in st.session_state:
            st.session_state.metrics_interval_min = 5

        sub_dd, sub_btn = st.columns([3, 2])
        with sub_dd:
            selected_interval = st.selectbox(
                "自动刷新间隔",
                options=interval_options,
                index=interval_options.index(st.session_state.metrics_interval_min),
                format_func=lambda x: interval_labels[interval_options.index(x)],
                key="metrics_interval_select",
                label_visibility="collapsed",
            )
        with sub_btn:
            if st.button("立即刷新", key="metrics_manual_refresh"):
                st.rerun()

        st.session_state.metrics_interval_min = selected_interval

    metrics_interval_ms = st.session_state.metrics_interval_min * 60 * 1000
    components.html(f"""
    <script>
    (function() {{
        var intervalMs = {metrics_interval_ms};
        sessionStorage.setItem('_kf_last_render', String(Date.now()));
        setTimeout(function() {{
            var now = Date.now();
            var last = parseInt(sessionStorage.getItem('_kf_last_render') || String(now));
            if (now - last >= intervalMs - 1000) {{
                window.location.reload();
            }}
        }}, intervalMs);
    }})();
    </script>
    """, height=0)

    st.caption(f"每 {st.session_state.metrics_interval_min} 分钟自动刷新（无操作时）")

    try:
        from src.metrics.store import MetricsStore
    except ImportError:
        st.warning("无法加载 MetricsStore 模块。")
        st.stop()

    ms = MetricsStore()
    st.caption(f"数据库: `{ms.db_path}`")

    try:
        sessions = ms.query_sessions(limit=50)
    except Exception as e:
        st.error(f"查询失败: {e}")
        sessions = []

    if not sessions:
        st.info("暂无运行记录。发一条消息后刷新页面。")
        st.stop()

    st.subheader("会话列表")
    for sess in sessions:
        cid = sess["chat_id"]
        turns = sess["turn_count"]
        total_ms = sess["total_duration_ms"] or 0
        first_at = sess["first_at"] or ""
        last_at = sess["last_at"] or ""

        with st.expander(
            f"`{cid[:16]}...` | {turns} 轮 | {total_ms:.0f}ms | {first_at}"
        ):
            try:
                turn_list = ms.query_session_turns(cid)
            except Exception:
                turn_list = []

            for turn in turn_list:
                turn_id = turn["turn_id"]
                wf = turn["workflow_name"]
                dur = turn["duration_ms"] or 0
                nc = turn["node_count"]
                query = (turn.get("query") or "")[:80]
                reply = (turn.get("reply") or "")[:80]

                with st.expander(
                    f"Turn {turn_id} | {wf} | {nc} 节点 | {dur:.0f}ms"
                ):
                    st.caption(f"Query: {query}")
                    st.caption(f"Reply: {reply}")

                    try:
                        nodes = ms.query_turn_nodes(turn["run_id"])
                    except Exception:
                        nodes = []

                    for node in nodes:
                        node_name = node["node_name"]
                        tool = node.get("tool_name") or "—"
                        ndur = node.get("duration_ms") or 0
                        status = node.get("status", "ok")
                        inp = node.get("input_data") or ""
                        out = node.get("output_text") or ""

                        status_icon = "✅" if status == "ok" else "❌"
                        with st.expander(
                            f"{status_icon} {node_name} (`{tool}`) — {ndur:.0f}ms"
                        ):
                            if inp:
                                st.markdown("**输入:**")
                                _pretty_display(inp)
                            if out:
                                st.markdown("**输出:**")
                                _pretty_display(out)

                            err = node.get("error_message")
                            if err:
                                st.error(err)

                            nid = node["node_log_id"]
                            try:
                                tools = ms.query_node_tools(nid)
                            except Exception:
                                tools = []

                            if tools:
                                st.markdown("---")
                                for tlog in tools:
                                    t_name = tlog["tool_name"]
                                    tdur = tlog.get("duration_ms") or 0
                                    t_status = tlog.get("status", "ok")
                                    params = tlog.get("input_params") or ""
                                    result = tlog.get("output_result") or ""

                                    t_icon = "✅" if t_status == "ok" else "❌"
                                    st.markdown(
                                        f"🔧 **`{t_name}`** {t_icon} ({tdur:.0f}ms)"
                                    )
                                    if params:
                                        st.caption("参数:")
                                        _pretty_display(params)
                                    if result:
                                        st.caption("结果:")
                                        _pretty_display(result)
                                    t_err = tlog.get("error_message")
                                    if t_err:
                                        st.caption(f"❌ {t_err}")
