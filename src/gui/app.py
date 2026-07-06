import json
import os
import sys
from datetime import datetime

import httpx2
import streamlit as st
import streamlit.components.v1 as components

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.gui.utils import _highlight_term

try:
    from src.config import load_app_config
    from src.rag.qdrant import QdrantSearch
    HAS_SRC = True
except ImportError:
    HAS_SRC = False

st.set_page_config(page_title="KF - 智能客服", layout="wide")

if HAS_SRC:
    from src.logger import init_logging
    init_logging(app_name="gui")


def _inject_css():
    st.markdown("""
    <style>
    [data-testid="stAppViewContainer"] > .main h1:first-of-type {
        font-size: 0.63rem !important;
        padding: 0.1rem 1rem !important;
        position: sticky; top: 0; z-index: 100;
        margin-bottom: 0 !important;
        background: inherit;
    }
    [data-testid="stTabs"] > div:first-child {
        position: sticky; top: 28px; z-index: 100;
        padding-top: 2px !important; padding-bottom: 2px !important;
        background: inherit;
    }
    button[data-testid="stBaseButton-headerNoPadding"] {
        font-size: 0.78rem !important;
        padding: 0.15rem 0.5rem !important;
        min-height: 28px !important;
    }
    h2 { font-size: 0.95rem !important; }
    h3 { font-size: 0.85rem !important; }

    .chat-controls-row [data-testid="stVerticalBlock"] {
        align-items: flex-end !important;
    }

    .dag-flow {
        display: flex; flex-direction: column;
        gap: 0; padding: 4px 0;
    }
    .dag-row {
        display: flex; align-items: center; gap: 6px;
        padding: 2px 0; flex-wrap: wrap;
    }
    .dag-card {
        display: inline-flex; flex-direction: column;
        border-radius: 6px;
        padding: 4px 10px;
        min-width: 90px;
        text-align: center;
        font-family: monospace;
    }
    .dag-card .node-name {
        font-size: 0.82rem; font-weight: 600;
    }
    .dag-card .node-tool {
        font-size: 0.65rem; opacity: 0.7;
    }
    .dag-card .node-dur {
        font-size: 0.6rem; opacity: 0.6;
    }
    .dag-card.executed {
        border: 1.5px solid #4caf50; background: #e8f5e9;
    }
    .dag-card.failed {
        border: 1.5px solid #f44336; background: #ffebee;
    }
    .dag-card.skipped {
        border: 1.5px solid #bdbdbd; background: #f5f5f5; opacity: 0.6;
    }
    .dag-card.no-status {
        border: 1.5px solid #90caf9; background: #e3f2fd;
    }
    .dag-arrow {
        font-size: 1.1rem; color: #999;
        flex-shrink: 0;
    }
    .dag-branch-label {
        font-size: 0.65rem; color: #888;
        margin-right: 4px;
    }
    .dag-branch {
        margin-left: 18px; border-left: 2px dashed #ccc;
        padding-left: 10px;
    }
    .dag-parallel {
        display: flex; gap: 12px; flex-wrap: wrap;
        margin-left: 18px; border-left: 2px solid #90caf9;
        padding-left: 10px;
    }

    @media (max-width: 768px) {
        [data-testid="stSidebar"] { display: none !important; }
        [data-testid="stTabs"] > div:first-child { flex-wrap: wrap !important; }
        button[data-testid="stBaseButton-headerNoPadding"] {
            font-size: 0.7rem !important; padding: 0.1rem 0.3rem !important;
            min-height: 24px !important;
        }
        h1 { font-size: 0.95rem !important; }
    }

    @media (min-width: 769px) and (max-width: 1024px) {
        [data-testid="stSidebar"] { width: 200px !important; }
    }
    </style>
    """, unsafe_allow_html=True)


_inject_css()

st.title("智能客服 - Knowledge Forge")

API_BASE = os.environ.get("KF_API_URL")
if not API_BASE and HAS_SRC:
    API_BASE = load_app_config().gui.api_url
if not API_BASE:
    API_BASE = "http://localhost:9000"

