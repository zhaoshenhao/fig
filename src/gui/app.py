import csv as _csv
import io as _io
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import httpx2
import streamlit as st
import streamlit.components.v1 as components

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.gui.utils import _highlight_term  # noqa: E402

try:
    from src.config import load_app_config  # noqa: E402
    from src.rag.qdrant import QdrantSearch  # noqa: E402
    HAS_SRC = True
except ImportError:
    HAS_SRC = False

st.set_page_config(page_title="KF - 智能客服", layout="wide")

_DAGRE_JS: str | None = None


def _get_dagre_js() -> str:
    global _DAGRE_JS
    if _DAGRE_JS is None:
        p = Path(__file__).resolve().parent / "static" / "dagre.min.js"
        _DAGRE_JS = p.read_text(encoding="utf-8")
    return _DAGRE_JS


def _inject_css():
    st.markdown("""<style>
    header[data-testid="stHeader"] { display: none !important; }
    [data-testid="stDeployButton"] { display: none !important; }
    [data-testid="baseButton-header"] { display: none !important; }
    [data-testid="stStatusWidget"] { display: none !important; }
    #MainMenu { display: none !important; }
    [data-testid="stAppViewContainer"] > .main h1:first-of-type {
        font-size: 0.38rem !important;
        padding: 0.1rem 1rem !important; margin: 0 !important;
        position: sticky; top: 0; z-index: 100; background: inherit;
    }
    h2 { font-size: 0.95rem !important; }
    h3 { font-size: 0.85rem !important; }
    .chat-controls-row [data-testid="stVerticalBlock"] {
        align-items: flex-end !important;
    }
    .dag-container { position: relative; overflow: auto; }
    .dag-node {
        position: absolute; border-radius: 10px;
        padding: 4px 12px; border: 2px solid #90caf9;
        background: #e3f2fd; text-align: center;
        cursor: pointer; white-space: nowrap;
        font-size: 0.8rem; font-weight: 600;
        box-shadow: 0 1px 3px rgba(0,0,0,.12);
        transform: translate(-50%,-50%);
    }
    .dag-node.n-ok { border-color:#4caf50; background:#e8f5e9; color:#2e7d32; }
    .dag-node.n-fail { border-color:#f44336; background:#ffebee; color:#c62828; }
    .dag-node.n-skip { border-color:#ccc; background:#f5f5f5; color:#888; }
    .dag-node.n-info { border-color:#64b5f6; background:#e3f2fd; color:#1565c0; }
    .dag-node:hover { box-shadow: 0 3px 8px rgba(0,0,0,.25); z-index: 10; }
    .dag-modal {
        display: none; position: fixed; top: 10vh; left: 10vw;
        width: 80vw; max-width: 540px; z-index: 10000;
        background: #fff; border: 2px solid #555; border-radius: 10px;
        padding: 18px; box-shadow: 0 8px 30px rgba(0,0,0,.3);
        font: 13px monospace; color: #333; max-height: 80vh; overflow: auto;
    }
    .dag-modal-header {
        display: flex; justify-content: space-between;
        align-items: center; margin-bottom: 12px;
    }
    .dag-modal-close {
        border: none; background: #eee; border-radius: 4px;
        padding: 4px 10px; cursor: pointer;
    }
    @media (max-width: 768px) {
        [data-testid="stSidebar"] { display: none !important; }
        h1 { font-size: 0.35rem !important; }
    }
    @media (min-width:769px) and (max-width:1024px) {
        [data-testid="stSidebar"] { width: 200px !important; }
    }
    </style>""", unsafe_allow_html=True)


_inject_css()

if HAS_SRC:
    from src.logger import init_logging  # noqa: E402
    init_logging(app_name="gui")

st.title("智能客服 - Knowledge Forge")

API_BASE = os.environ.get("KF_API_URL")
if not API_BASE and HAS_SRC:
    API_BASE = load_app_config().gui.api_url
