<template>
  <div style="display:flex;flex-direction:column;height:calc(100vh - 80px)">
    <div style="flex-shrink:0;margin-bottom:8px">
      <details>
        <summary style="cursor:pointer;padding:4px 0;color:var(--text2);font-size:0.82rem">搜索过滤</summary>
        <div class="filter-grid">
          <div class="fg">
            <label>时间范围</label>
            <select v-model="timeRange" class="field" @change="onTimePreset">
              <option value="">全部</option>
              <option v-for="p in TIME_PRESETS" :key="p.value" :value="p.value">{{ p.label }}</option>
              <option value="custom">自定义</option>
            </select>
          </div>
          <div class="fg" v-if="timeRange === 'custom'">
            <label>开始</label><input type="datetime-local" v-model="timeFrom" class="field" />
          </div>
          <div class="fg" v-if="timeRange === 'custom'">
            <label>结束</label><input type="datetime-local" v-model="timeTo" class="field" />
          </div>
          <div class="fg">
            <label>工作流</label>
            <select v-model="fWorkflow" class="field">
              <option value="">全部</option>
              <option v-for="w in facets.workflows" :key="w" :value="w">{{ w }}</option>
            </select>
          </div>
          <div class="fg">
            <label>节点名</label>
            <select v-model="fNode" class="field">
              <option value="">全部</option>
              <option v-for="n in facets.nodes" :key="n" :value="n">{{ n }}</option>
            </select>
          </div>
          <div class="fg">
            <label>工具名</label>
            <select v-model="fTool" class="field">
              <option value="">全部</option>
              <option v-for="t in facets.tools" :key="t" :value="t">{{ t }}</option>
            </select>
          </div>
          <div class="fg"><label>输入</label><input v-model="fInput" class="field" placeholder="部分匹配..." /></div>
          <div class="fg"><label>输出</label><input v-model="fOutput" class="field" placeholder="部分匹配..." /></div>
          <div class="fg"><label>标题</label><input v-model="fTitle" class="field" placeholder="会话标题（部分匹配）" /></div>
          <div class="fg">
            <label>用户评价</label>
            <select v-model="fFeedback" class="field">
              <option value="">全部</option>
              <option value="none">空（无评价）</option>
              <option value="up">好评</option>
              <option value="down">差评</option>
            </select>
          </div>
          <div class="fg">
            <label>耗时</label>
            <select v-model="fDuration" class="field">
              <option value="">全部</option>
              <option value="1">&lt; 1s</option>
              <option value="2">1-5s</option>
              <option value="3">5-10s</option>
              <option value="4">&gt; 10s</option>
            </select>
          </div>
          <div class="fg" style="align-self:flex-end;flex-direction:row;gap:4px">
            <button class="btn" @click="doSearch">搜索</button>
            <button class="btn" @click="resetFilters">重置</button>
          </div>
        </div>
      </details>
    </div>

    <div style="flex-shrink:0;display:flex;justify-content:flex-end;margin-bottom:6px">
      <button class="btn" @click="exportTraining">导出训练数据 (JSONL)</button>
    </div>

    <div class="table-wrap">
      <div v-if="loading2" class="empty" style="padding:20px">加载中...</div>
      <div v-else-if="!rows.length" class="empty" style="padding:20px">暂无匹配的记录</div>
      <table v-else class="data-table">
        <thead>
          <tr>
            <th @click="toggleSort('chat_id')" class="sortable">会话 ID {{ sortIcon('chat_id') }}</th>
            <th>标题 / 标签</th>
            <th @click="toggleSort('first_at')" class="sortable">开始时间 {{ sortIcon('first_at') }}</th>
            <th>工作流</th>
            <th @click="toggleSort('turn_count')" class="sortable">轮次 {{ sortIcon('turn_count') }}</th>
            <th @click="toggleSort('duration_ms')" class="sortable">总耗时 {{ sortIcon('duration_ms') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.chat_id" @click="openSession(row.chat_id)" class="clickable">
            <td><code>{{ row.chat_id?.slice(0,16) }}...</code></td>
            <td>
              <span v-if="row.title" class="sess-title">{{ row.title }}</span>
              <span v-else class="sess-title muted">（未命名）</span>
              <span v-for="t in (row.tags||[])" :key="t" class="tag-chip">{{ t }}</span>
            </td>
            <td style="font-size:0.75rem;color:var(--text3)">{{ row.first_at }}</td>
            <td>{{ row.workflow_names || "-" }}</td>
            <td>{{ row.turn_count }}</td>
            <td>{{ ((row.total_duration_ms||0)/1000).toFixed(1) }}s</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="pager" v-if="total > pageSize">
      <button class="btn-sm" :disabled="page <= 1" @click="page--;doSearch()">上一页</button>
      <span>第 {{ page }} 页 (共 {{ Math.ceil(total / pageSize) }} / {{ total }} 条)</span>
      <button class="btn-sm" :disabled="page >= Math.ceil(total / pageSize)" @click="page++;doSearch()">下一页</button>
    </div>

    <div v-if="detailSess" class="modal-overlay" @click.self="detailSess=null">
      <div class="modal-panel">
        <div class="modal-hd">
          <b>{{ detailSess.slice(0,24) }}...</b>
          <select v-model="detailTurnId" class="field" style="width:auto;margin:0 12px">
            <option v-for="t in turnList" :key="t.turn_id" :value="t.turn_id">Turn {{ t.turn_id }} | {{ t.workflow_name }} | {{ ((t.duration_ms||0)/1000).toFixed(1) }}s</option>
          </select>
          <button class="btn" @click="detailSess=null">✕</button>
        </div>
        <div class="modal-split">
          <div class="modal-dag">
            <DAGView v-if="detailTurn?._wfNodes?.length" :nodes="detailTurn._wfNodes" :nodeData="detailTurn._nodeData" height="100%" @selectNode="onSelectNode" />
            <div v-else class="empty" style="padding:10px">无 DAG</div>
          </div>
          <div class="modal-io">
            <div class="panel-tabs">
              <button :class="['tab', { active: ioTab === 'status' }]" @click="ioTab='status'">状态</button>
              <button :class="['tab', { active: ioTab === 'input' }]" @click="ioTab='input'">输入</button>
              <button :class="['tab', { active: ioTab === 'output' }]" @click="ioTab='output'">输出</button>
              <button :class="['tab', { active: ioTab === 'config' }]" @click="ioTab='config'">配置</button>
            </div>
            <div class="panel-body scroll">
              <div v-if="ioTab === 'status'">
                <div v-if="turnInfo">
                  <div class="sec-h2">本轮信息（runs）</div>
                  <div class="prop"><span>run_id</span>{{ turnInfo.run.run_id }}</div>
                  <div class="prop"><span>turn_id</span>{{ turnInfo.run.turn_id }}</div>
                  <div class="prop"><span>工作流</span>{{ turnInfo.run.workflow_name }}</div>
                  <div class="prop"><span>状态</span>{{ turnInfo.run.status }}</div>
                  <div class="prop" v-if="turnInfo.run.error_message"><span>错误</span><span class="err">{{ turnInfo.run.error_message }}</span></div>
                  <div class="prop"><span>节点数</span>{{ turnInfo.run.node_count }}</div>
                  <div class="prop"><span>总耗时</span>{{ Math.round(turnInfo.run.duration_ms || 0) }} ms</div>
                  <div class="prop"><span>Tokens</span>{{ (turnInfo.run.prompt_tokens||0) }} + {{ (turnInfo.run.completion_tokens||0) }} = {{ (turnInfo.run.prompt_tokens||0)+(turnInfo.run.completion_tokens||0) }}</div>
                  <div class="prop"><span>时间</span>{{ turnInfo.run.created_at }}</div>
                  <div class="prop prop-block"><span>输入 query</span><div class="prop-val">{{ turnInfo.run.query || '(无)' }}</div></div>
                  <div class="prop prop-block"><span>回复 reply</span><div class="prop-val">{{ turnInfo.run.reply || '(无)' }}</div></div>

                  <div class="sec-h2">用户反馈（feedback）</div>
                  <div v-if="!turnInfo.feedback.length" class="empty" style="padding:8px">暂无反馈</div>
                  <div v-for="f in turnInfo.feedback" :key="f.id" class="fb-item">
                    <span :class="['fb-badge', f.rating]">{{ f.rating === 'up' ? '👍 好评' : '👎 差评' }}</span>
                    <span class="fb-time">{{ f.created_at }}</span>
                    <div v-if="f.comment" class="prop-val">评论：{{ f.comment }}</div>
                    <div v-if="f.correction" class="prop-val">纠错：{{ f.correction }}</div>
                  </div>
                </div>
                <div v-else-if="!statusInfo" class="empty" style="padding:20px">点击 DAG 节点查看状态</div>
                <template v-else>
                  <div class="prop"><span>节点名称</span>{{ statusInfo.name }}</div>
                  <div class="prop"><span>状态</span>{{ statusInfo.status }}</div>
                  <div class="prop"><span>后继</span>{{ statusInfo.next }}</div>
                  <div class="prop"><span>耗时</span>{{ statusInfo.duration }}</div>
                  <div class="prop"><span>工具名称</span>{{ statusInfo.tool }}</div>
                  <div class="prop" v-if="statusInfo.error"><span>工具错误信息</span><span class="err">{{ statusInfo.error }}</span></div>
                  <template v-if="statusInfo.ragRows?.length">
                    <div class="sec-h2">RAG 检索详情（{{ statusInfo.ragCount }} 条，平均分 {{ statusInfo.ragAvgScore }}）</div>
                    <div v-for="r in statusInfo.ragRows" :key="r.id" class="rag-row">
                      <div class="rag-hdr">
                        <span class="rag-score">{{ (r.score||0).toFixed(4) }}</span>
                        <span class="fb-wf">{{ r.collection || '-' }}</span>
                        <span class="fb-time">{{ r.source || '-' }}</span>
                      </div>
                      <div class="rag-preview">{{ r.chunk_preview || "(无)" }}</div>
                    </div>
                  </template>
                </template>
              </div>
              <pre v-else-if="ioTab === 'input'" class="hl-json" v-html="highlightJSON(ioData.input)"></pre>
              <pre v-else-if="ioTab === 'output'" class="hl-json" v-html="highlightJSON(ioData.output)"></pre>
              <pre v-else class="hl-json" v-html="highlightJSON(ioData.config)"></pre>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, inject, watch } from "vue";
import { api } from "../api.js";
import DAGView from "../components/DAGView.vue";

const toast = inject("toast");

/** @type {Record<string, any>} */
const _wfCache = {};

/** @param {string} name */
async function getWfConfig(name) {
  if (_wfCache[name]) return _wfCache[name];
  try {
    _wfCache[name] = await api.get(`/api/v1/workflows/${name}`);
  } catch { _wfCache[name] = { nodes: [] }; }
  return _wfCache[name];
}

const TIME_PRESETS = [
  { label: "最后 5 分钟", value: "5m" }, { label: "最后 10 分钟", value: "10m" },
  { label: "最后 15 分钟", value: "15m" }, { label: "最后 30 分钟", value: "30m" },
  { label: "最后 1 小时", value: "1h" }, { label: "最后 2 小时", value: "2h" },
  { label: "最后 4 小时", value: "4h" }, { label: "最后 12 小时", value: "12h" },
  { label: "最后 24 小时", value: "24h" }, { label: "最后 3 天", value: "3d" },
  { label: "最后 7 天", value: "7d" }, { label: "最后 2 周", value: "2w" },
  { label: "最后 4 周", value: "4w" }, { label: "最后 2 月", value: "2M" },
  { label: "最后 90 天", value: "90d" },
];

const loading2 = ref(true);
const rows = ref([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(20);
const sortBy = ref("first_at");
const sortDir = ref("desc");

const timeRange = ref("");
const timeFrom = ref("");
const timeTo = ref("");
const fWorkflow = ref("");
const fNode = ref("");
const fTool = ref("");
const fInput = ref("");
const fOutput = ref("");
const fFeedback = ref("");
const fTitle = ref("");
const fDuration = ref("");
const facets = ref({ workflows: [], nodes: [], tools: [] });

const detailSess = ref("");const turnList = ref([]);
const detailTurnId = ref(0);
const ioTab = ref("input");
const ioData = ref({ input: "(无)", output: "(无)", config: "(无)" });
const statusInfo = ref(null);
const turnInfo = ref(null);

const DURATION_RANGES = [[0, 1000], [1001, 5000], [5001, 10000], [10001, Infinity]];

const detailTurn = computed(() => turnList.value.find(t => t.turn_id === detailTurnId.value) || null);

watch(detailTurnId, () => {
  ioData.value = { input: "(无)", output: "(无)", config: "(无)" };
  statusInfo.value = null;
  turnInfo.value = null;
});

function toDbTime(d) {
  if (isNaN(d.getTime())) return "";
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getUTCFullYear()}-${p(d.getUTCMonth() + 1)}-${p(d.getUTCDate())} ` +
         `${p(d.getUTCHours())}:${p(d.getUTCMinutes())}:${p(d.getUTCSeconds())}`;
}

function parseTimePreset(p) {
  const now = Date.now();
  const m = { m: 60000, h: 3600000, d: 86400000, w: 604800000, M: 2592000000 };
  for (const [k, v] of Object.entries(m)) {
    if (p.endsWith(k)) { const n = parseInt(p); return toDbTime(new Date(now - n * v)); }
  }
  return null;
}

function onTimePreset() {
  if (timeRange.value && timeRange.value !== "custom") {
    timeFrom.value = parseTimePreset(timeRange.value) || "";
    timeTo.value = "";
  }
}

function toggleSort(col) {
  if (sortBy.value === col) { sortDir.value = sortDir.value === "asc" ? "desc" : "asc"; }
  else { sortBy.value = col; sortDir.value = "asc"; }
  doSearch();
}
function sortIcon(col) {
  if (sortBy.value !== col) return "";
  return sortDir.value === "asc" ? "▲" : "▼";
}

async function doSearch() {
  loading2.value = true;
  try {
    const params = { limit: pageSize.value, offset: (page.value - 1) * pageSize.value, sort_by: sortBy.value, sort_dir: sortDir.value };
    if (timeFrom.value) params.time_from = timeRange.value === "custom" ? toDbTime(new Date(timeFrom.value)) : timeFrom.value;
    if (timeTo.value) params.time_to = timeRange.value === "custom" ? toDbTime(new Date(timeTo.value)) : timeTo.value;
    if (fWorkflow.value) params.workflow = fWorkflow.value;
    if (fNode.value) params.node = fNode.value;
    if (fTool.value) params.tool = fTool.value;
    if (fInput.value) params.input_text = fInput.value;
    if (fOutput.value) params.output_text = fOutput.value;
    if (fFeedback.value) params.feedback = fFeedback.value;
    if (fTitle.value.trim()) params.title = fTitle.value.trim();
    if (fDuration.value) {
      const [lo, hi] = DURATION_RANGES[parseInt(fDuration.value) - 1];
      params.duration_min = lo;
      if (hi < Infinity) params.duration_max = hi;
    }
    const d = await api.get("/api/v1/sessions", params);
    rows.value = d.sessions || [];
    total.value = d.total || 0;
  } catch (e) { toast("搜索失败: " + e.message, "error"); }
  loading2.value = false;
}
function resetFilters() {
  timeRange.value = "";
  timeFrom.value = "";
  timeTo.value = "";
  fWorkflow.value = "";
  fNode.value = "";
  fTool.value = "";
  fInput.value = "";
  fOutput.value = "";
  fFeedback.value = "";
  fTitle.value = "";
  fDuration.value = "";
  page.value = 1;
  doSearch();
}

async function loadFacets() {
  try { facets.value = await api.get("/api/v1/sessions/filters"); }
  catch (_) { /* 下拉为空时用户仍可留空搜索 */ }
}

async function exportTraining() {
  try {
    const blob = await api.getBlob("/export/training.jsonl", { limit: 5000 });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "training.jsonl";
    a.click();
    URL.revokeObjectURL(a.href);
  } catch (e) { toast("导出失败: " + e.message, "error"); }
}

async function openSession(chatId) {
  detailSess.value = chatId;
  detailTurnId.value = 0;
  ioTab.value = "input";
  ioData.value = { input: "(无)", output: "(无)", config: "(无)" };
  turnList.value = [];
  try {
    const d = await api.get(`/api/v1/sessions/${chatId}`);
    // 并行拉取每个 turn 的节点详情（消除 N+1 串行瀑布）
    const turnsWithNodes = await Promise.all((d.turns || []).map(async (t) => {
      try {
        const td = await api.get(`/api/v1/sessions/${chatId}/turns/${t.turn_id}`);
        const wfName = td.run?.workflow_name || t.workflow_name;
        let wfNodes = [];
        try {
          const wf = await getWfConfig(wfName);
          wfNodes = (wf.nodes || []).map(n => ({ ...n, tool: n.tool || "" }));
        } catch (_) {}
        const nodeMap = {}, nodeData = {};
        for (const n of (td.nodes || [])) {
          const status = n.status === "ok" ? "executed" : "failed";
          nodeMap[n.node_name] = status;
          nodeData[n.node_name] = { status, tool: n.tool_name || "", duration_ms: n.duration_ms || 0, input: n.input_data || "", output: n.output_text || "", error: n.error_message || "" };
        }
        for (const n of wfNodes) {
          if (!nodeData[n.name]) nodeData[n.name] = { status: "skipped", tool: n.tool || "", duration_ms: 0, input: "", output: "", error: "" };
        }
        return { ...t, run: td.run || t, feedback: td.feedback || [], rag: td.rag || [],
                 nodes: td.nodes || [], _wfNodes: wfNodes, _nodeMap: nodeMap, _nodeData: nodeData };
      } catch (_) {
        return { ...t, run: t, feedback: [], rag: [],
                 nodes: [], _wfNodes: [], _nodeMap: {}, _nodeData: {} };
      }
    }));
    turnList.value = turnsWithNodes;
    if (turnsWithNodes.length) detailTurnId.value = turnsWithNodes[0].turn_id;
  } catch (e) { toast("加载详情失败: " + e.message, "error"); }
}

async function onSelectNode(data) {
  const turn = detailTurn.value;

  // 虚拟 IN/OUT 节点：显示本轮次完整信息（全部 runs 字段 + feedback）
  if (data.name === "INPUT" || data.name === "OUTPUT") {
    const isIn = data.name === "INPUT";
    const run = turn?.run || turn || {};
    turnInfo.value = { run, feedback: turn?.feedback || [] };
    statusInfo.value = null;
    ioData.value = {
      input: isIn ? (run.query || "(无)") : "(无)",
      output: isIn ? "(无)" : (run.reply || "(无)"),
      config: "(无)",
    };
    ioTab.value = "status";
    return;
  }

  turnInfo.value = null;
  const nd = turn?._nodeData?.[data.name] || {};
  const ragRows = data.tool === "rag_search" ? (turn?.rag || []) : [];
  const STATUS_LABEL = { executed: "已执行", failed: "失败", skipped: "未执行", virtual: "虚拟" };
  const st = nd.status || data.status || "-";
  statusInfo.value = {
    name: data.name,
    status: STATUS_LABEL[st] || st,
    next: (data.next && data.next.length) ? data.next.join(", ") : "-",
    duration: nd.duration_ms ? `${Math.round(Number(nd.duration_ms))} ms` : "-",
    tool: nd.tool || data.tool || "-",
    error: nd.error || "",
    ragCount: ragRows.length,
    ragAvgScore: ragRows.length
      ? (ragRows.reduce((s, r) => s + (r.score || 0), 0) / ragRows.length).toFixed(4)
      : 0,
    ragRows,
  };
  let config = "(无)";
  if (turn?.workflow_name) {
    const wf = await getWfConfig(turn.workflow_name);
    const nc = (wf.nodes || []).find(n => n.name === data.name);
    if (nc?.config) config = JSON.stringify(nc.config, null, 2);
  }
  ioData.value = { input: nd.input || "(无)", output: nd.output || "(无)", config };
  ioTab.value = "status";
}

function highlightJSON(text) {
  if (!text || text === "(无)") return '<span style="color:var(--text3)">(无)</span>';
  let obj;
  try { obj = JSON.parse(text); } catch { return text; }
  const fmt = JSON.stringify(obj, null, 2);
  return fmt.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/("(?:[^"\\]|\\.)*")\s*:/g, '<span class="jk">$1</span>:')
    .replace(/: ("(?:[^"\\]|\\.)*")/g, ': <span class="js">$1</span>')
    .replace(/: (\d+\.?\d*)/g, ': <span class="jn">$1</span>')
    .replace(/: (true|false|null)/g, ': <span class="jb">$1</span>');
}

function onKey(e) {
  if (e.key === "Escape" && detailSess.value) detailSess.value = null;
}

onMounted(() => { doSearch(); loadFacets(); window.addEventListener("keydown", onKey); });
onUnmounted(() => window.removeEventListener("keydown", onKey));
</script>

<style scoped>
.empty { text-align: center; color: var(--text3); padding: 40px 0; font-size: 0.9rem; }
.field { padding: 4px 6px; border: 1px solid var(--border); border-radius: 4px; background: var(--bg); font-size: 0.78rem; width:100%; }
.btn { padding: 5px 14px; border: 1px solid var(--border); border-radius: 6px; background: var(--bg); font-size: 0.82rem; cursor: pointer; color: var(--text); }
.btn-sm { padding: 2px 10px; font-size: 0.75rem; border: 1px solid var(--border); border-radius: 4px; background: var(--bg); cursor: pointer; color: var(--text); }
.btn-sm:disabled { opacity: 0.4; cursor: not-allowed; }

.filter-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 6px 12px; padding: 8px 0; }.fg { display: flex; flex-direction: column; gap: 2px; }
.fg label { font-size: 0.72rem; color: var(--text3); }

.table-wrap { flex: 1; overflow: auto; min-height: 0; }
.data-table { width: 100%; border-collapse: collapse; font-size: 0.8rem; }
.data-table th, .data-table td { padding: 5px 8px; border-bottom: 1px solid var(--border); text-align: left; white-space: nowrap; }
.data-table th { background: var(--bg2); position: sticky; top: 0; z-index: 1; font-weight: 600; color: var(--text2); }
.data-table code { font-size: 0.72rem; }
.sess-title { font-size: 0.8rem; color: var(--text); }
.sess-title.muted { color: var(--text3); }
.tag-chip { display: inline-block; font-size: 0.66rem; color: var(--text2); background: var(--bg3); border-radius: 8px; padding: 0 6px; margin-left: 4px; }
.sortable { cursor: pointer; user-select: none; }
.sortable:hover { color: var(--accent); }
tr.clickable { cursor: pointer; }
tr.clickable:hover { background: var(--bg3); }

.pager { display: flex; gap: 8px; align-items: center; justify-content: center; padding: 6px 0; font-size: 0.8rem; color: var(--text2); flex-shrink: 0; }

.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); z-index: 600; display: flex; align-items: center; justify-content: center; }
.modal-panel { background: var(--bg); border-radius: 12px; width: 90vw; height: 85vh; display: flex; flex-direction: column; box-shadow: var(--shadow-lg); overflow: hidden; }
.modal-hd { display: flex; align-items: center; padding: 8px 14px; background: var(--bg2); border-bottom: 1px solid var(--border); flex-shrink: 0; gap: 8px; font-size: 0.85rem; }
.modal-split { flex: 1; display: flex; flex-direction: column; min-height: 0; }
.modal-dag { flex: 1; min-height: 0; }
.modal-io { flex: 1; min-height: 0; border-top: 1px solid var(--border); display: flex; flex-direction: column; }

.panel-tabs { display: flex; gap: 0; background: var(--bg2); border-bottom: 1px solid var(--border); flex-shrink: 0; }
.tab { padding: 6px 16px; border: none; background: none; font-size: 0.82rem; cursor: pointer; color: var(--text2); border-bottom: 2px solid transparent; }
.tab.active { color: var(--accent); border-bottom-color: var(--accent); font-weight: 600; }
.panel-body { padding: 10px 14px; flex: 1; }
.panel-body.scroll { overflow: auto; }
.prop { font-size: 0.82rem; margin-bottom: 6px; color: var(--text); display: flex; gap: 8px; }
.prop span:first-child { color: var(--text3); font-weight: 600; min-width: 80px; flex-shrink: 0; }
.prop .err { color: var(--hl-string, #f44336); white-space: pre-wrap; word-break: break-word; }
.prop.prop-block { flex-direction: column; gap: 2px; }
.prop-val { white-space: pre-wrap; word-break: break-word; color: var(--text2); font-size: 0.8rem; background: var(--bg2); padding: 4px 6px; border-radius: 4px; }
.sec-h2 { font-size: 0.8rem; font-weight: 700; color: var(--text2); margin: 10px 0 6px; border-bottom: 1px solid var(--border); padding-bottom: 3px; }
.fb-item { border: 1px solid var(--border); border-radius: 6px; padding: 6px 8px; margin-bottom: 6px; background: var(--bg2); }
.fb-badge { font-size: 0.72rem; font-weight: 600; padding: 1px 8px; border-radius: 10px; }
.fb-badge.up { background: #dcfce7; color: #166534; }
.fb-badge.down { background: #fee2e2; color: #991b1b; }
.fb-time { font-size: 0.68rem; color: var(--text3); margin-left: 8px; }
.rag-row { border: 1px solid var(--border); border-radius: 6px; padding: 4px 8px; margin-bottom: 4px; background: var(--bg2); }
.rag-hdr { display: flex; align-items: center; gap: 8px; margin-bottom: 2px; }
.rag-score { font-size: 0.72rem; font-weight: 700; color: var(--accent); min-width: 48px; }
.rag-preview { font-size: 0.74rem; color: var(--text2); white-space: pre-wrap; word-break: break-word; max-height: 120px; overflow: auto; }
.fb-wf { font-size: 0.75rem; color: var(--text2); background: var(--bg3); padding: 1px 6px; border-radius: 4px; }

.hl-json { font-size: 0.75rem; white-space: pre; margin: 0; font-family: "Cascadia Code", "Fira Code", "Consolas", monospace; color: var(--text2); }
.hl-json :deep(.jk) { color: var(--hl-key); }
.hl-json :deep(.js) { color: var(--hl-string); }
.hl-json :deep(.jn) { color: var(--hl-number); }
.hl-json :deep(.jb) { color: var(--hl-bool); }

</style>