with st.sidebar:
    st.markdown("### API 连接")

    if "api_key" not in st.session_state:
        st.session_state.api_key = os.environ.get("KF_API_KEY", "")

    col_key, col_stat = st.columns([3, 1])
    with col_key:
        api_key = st.text_input(
            "API Key", value=st.session_state.api_key, type="password",
            key="sidebar_api_key_input", label_visibility="collapsed",
            placeholder="输入 API Key...",
        )
    st.session_state.api_key = api_key

    with col_stat:
        if "sidebar_status" in st.session_state:
            st.markdown(st.session_state.sidebar_status, unsafe_allow_html=True)
        else:
            st.markdown("")

    _headers = {"X-API-Key": api_key} if api_key else {}
    try:
        resp = httpx2.get(f"{API_BASE}/health", headers=_headers, timeout=5)
        if resp.status_code == 200:
            st.session_state.sidebar_status = (
                '<span style="color:green;font-size:0.85rem">● 已连接</span>'
            )
        else:
            st.session_state.sidebar_status = (
                f'<span style="color:orange;font-size:0.85rem">● {resp.status_code}</span>'
            )
    except Exception:
        st.session_state.sidebar_status = (
            '<span style="color:red;font-size:0.85rem">● 已断开</span>'
        )
    st.markdown(st.session_state.sidebar_status, unsafe_allow_html=True)

    st.divider()
    with st.expander("会话信息", expanded=False):
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


def _dag_card_html(
    node_name: str,
    status: str = "no-status",
    tool: str = "",
    duration_ms: float = 0,
) -> str:
    """Render a single DAG node as a Dify-style card HTML snippet."""
    dur_text = f"<div class='node-dur'>{duration_ms:.0f}ms</div>" if duration_ms else ""
    tool_text = f"<div class='node-tool'>{tool}</div>" if tool else ""
    return (
        f"<div class='dag-card {status}'>"
        f"<div class='node-name'>{node_name}</div>"
        f"{tool_text}{dur_text}"
        f"</div>"
    )


def _render_dag_flow(nodes: list[dict], node_data: dict | None = None):
    """Render a DAG workflow as a Dify-style card flow (HTML).

    Args:
        nodes: workflow node definitions (name, next_type, next)
        node_data: optional dict {node_name: {status, tool, duration_ms}}
                   If provided, cards are colored by execution status.
    """
    if not nodes:
        st.caption("_无节点_")
        return

    if node_data is None:
        node_data = {}

    def _card(name):
        nd = node_data.get(name, {})
        status = nd.get("status", "no-status") if nd else "no-status"
        tool = nd.get("tool", "") if nd else ""
        dur = nd.get("duration_ms", 0) if nd else 0
        return _dag_card_html(name, status=status, tool=tool, duration_ms=dur)

    adj: dict[str, list[str]] = {}
    levels: dict[str, int] = {}
    for n in nodes:
        adj[n["name"]] = []
        nt = n.get("next_type", "one")
        nxt = n.get("next", "")
        if nt == "one" and nxt:
            adj[n["name"]].append(nxt)
        elif nt in ("if-then", "switch") and isinstance(nxt, list):
            for b in nxt:
                adj[n["name"]].append(b)

    has_parent = {t for v in adj.values() for t in v}
    roots = [n["name"] for n in nodes if n["name"] not in has_parent]
    if not roots:
        roots = [nodes[0]["name"]]

    from collections import deque
    q = deque((r, 0) for r in roots)
    while q:
        name, lv = q.popleft()
        if name in levels:
            continue
        levels[name] = lv
        for nb in adj.get(name, []):
            if nb not in levels:
                q.append((nb, lv + 1))
    for n in nodes:
        if n["name"] not in levels:
            levels[n["name"]] = max(levels.values(), default=0) + 1

    max_lv = max(levels.values()) if levels else 0
    groups: list[list[str]] = [[] for _ in range(max_lv + 1)]
    for node_name, lv in levels.items():
        groups[lv].append(node_name)

    node_map = {n["name"]: n for n in nodes}

    html_parts = ['<div class="dag-flow">']

    for lv, group in enumerate(groups):
        if not group:
            continue
        row_parts = []
        for node_name in group:
            row_parts.append(_card(node_name))
            children = adj.get(node_name, [])
            nt = node_map.get(node_name, {}).get("next_type", "one")
            if children:
                if nt == "switch" and node_map.get(node_name, {}).get("parallel"):
                    row_parts.append("<div class='dag-parallel'>")
                    for ch in children:
                        row_parts.append(
                            f"<div class='dag-row'>"
                            f"{_card(ch)}"
                            f"</div>"
                        )
                        for gc in adj.get(ch, []):
                            row_parts.append(
                                f"<div class='dag-row'>"
                                f"<span class='dag-arrow'> →</span>"
                                f"{_card(gc)}"
                                f"</div>"
                            )
                    row_parts.append("</div>")
                elif nt == "if-then":
                    row_parts.append("<div class='dag-branch'>")
                    row_parts.append(
                        '<div class="dag-row">'
                        '<span class="dag-branch-label">branches:</span>'
                        '</div>'
                    )
                    for ch in children:
                        row_parts.append(
                            f"<div class='dag-row'>"
                            f"{_card(ch)}"
                            f"</div>"
                        )
                        for gc in adj.get(ch, []):
                            row_parts.append(
                                f"<div class='dag-row'>"
                                f"<span class='dag-arrow'> →</span>"
                                f"{_card(gc)}"
                                f"</div>"
                            )
                    row_parts.append("</div>")
                else:
                    for ch in children:
                        row_parts.append("<span class='dag-arrow'>→</span>")
                        row_parts.append(_card(ch))

        html_parts.append(f'<div class="dag-row">{"".join(row_parts)}</div>')

    html_parts.append("</div>")
    st.markdown("\n".join(html_parts), unsafe_allow_html=True)