if not API_BASE:
    API_BASE = "http://localhost:9000"

# ---------------------------------------------------------------------------
# sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### 导航")
    if "nav" not in st.session_state:
        st.session_state.nav = "聊天"
    nav_items = ["聊天", "知识库浏览", "工作流状态", "文档管理", "运行指标"]
    nav = st.radio(
        "导航", nav_items,
        index=nav_items.index(st.session_state.nav),
        label_visibility="collapsed",
    )
    st.session_state.nav = nav
    st.divider()
    with st.expander("会话信息", expanded=False):
        cid = st.session_state.get("chat_id", "")
        if cid:
            st.caption(f"`{cid[:16]}...`")
            st.caption(f"Turn: {st.session_state.get('chat_turn', 0)}")
        else:
            st.caption("暂无")
    st.divider()
    st.markdown("**API 连接**")
    if "api_key" not in st.session_state:
        st.session_state.api_key = os.environ.get("KF_API_KEY", "")
    api_key = st.text_input(
        "Key", value=st.session_state.api_key, type="password",
        key="sidebar_api_key_input", label_visibility="collapsed",
        placeholder="API Key...",
    )
    st.session_state.api_key = api_key
    _h = {"X-API-Key": api_key} if api_key else {}
    try:
        r = httpx2.get(f"{API_BASE}/health", headers=_h, timeout=3)
        if r.status_code == 200:
            st.caption("● 已连接")
        else:
            st.caption(f"● {r.status_code}")
    except Exception:
        st.caption("● 已断开")
    st.divider()
    st.markdown("**显示偏好**")
    if "stream_default" not in st.session_state:
        st.session_state.stream_default = False
    need = st.checkbox("默认流式输出", key="pref_stream")
    st.session_state.stream_default = need
    st.caption(f"API: `{API_BASE}`")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _pretty_display(text: str, max_len: int = 5000):
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


def _render_dag_svg(nodes, node_data=None, height=320):
    if not nodes:
        st.caption("_无节点_")
        return
    if node_data is None:
        node_data = {}
    import json as _json
    elements = []
    info = {}
    for n in nodes:
        name = n["name"]
        nd = node_data.get(name, {})
        sts = nd.get("status", "no-status") if nd else "no-status"
        tool = nd.get("tool", "") if nd else ""
        dur = nd.get("duration_ms", 0) if nd else 0
        label = name[:22] + "…" if len(name) > 22 else name
        elements.append({"data": {
            "id": name, "label": label, "status": sts,
            "fullName": name, "tool": tool,
            "dur": f"{dur:.0f}ms" if dur else "",
        }})
        info[name] = {"name": name, "tool": tool, "dur": dur, "status": sts}
        nt = n.get("next_type", "one")
        nxt = n.get("next", "")
        if nt == "one" and nxt:
            elements.append({"data": {"source": name, "target": nxt}})
        elif nt in ("if-then", "switch") and isinstance(nxt, list):
            for b in nxt:
                elements.append({"data": {"source": name, "target": b}})
    rid = f"dg_{abs(hash(_json.dumps(list(info.keys()), sort_keys=True))) % 1000000}"
    data_js = _json.dumps(elements, ensure_ascii=False)
    info_js = _json.dumps(info, ensure_ascii=False)

    close_js = "this.parentElement.parentElement.style.display='none'"
    components.html(
        '<div id="' + rid + '" class="dag-container" style="height:'
        + str(height) + 'px"></div>'
        '<div id="' + rid + '_modal" class="dag-modal">'
        '<div class="dag-modal-header">'
        '<b id="' + rid + '_mti"></b>'
        '<button class="dag-modal-close" onclick="' + close_js + '">✕</button>'
        '</div><pre id="' + rid
        + '_mbo" style="white-space:pre-wrap;margin:0"></pre></div>'
        '<script>' + _get_dagre_js() + '</script>'
        '<script>(function(){'
        'var d=' + data_js + ';var inf=' + info_js + ';'
        'var g=new dagre.graphlib.Graph();'
        'g.setGraph({rankdir:"LR",nodesep:50,ranksep:80,edgesep:20,marginx:30,marginy:30});'
        'g.setDefaultEdgeLabel(function(){return{};});'
        'd.forEach(function(el){'
        'if(el.data.id){g.setNode(el.data.id,{width:130,height:40});}'
        'else{g.setEdge(el.data.source,el.data.target);}});'
        'dagre.layout(g);'
        'var W=g.graph().width+60,H=g.graph().height+60;'
        'var ct=document.getElementById("' + rid + '");'
        'ct.style.height=Math.max(' + str(height) + ',H+10)+"px";'
        'ct.style.position="relative";'
        'var sNs="http://www.w3.org/2000/svg";'
        'var svg=document.createElementNS(sNs,"svg");'
        'svg.setAttribute("width",W);svg.setAttribute("height",H);'
        'svg.style.position="absolute";svg.style.top="0";svg.style.left="0";'
        'svg.style.pointerEvents="none";ct.appendChild(svg);'
        'g.edges().forEach(function(e){'
        'var pts=g.edge(e).points;'
        'var p2=document.createElementNS(sNs,"path");'
        'p2.setAttribute("d","M"+pts.map(function(p){return p.x+" "+p.y;}).join("L"));'
        'p2.setAttribute("stroke","#bbb");p2.setAttribute("stroke-width","2");'
        'p2.setAttribute("fill","none");p2.setAttribute("stroke-linecap","round");'
        'svg.appendChild(p2);});'
        'g.nodes().forEach(function(id){'
        'var nd=g.node(id);'
        'var el=d.find(function(x){return x.data&&x.data.id===id;});'
        'if(!el)return;var dd=el.data;'
        'var cls="n-"+dd.status.replace("executed","ok")'
        '.replace("failed","fail")'
        '.replace("skipped","skip")'
        '.replace("no-status","info");'
        'var div=document.createElement("div");'
        'div.className="dag-node "+cls;'
        'div.style.left=nd.x+"px";div.style.top=nd.y+"px";'
        'div.textContent=dd.label;'
        'div.title=(inf[id]?inf[id].name:dd.id);'
        'div.onclick=function(){'
        'var i=inf[id]||{};'
        'document.getElementById("' + rid + '_mti").textContent="◉ "+(i.name||id);'
        'var b=["Name: "+(i.name||id)];'
        'if(i.tool)b.push("Tool: "+i.tool);'
        'if(i.dur)b.push("Duration: "+i.dur+"ms");'
        'b.push("Status: "+(dd.status||"-"));'
        'document.getElementById("' + rid + '_mbo").textContent=b.join("\\n");'
        'document.getElementById("' + rid + '_modal").style.display="block";};'
        'ct.appendChild(div);});'
        '})();</script>',
        height=height + 60,
    )