def _render_dag_nodes(nodes: list[dict], product_name: str):
    """Render DAG as Dify-style card flow with clickable node configs below."""
    if not nodes:
        st.caption("_无节点_")
        return

    _render_dag_flow(nodes)

    st.markdown("**节点配置：**")
    app_cfg = load_app_config()
    cols = st.columns(min(len(nodes), 6))
    for i, n in enumerate(nodes):
        node_name = n["name"]
        nt = n.get("next_type", "one")
        badge = " ⇢" if nt == "if-then" else (" ⇉" if nt == "switch" else "")
        with cols[i % len(cols)]:
            with st.popover(f"{node_name}{badge}", use_container_width=True):
                st.caption(f"**路由：** `{nt}`")
                if n.get("next"):
                    st.caption(f"**后继：** `{n['next']}`")
                if nt == "switch" and n.get("parallel"):
                    st.caption("**并行：** 是")
                node_key = f"{product_name}:{node_name}"
                cfg_data = app_cfg.nodes.get(node_key)
                if cfg_data:
                    st.markdown("**YAML 配置：**")
                    st.json(cfg_data)
                else:
                    st.caption("（无独立节点配置文件）")

with tabs[0]:
    chat_header = st.container()
    with chat_header:
        st.markdown("### 多轮对话")

    if not HAS_SRC:
        st.warning("无法加载 src 模块，请确认虚拟环境配置正确。")
    else:
        app_cfg = load_app_config()
        wf_names = list(app_cfg.workflows.keys())

        if not wf_names:
            st.info("暂无已注册的工作流。")
        else:
            with chat_header:
                st.markdown('<div class="chat-controls-row">', unsafe_allow_html=True)
                col_a, col_b, col_c = st.columns([2, 1, 1])
                with col_a:
                    wf_choice = st.selectbox(
                        "选择工作流", wf_names, key="chat_wf",
                        label_visibility="collapsed",
                    )
                with col_b:
                    if "use_stream" not in st.session_state:
                        st.session_state.use_stream = False
                    st.session_state.use_stream = st.checkbox(
                        "流式输出", key="stream_toggle",
                    )
                with col_c:
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
                st.markdown('</div>', unsafe_allow_html=True)

            if "chat_messages" not in st.session_state:
                st.session_state.chat_messages = []
                st.session_state.chat_turn = 0

            chat_messages_box = st.container(height=500)
            with chat_messages_box:
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
                    use_stream = st.session_state.get("use_stream", False)

                    try:
                        if use_stream:
                            resp = httpx2.post(
                                f"{API_BASE}/workflows/{wf_choice}/run?stream=true",
                                json=payload, headers=_headers, timeout=120,
                            )
                            reply = ""
                            cid = ""
                            tid = 0
                            for line in resp.iter_lines():
                                if line.startswith("data: "):
                                    evt = json.loads(line[6:])
                                    if evt.get("event") == "done":
                                        reply = evt.get("reply", "")
                                        cid = evt.get("chat_id", "")
                                        tid = evt.get("turn_id", 0)
                                    elif evt.get("event") == "error":
                                        reply = f"**错误**\n\n{evt['data']}"
                                        break
                            st.session_state.chat_id = cid
                            st.session_state.chat_turn = tid
                        else:
                            resp = httpx2.post(
                                f"{API_BASE}/workflows/{wf_choice}/run",
                                json=payload, headers=_headers, timeout=60,
                            )
                            if resp.status_code == 200:
                                data = resp.json()
                                reply = data.get("reply", "")
                                st.session_state.chat_id = data.get("chat_id", "")
                                st.session_state.chat_turn = data.get("turn_id", 0)
                            else:
                                reply = f"**错误 {resp.status_code}**\n\n{resp.text}"

                        st.session_state.chat_messages.append(
                            {"role": "assistant", "content": reply, "timestamp": reply_ts}
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

            msgs = st.session_state.get("chat_messages", [])
            if msgs:
                with st.expander("导出对话", expanded=False):
                    exp_c1, exp_c2 = st.columns(2)
                    with exp_c1:
                        json_str = json.dumps(msgs, ensure_ascii=False, indent=2)
                        st.download_button(
                            "下载 JSON", json_str, "chat_history.json",
                            "application/json", key="export_json",
                        )
                    with exp_c2:
                        import csv
                        import io as _io
                        buf = _io.StringIO()
                        w = csv.writer(buf)
                        w.writerow(["role", "content", "timestamp"])
                        for m in msgs:
                            w.writerow([m["role"], m["content"], m.get("timestamp", "")])
                        st.download_button(
                            "下载 CSV", buf.getvalue(), "chat_history.csv",
                            "text/csv", key="export_csv",
                        )

            if st.session_state.get("chat_id"):
                st.caption(
                    f"chat_id: `{st.session_state['chat_id']}` | "
                    f"turn: {st.session_state.get('chat_turn', 0)}"
                )

# ── Tab 1: Knowledge Browser ──────────────────────────────────
with tabs[1]:
    col_h1, col_r1 = st.columns([5, 1])
    with col_h1:
        st.markdown("### 知识库浏览")
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
                            payload = r.get("payload", {})
                            score = r.get("score", 0)
                            with st.expander(f"ID: {r['id']}  |  分数: {score:.4f}"):
                                text_val = payload.get("text", "")
                                if text_val and search_query.strip():
                                    st.markdown(
                                        _highlight_term(str(text_val), search_query),
                                        unsafe_allow_html=True,
                                    )
                                st.json(payload)
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
        st.markdown("### 工作流状态")
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
                    nodes = wf.get("nodes", [])
                    if nodes:
                        st.markdown("**节点 DAG：**")
                        _render_dag_nodes(nodes, wf.get("_product", name))
                    else:
                        st.markdown("_无节点_")

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
        st.markdown("### 文档管理")
    with col_r3:
        if st.button("刷新", key="doc_refresh"):
            st.rerun()

    if not HAS_SRC:
        st.warning("无法加载 src 模块，请确认虚拟环境配置正确。")
    else:
        st.subheader("上传文档")
        uploaded_file = st.file_uploader(
            "选择文件（.txt / .md / .pdf / .docx / .csv / .xlsx）",
            type=["txt", "md", "pdf", "docx", "csv", "xlsx"],
            key="doc_upload",
        )
        col1, col2 = st.columns(2)
        with col1:
            upload_collection = st.text_input(
                "目标集合", value="default", key="upload_collection"
            )
        with col2:
            upload_chunk_size = st.number_input(
                "分块大小（字符）", value=800, min_value=64, max_value=4096,
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
        st.markdown("### 运行指标")
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

    if HAS_SRC:
        app_cfg = load_app_config()
    else:
        app_cfg = None

    st.subheader("会话列表")
    if sessions:
        import csv as _csv
        import io as _io_buf
        csv_buf = _io_buf.StringIO()
        w = _csv.writer(csv_buf)
        w.writerow(["chat_id", "turns", "total_duration_ms", "first_at", "last_at"])
        for s in sessions:
            w.writerow([
                s["chat_id"], s["turn_count"], s.get("total_duration_ms", ""),
                s.get("first_at", ""), s.get("last_at", ""),
            ])
        st.download_button(
            "下载会话 CSV", csv_buf.getvalue(), "sessions.csv",
            "text/csv", key="metrics_csv_export",
        )

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

                    node_by_name = {n["node_name"]: n for n in nodes}
                    wf_def = app_cfg.workflows.get(wf, {}) if app_cfg else {}
                    wf_nodes = wf_def.get("nodes", [])

                    if wf_nodes:
                        st.markdown("**DAG 执行状态：**")
                        nd_map: dict[str, dict[str, object]] = {}
                        for n in wf_nodes:
                            nd = node_by_name.get(n["name"])
                            if nd:
                                nd_map[n["name"]] = {
                                    "status": (
                                        "failed" if nd.get("status", "ok") != "ok"
                                        else "executed"
                                    ),
                                    "tool": str(nd.get("tool_name") or ""),
                                    "duration_ms": float(nd.get("duration_ms") or 0),
                                }
                            else:
                                nd_map[n["name"]] = {"status": "skipped"}
                        _render_dag_flow(wf_nodes, nd_map)

                        st.markdown("**节点详情：**")
                        nc2 = st.columns(min(len(wf_nodes), 6))
                        for i, n in enumerate(wf_nodes):
                            node_name = n["name"]
                            nd = node_by_name.get(node_name)
                            with nc2[i % len(nc2)]:
                                if nd:
                                    icon = (
                                        "✅" if nd.get("status", "ok") == "ok"
                                        else "❌"
                                    )
                                    dur = nd.get("duration_ms") or 0
                                    tool = nd.get("tool_name") or "—"
                                    label = f"{icon} {node_name} ({dur:.0f}ms)"
                                    with st.popover(label, use_container_width=True):
                                        inp = nd.get("input_data") or ""
                                        out = nd.get("output_text") or ""
                                        if inp:
                                            st.markdown("**输入：**")
                                            _pretty_display(inp)
                                        if out:
                                            st.markdown("**输出：**")
                                            _pretty_display(out)
                                        err = nd.get("error_message")
                                        if err:
                                            st.error(err)
                                        nid = nd["node_log_id"]
                                        try:
                                            tools = ms.query_node_tools(nid)
                                        except Exception:
                                            tools = []
                                        if tools:
                                            st.markdown("---")
                                            for tlog in tools:
                                                tdur = tlog.get("duration_ms") or 0
                                                ts_icon = (
                                                    "✅"
                                                    if tlog.get("status", "ok") == "ok"
                                                    else "❌"
                                                )
                                                tname = tlog["tool_name"]
                                                st.markdown(
                                                    f"🔧 **`{tname}`** {ts_icon} ({tdur:.0f}ms)"
                                                )
                                                params = tlog.get("input_params") or ""
                                                result = tlog.get("output_result") or ""
                                                if params:
                                                    st.caption("参数：")
                                                    _pretty_display(params)
                                                if result:
                                                    st.caption("结果：")
                                                    _pretty_display(result)
                                else:
                                    st.markdown(
                                        f"<span style='color:#9e9e9e'>⚪ {node_name}</span>",
                                        unsafe_allow_html=True,
                                    )

                    else:
                        for node in nodes:
                            node_name = node["node_name"]
                            tool = node.get("tool_name") or "—"
                            ndur = node.get("duration_ms") or 0
                            status = node.get("status", "ok")
                            inp = node.get("input_data") or ""
                            out = node.get("output_text") or ""
                            status_icon = "✅" if status == "ok" else "❌"
                            exp_label = (
                                f"{status_icon} {node_name} (`{tool}`) — {ndur:.0f}ms"
                            )
                            with st.expander(exp_label):
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
                                        tdur = tlog.get("duration_ms") or 0
                                        ts_icon = (
                                            "✅" if tlog.get("status", "ok") == "ok"
                                            else "❌"
                                        )
                                        tname = tlog["tool_name"]
                                        st.markdown(
                                            f"🔧 **`{tname}`** {ts_icon} ({tdur:.0f}ms)"
                                        )
                                        params = tlog.get("input_params") or ""
                                        result = tlog.get("output_result") or ""
                                        if params:
                                            st.caption("参数:")
                                            _pretty_display(params)
                                        if result:
                                            st.caption("结果:")
                                            _pretty_display(result)