# ---------------------------------------------------------------------------
# ── Chat ──
# ---------------------------------------------------------------------------
def _page_chat():
    st.markdown("### 多轮对话")
    if not HAS_SRC:
        st.warning("无法加载 src 模块")
        return
    app_cfg = load_app_config()
    wf_names = list(app_cfg.workflows.keys())
    if not wf_names:
        st.info("暂无已注册的工作流。")
        return
    ch = st.container()
    with ch:
        st.markdown(
            '<div class="chat-controls-row">', unsafe_allow_html=True,
        )
        ca, cb, cc = st.columns([2, 1, 1])
        with ca:
            wf_choice = st.selectbox(
                "选择工作流", wf_names, key="chat_wf",
                label_visibility="collapsed",
            )
        with cb:
            if "use_stream" not in st.session_state:
                st.session_state.use_stream = False
            st.session_state.use_stream = st.checkbox(
                "流式", key="stream_toggle",
            )
        with cc:
            if st.button("清空", key="chat_clear"):
                cid2 = st.session_state.get("chat_id", "")
                if cid2:
                    hh = {"X-API-Key": api_key} if api_key else {}
                    try:
                        httpx2.delete(
                            f"{API_BASE}/sessions/{cid2}", headers=hh,
                        )
                    except Exception:
                        pass
                for k in ("chat_id", "chat_messages", "chat_turn"):
                    st.session_state.pop(k, None)
                st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []
        st.session_state.chat_turn = 0
    mb = st.container(height=500)
    with mb:
        for msg in st.session_state.chat_messages:
            ts_val = msg.get("timestamp", "")
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                if ts_val:
                    st.caption(ts_val)
    if st.session_state.pop("_focus_input", False):
        components.html("""<script>
setTimeout(function(){var el=parent.document.querySelector(
'[data-testid="stChatInput"] textarea,[data-testid="stChatInput"] input');
if(el)el.focus();},100);</script>""", height=0)
    pending = st.session_state.pop("_pending_query", None)
    if pending:
        with st.spinner("思考中..."):
            payload = {"query": pending}
            cid3 = st.session_state.get("chat_id", "")
            if cid3:
                payload["chat_id"] = cid3
            hh2 = {"X-API-Key": api_key} if api_key else {}
            ts2 = datetime.now().strftime("%H:%M:%S")
            use_s = st.session_state.get("use_stream", False)
            reply2 = ""
            try:
                if use_s:
                    r = httpx2.post(
                        f"{API_BASE}/workflows/{wf_choice}/run?stream=true",
                        json=payload, headers=hh2, timeout=120,
                    )
                    cid4, tid4 = "", 0
                    for line in r.iter_lines():
                        if line.startswith("data: "):
                            evt = json.loads(line[6:])
                            if evt.get("event") == "done":
                                reply2 = evt.get("reply", "")
                                cid4 = evt.get("chat_id", "")
                                tid4 = evt.get("turn_id", 0)
                            elif evt.get("event") == "error":
                                reply2 = f"错误: {evt['data']}"
                                break
                    st.session_state.chat_id = cid4
                    st.session_state.chat_turn = tid4
                else:
                    r = httpx2.post(
                        f"{API_BASE}/workflows/{wf_choice}/run",
                        json=payload, headers=hh2, timeout=60,
                    )
                    if r.status_code == 200:
                        d = r.json()
                        reply2 = d.get("reply", "")
                        st.session_state.chat_id = d.get("chat_id", "")
                        st.session_state.chat_turn = d.get("turn_id", 0)
                    else:
                        reply2 = f"错误 {r.status_code}\n\n{r.text}"
            except Exception as e:
                reply2 = f"连接失败\n\n{str(e)}"
            st.session_state.chat_messages.append({
                "role": "assistant", "content": reply2, "timestamp": ts2,
            })
        st.session_state._focus_input = True
        st.rerun()
    ui = st.chat_input("输入消息...", key="chat_input")
    if ui:
        ts3 = datetime.now().strftime("%H:%M:%S")
        st.session_state.chat_messages.append({
            "role": "user", "content": ui, "timestamp": ts3,
        })
        st.session_state._pending_query = ui
        st.rerun()
    msgs = st.session_state.get("chat_messages", [])
    if msgs:
        with st.expander("导出对话", expanded=False):
            e1, e2 = st.columns(2)
            with e1:
                st.download_button(
                    "JSON",
                    json.dumps(msgs, ensure_ascii=False, indent=2),
                    "chat_history.json", "application/json", key="exp_j",
                )
            with e2:
                buf = _io.StringIO()
                w = _csv.writer(buf)
                w.writerow(["role", "content", "timestamp"])
                for m in msgs:
                    w.writerow([
                        m["role"], m["content"],
                        m.get("timestamp", ""),
                    ])
                st.download_button(
                    "CSV", buf.getvalue(), "chat_history.csv",
                    "text/csv", key="exp_c",
                )


# ---------------------------------------------------------------------------
# ── KB Browser ──
# ---------------------------------------------------------------------------
def _page_knowledge_browser():
    st.markdown("### 知识库浏览")

    @st.cache_resource
    def _get_qdrant():
        h = os.environ.get("QDRANT_HOST", "localhost")
        p = int(os.environ.get("QDRANT_PORT", "6334"))
        try:
            return QdrantSearch(host=h, port=p)
        except Exception:
            return None

    qdrant = _get_qdrant()
    if qdrant is None:
        st.warning("无法连接 Qdrant (localhost:6334)。")
        return
    try:
        colls = sorted(
            c.name for c in qdrant._client.get_collections().collections
        )
    except Exception:
        colls = []
    if not colls:
        st.info("暂无集合。")
        return
    c1, c2 = st.columns([2, 1])
    with c1:
        selected = st.selectbox("集合", colls, key="kb_coll")
    with c2:
        pp = st.selectbox("每页", [10, 20, 50, 100], index=1, key="kb_pp")
    sq = st.text_input("搜索", placeholder="关键词...", key="kb_sq")
    if "kb_page" not in st.session_state:
        st.session_state.kb_page = 1
    try:
        total = qdrant._client.count(selected).count
    except Exception:
        total = 0
    mp = max(1, (total + pp - 1) // pp)
    if sq:
        try:
            app_cfg = load_app_config()
            pv = app_cfg.embed_provider()
            from src.llm.client import LLMClient  # noqa: E402
            cl = LLMClient(base_url=pv.base_url, api_key=pv.api_key)
            vs = cl.embed(pv.model, sq)
            results = qdrant.search(
                collection=selected, vector=vs[0], query_text=sq,
                limit=pp,
                offset=(st.session_state.kb_page - 1) * pp,
            )
            st.caption(f"搜索 '{sq}' 找到 {len(results)} 条")
            for r in results:
                pl = r.get("payload", {})
                sc = r.get("score", 0)
                with st.expander(f"ID: {r['id']}  |  {sc:.4f}"):
                    txt = pl.get("text", "")
                    if txt and sq.strip():
                        st.markdown(
                            _highlight_term(str(txt), sq),
                            unsafe_allow_html=True,
                        )
                    st.json(pl)
        except Exception as e:
            st.error(f"搜索失败: {e}")
        return
    pg1, pg2, pg3 = st.columns([1, 2, 1])
    with pg1:
        if st.button("上一页") and st.session_state.kb_page > 1:
            st.session_state.kb_page -= 1
            st.rerun()
    with pg2:
        st.markdown(f"**第 {st.session_state.kb_page}/{mp} 页**（共 {total}）")
    with pg3:
        if st.button("下一页") and st.session_state.kb_page < mp:
            st.session_state.kb_page += 1
            st.rerun()
    try:
        records, _ = qdrant.scroll(
            collection=selected, limit=pp,
            offset=(st.session_state.kb_page - 1) * pp,
        )
        for r in records:
            with st.expander(f"ID: {r['id']}"):
                st.json(r.get("payload", {}))
    except Exception as e:
        st.error(f"加载失败: {e}")


# ---------------------------------------------------------------------------
# ── Workflow Status ──
# ---------------------------------------------------------------------------
def _page_workflow_status():
    st.markdown("### 工作流状态")
    if not HAS_SRC:
        st.error("无法加载 src 模块")
        return
    try:
        app_cfg = load_app_config()
        for name, wf in app_cfg.workflows.items():
            with st.expander(f"{name} — {wf.get('description','')}"):
                st.markdown(
                    f"**Collections:** `{wf.get('collections',['default'])}`"
                )
                st.markdown(
                    f"**Return Mode:** `{wf.get('return_mode','full')}`"
                )
                nds = wf.get("nodes", [])
                if nds:
                    st.markdown("**DAG:**")
                    _render_dag_svg(nds)
                    st.markdown("**配置:**")
                    app_cfg2 = load_app_config()
                    cols = st.columns(min(len(nds), 6))
                    for i, n in enumerate(nds):
                        nt = n.get("next_type", "one")
                        if nt == "if-then":
                            badge = " ⇢"
                        elif nt == "switch":
                            badge = " ⇉"
                        else:
                            badge = ""
                        with cols[i % len(cols)]:
                            lp = f"{n['name']}{badge}"
                            with st.popover(lp, use_container_width=True):
                                st.caption(f"路由: `{nt}`")
                                if n.get("next"):
                                    st.caption(f"后继: `{n['next']}`")
                                pn = wf.get("_product", name)
                                key = f"{pn}:{n['name']}"
                                cdata = app_cfg2.nodes.get(key)
                                if cdata:
                                    st.json(cdata)
                                else:
                                    st.caption("无独立配置")
        st.divider()
        st.subheader("LLM")
        if app_cfg.llm:
            st.write(f"默认: `{app_cfg.llm.default}`")
            for pn, p in app_cfg.llm.providers.items():
                st.caption(f"  {pn}: {p.type}/{p.model} @ {p.base_url}")
        st.subheader("Embedding")
        if app_cfg.embed:
            st.write(f"默认: `{app_cfg.embed.default}`")
            for pn, p in app_cfg.embed.providers.items():
                st.caption(
                    f"  {pn}: {p.type}/{p.model}({p.dims}d)"
                    f" @ {p.base_url}"
                )
    except Exception as e:
        st.error(f"加载失败: {e}")


# ---------------------------------------------------------------------------
# ── Document Management ──
# ---------------------------------------------------------------------------
def _page_document_management():
    st.markdown("### 文档管理")
    if not HAS_SRC:
        st.warning("无法加载 src 模块")
        return
    st.subheader("上传文档")
    uf = st.file_uploader(
        "选择文件 (.txt .md .pdf .docx .csv .xlsx)",
        type=["txt", "md", "pdf", "docx", "csv", "xlsx"], key="doc_up",
    )
    c1, c2 = st.columns(2)
    with c1:
        uc = st.text_input("目标集合", value="default", key="up_coll")
    with c2:
        ucs = st.number_input(
            "分块大小", value=800, min_value=64, max_value=4096,
            key="up_cs",
        )
    if uf and st.button("上传并构建"):
        with st.spinner("处理中..."):
            import tempfile
            tmp = Path(tempfile.gettempdir()) / uf.name
            tmp.write_bytes(uf.getvalue())
            try:
                from src.config import load_app_config  # noqa: E402
                from src.ingestion.builder import build_document  # noqa: E402
                from src.llm.client import LLMClient  # noqa: E402
                from src.rag.qdrant import QdrantSearch  # noqa: E402
                ac = load_app_config()
                ep = ac.embed_provider()
                qh = os.environ.get("QDRANT_HOST", "localhost")
                qp = int(os.environ.get("QDRANT_PORT", "6334"))
                qd = QdrantSearch(host=qh, port=qp)
                ec = LLMClient(base_url=ep.base_url, api_key=ep.api_key)
                cnt = build_document(
                    tmp, uc, qd, ec, ep.model, chunk_size=int(ucs),
                )
                st.success(f"完成！{cnt} 分块 → `{uc}`")
            except Exception as e:
                st.error(f"失败: {e}")
    st.divider()
    st.subheader("扫描目录")
    ca, cb = st.columns(2)
    with ca:
        sd = st.text_input("目录", value="data/documents", key="sc_dir")
    with cb:
        sc = st.text_input("集合", value="default", key="sc_coll")
    if st.button("扫描并构建"):
        with st.spinner(f"扫描 `{sd}`..."):
            try:
                from src.config import load_app_config  # noqa: E402
                from src.ingestion.builder import build_directory  # noqa: E402
                from src.llm.client import LLMClient  # noqa: E402
                from src.rag.qdrant import QdrantSearch  # noqa: E402
                ac = load_app_config()
                ep = ac.embed_provider()
                qh = os.environ.get("QDRANT_HOST", "localhost")
                qp = int(os.environ.get("QDRANT_PORT", "6334"))
                qd = QdrantSearch(host=qh, port=qp)
                ec = LLMClient(base_url=ep.base_url, api_key=ep.api_key)
                cnt = build_directory(sd, sc, qd, ec, ep.model)
                st.success(f"完成！{cnt} 分块 → `{sc}`")
            except Exception as e:
                st.error(f"失败: {e}")


# ---------------------------------------------------------------------------
# ── Metrics ──
# ---------------------------------------------------------------------------
def _page_metrics():
    st.markdown("### 运行指标")
    try:
        from src.metrics.store import MetricsStore  # noqa: E402
    except ImportError:
        st.warning("无法加载 MetricsStore。")
        return
    ms = MetricsStore()
    st.caption(f"数据库: `{ms.db_path}`")
    try:
        sessions = ms.query_sessions(limit=50)
    except Exception as e:
        st.error(f"查询失败: {e}")
        return
    if not sessions:
        st.info("暂无运行记录。")
        return
    if HAS_SRC:
        app_cfg = load_app_config()
    else:
        app_cfg = None
    st.subheader("会话列表")
    if sessions:
        buf = _io.StringIO()
        w = _csv.writer(buf)
        w.writerow([
            "chat_id", "turns", "total_duration_ms",
            "first_at", "last_at",
        ])
        for s in sessions:
            w.writerow([
                s["chat_id"], s["turn_count"],
                s.get("total_duration_ms", ""),
                s.get("first_at", ""), s.get("last_at", ""),
            ])
        st.download_button(
            "CSV", buf.getvalue(), "sessions.csv",
            "text/csv", key="mtr_csv",
        )
    for sess in sessions:
        cid = sess["chat_id"]
        info_line = (
            f"`{cid[:16]}...` | {sess['turn_count']}轮"
            f" | {(sess.get('total_duration_ms', 0) or 0):.0f}ms"
        )
        with st.expander(info_line):
            try:
                turns = ms.query_session_turns(cid)
            except Exception:
                turns = []
            for turn in turns:
                tid = turn["turn_id"]
                wf = turn["workflow_name"]
                dur = turn.get("duration_ms") or 0
                tur_line = (
                    f"Turn {tid} | {wf} | {turn['node_count']}节点"
                    f" | {dur:.0f}ms"
                )
                with st.expander(tur_line):
                    st.caption(f"Query: {(turn.get('query') or '')[:80]}")
                    st.caption(f"Reply: {(turn.get('reply') or '')[:80]}")
                    try:
                        nds2 = ms.query_turn_nodes(turn["run_id"])
                    except Exception:
                        nds2 = []
                    nb = {n["node_name"]: n for n in nds2}
                    wf_def = (
                        app_cfg.workflows.get(wf, {}) if app_cfg else {}
                    )
                    wf_nds = wf_def.get("nodes", [])
                    if wf_nds:
                        st.markdown("**DAG:**")
                        ndm = {}
                        for n in wf_nds:
                            nd = nb.get(n["name"])
                            if nd:
                                sts2 = "failed" if nd.get(
                                    "status", "ok"
                                ) != "ok" else "executed"
                                ndm[n["name"]] = {
                                    "status": sts2,
                                    "tool": str(nd.get("tool_name") or ""),
                                    "duration_ms": float(
                                        nd.get("duration_ms") or 0
                                    ),
                                }
                            else:
                                ndm[n["name"]] = {"status": "skipped"}
                        _render_dag_svg(wf_nds, ndm, height=300)
                        st.markdown("**详情:**")
                        nc2 = st.columns(min(len(wf_nds), 6))
                        for i, n in enumerate(wf_nds):
                            nd = nb.get(n["name"])
                            with nc2[i % len(nc2)]:
                                if nd:
                                    ok = nd.get("status", "ok") == "ok"
                                    icon = "✅" if ok else "❌"
                                    dur2 = nd.get("duration_ms") or 0
                                    pl = (
                                        f"{icon} {n['name']}"
                                        f" ({dur2:.0f}ms)"
                                    )
                                    with st.popover(
                                        pl, use_container_width=True,
                                    ):
                                        inp = nd.get("input_data") or ""
                                        out = nd.get("output_text") or ""
                                        if inp:
                                            st.markdown("**输入:**")
                                            _pretty_display(inp)
                                        if out:
                                            st.markdown("**输出:**")
                                            _pretty_display(out)
                                        if nd.get("error_message"):
                                            st.error(nd["error_message"])
                                        try:
                                            tls = ms.query_node_tools(
                                                nd["node_log_id"],
                                            )
                                        except Exception:
                                            tls = []
                                        for tlog in tls:
                                            td = (
                                                tlog.get("duration_ms")
                                                or 0
                                            )
                                            ok2 = tlog.get(
                                                "status", "ok"
                                            ) == "ok"
                                            ti = "✅" if ok2 else "❌"
                                            tn = tlog["tool_name"]
                                            st.markdown(
                                                f"🔧 `{tn}` {ti}"
                                                f" ({td:.0f}ms)"
                                            )
                                            ip = tlog.get("input_params")
                                            if ip:
                                                st.caption("参数:")
                                                _pretty_display(ip)
                                            op = tlog.get("output_result")
                                            if op:
                                                st.caption("结果:")
                                                _pretty_display(op)
                                else:
                                    st.markdown(
                                        "<span style='color:#9e9e9e'>"
                                        f"⚪ {n['name']}</span>",
                                        unsafe_allow_html=True,
                                    )
                    else:
                        for node in nds2:
                            ok3 = node.get("status", "ok") == "ok"
                            si = "✅" if ok3 else "❌"
                            dur3 = node.get("duration_ms") or 0
                            tool3 = node.get("tool_name") or "—"
                            el = (
                                f"{si} {node['node_name']} (`{tool3}`)"
                                f" — {dur3:.0f}ms"
                            )
                            with st.expander(el):
                                if node.get("input_data"):
                                    st.markdown("**输入:**")
                                    _pretty_display(node["input_data"])
                                if node.get("output_text"):
                                    st.markdown("**输出:**")
                                    _pretty_display(node["output_text"])
                                if node.get("error_message"):
                                    st.error(node["error_message"])
                                try:
                                    tls2 = ms.query_node_tools(
                                        node["node_log_id"],
                                    )
                                except Exception:
                                    tls2 = []
                                for tlog in tls2:
                                    td2 = (
                                        tlog.get("duration_ms") or 0
                                    )
                                    ok4 = tlog.get(
                                        "status", "ok"
                                    ) == "ok"
                                    ti2 = "✅" if ok4 else "❌"
                                    tn = tlog["tool_name"]
                                    st.markdown(
                                        f"🔧 `{tn}` {ti2} ({td2:.0f}ms)"
                                    )
                                    ip2 = tlog.get("input_params")
                                    if ip2:
                                        st.caption("参数:")
                                        _pretty_display(ip2)
                                    op2 = tlog.get("output_result")
                                    if op2:
                                        st.caption("结果:")
                                        _pretty_display(op2)


# ---------------------------------------------------------------------------
# route
# ---------------------------------------------------------------------------
nv = st.session_state.nav
if nv == "聊天":
    _page_chat()
elif nv == "知识库浏览":
    _page_knowledge_browser()
elif nv == "工作流状态":
    _page_workflow_status()
elif nv == "文档管理":
    _page_document_management()
elif nv == "运行指标":
    _page_metrics()
