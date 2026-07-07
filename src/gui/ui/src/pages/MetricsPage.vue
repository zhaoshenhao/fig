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
          <div class="fg"><label>工作流</label><input v-model="fWorkflow" class="field" placeholder="部分匹配..." /></div>
          <div class="fg"><label>节点名</label><input v-model="fNode" class="field" placeholder="部分匹配..." /></div>
          <div class="fg"><label>工具名</label><input v-model="fTool" class="field" placeholder="部分匹配..." /></div>
          <div class="fg"><label>输入</label><input v-model="fInput" class="field" placeholder="部分匹配..." /></div>
          <div class="fg"><label>输出</label><input v-model="fOutput" class="field" placeholder="部分匹配..." /></div>
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

    <div class="table-wrap">
      <div v-if="loading2" class="empty" style="padding:20px">加载中...</div>
      <div v-else-if="!rows.length" class="empty" style="padding:20px">暂无匹配的记录</div>
      <table v-else class="data-table">
        <thead>
          <tr>
            <th @click="toggleSort('chat_id')" class="sortable">会话 ID {{ sortIcon('chat_id') }}</th>
            <th @click="toggleSort('first_at')" class="sortable">开始时间 {{ sortIcon('first_at') }}</th>
            <th>工作流</th>
            <th @click="toggleSort('turn_count')" class="sortable">轮次 {{ sortIcon('turn_count') }}</th>
            <th @click="toggleSort('duration_ms')" class="sortable">总耗时 {{ sortIcon('duration_ms') }}</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.chat_id">
            <td><code>{{ row.chat_id?.slice(0,16) }}...</code></td>
            <td style="font-size:0.75rem;color:var(--text3)">{{ row.first_at }}</td>
            <td>{{ row.workflow_names || "-" }}</td>
            <td>{{ row.turn_count }}</td>
            <td>{{ ((row.total_duration_ms||0)/1000).toFixed(1) }}s</td>
            <td><button class="btn-sm" @click="openSession(row.chat_id)">查看</button></td>
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
            <option v-for="t in turnList" :key="t.turn_id" :value="t.turn_id">Turn {{ t.turn_id }} | {{ t.workflow_name }}</option>
          </select>
          <button class="btn" @click="detailSess=null">✕</button>
        </div>
        <div class="modal-split">
          <div class="modal-dag">
            <DAGView v-if="detailTurn?._wfNodes?.length" :nodes="detailTurn._wfNodes" :nodeData="detailTurn._nodeMap" height="100%" @selectNode="onSelectNode" />
            <div v-else class="empty" style="padding:10px">无 DAG</div>
          </div>
          <div class="modal-io">
            <div class="panel-tabs">
              <button :class="['tab', { active: ioTab === 'input' }]" @click="ioTab='input'">输入</button>
              <button :class="['tab', { active: ioTab === 'output' }]" @click="ioTab='output'">输出</button>
            </div>
            <div class="panel-body scroll">
              <pre v-if="ioTab === 'input'" class="hl-json" v-html="highlightJSON(ioData.input)"></pre>
              <pre v-else class="hl-json" v-html="highlightJSON(ioData.output)"></pre>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, inject } from "vue";
import { api } from "../api.js";
import DAGView from "../components/DAGView.vue";

const toast = inject("toast");

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
const fDuration = ref("");

const detailSess = ref("");
const turnList = ref([]);
const detailTurnId = ref(0);
const ioTab = ref("input");
const ioData = ref({ input: "(无)", output: "(无)" });

const DURATION_RANGES = [[0, 1000], [1001, 5000], [5001, 10000], [10001, Infinity]];

const detailTurn = computed(() => turnList.value.find(t => t.turn_id === detailTurnId.value) || null);

function parseTimePreset(p) {
  const now = Date.now();
  const m = { m: 60000, h: 3600000, d: 86400000, w: 604800000, M: 2592000000 };
  for (const [k, v] of Object.entries(m)) {
    if (p.endsWith(k)) { const n = parseInt(p); return new Date(now - n * v).toISOString(); }
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
    if (timeFrom.value) params.time_from = timeFrom.value;
    if (timeTo.value) params.time_to = timeTo.value;
    if (fWorkflow.value) params.workflow = fWorkflow.value;
    if (fNode.value) params.node = fNode.value;
    if (fTool.value) params.tool = fTool.value;
    if (fInput.value) params.input_text = fInput.value;
    if (fOutput.value) params.output_text = fOutput.value;
    if (fDuration.value) {
      const [lo, hi] = DURATION_RANGES[parseInt(fDuration.value) - 1];
      params.duration_min = lo;
      if (hi < Infinity) params.duration_max = hi;
    }
    const d = await api.get("/sessions", params);
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
  fDuration.value = "";
  page.value = 1;
  doSearch();
}

async function openSession(chatId) {
  detailSess.value = chatId;
  detailTurnId.value = 0;
  ioTab.value = "input";
  ioData.value = { input: "(无)", output: "(无)" };
  turnList.value = [];
  try {
    const d = await api.get(`/sessions/${chatId}`);
    const turnsWithNodes = [];
    for (const t of (d.turns || [])) {
      try {
        const td = await api.get(`/sessions/${chatId}/turns/${t.turn_id}`);
        const wfName = td.run?.workflow_name || t.workflow_name;
        let wfNodes = [];
        try {
          const wf = await api.get(`/workflows/${wfName}`);
          wfNodes = (wf.nodes || []).map(n => ({ ...n, tool: n.tool || "" }));
        } catch (_) {}
        const nodeMap = {}, nodeData = {};
        for (const n of (td.nodes || [])) {
          const status = n.status === "ok" ? "executed" : "failed";
          nodeMap[n.node_name] = status;
          nodeData[n.node_name] = { status, tool: n.tool_name || "", duration_ms: n.duration_ms || 0, input: n.input_data || "", output: n.output_text || "" };
        }
        turnsWithNodes.push({ ...t, nodes: td.nodes || [], _wfNodes: wfNodes, _nodeMap: nodeMap, _nodeData: nodeData });
      } catch (_) { turnsWithNodes.push({ ...t, nodes: [], _wfNodes: [], _nodeMap: {}, _nodeData: {} }); }
    }
    turnList.value = turnsWithNodes;
    if (turnsWithNodes.length) detailTurnId.value = turnsWithNodes[0].turn_id;
  } catch (e) { toast("加载详情失败: " + e.message, "error"); }
}

function onSelectNode(data) {
  const turn = detailTurn.value;
  const nd = turn?._nodeData?.[data.name] || {};
  ioData.value = { input: nd.input || "(无)", output: nd.output || "(无)" };
  ioTab.value = nd.output ? "output" : "input";
}

function highlightJSON(text) {
  if (!text || text === "(无)") return '<span style="color:var(--text3)">(无)</span>';
  try { JSON.parse(text); } catch { return text; }
  const fmt = typeof text === "string" ? text : JSON.stringify(text, null, 2);
  return fmt.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/("(?:[^"\\]|\\.)*")\s*:/g, '<span class="jk">$1</span>:')
    .replace(/: ("(?:[^"\\]|\\.)*")/g, ': <span class="js">$1</span>')
    .replace(/: (\d+\.?\d*)/g, ': <span class="jn">$1</span>')
    .replace(/: (true|false|null)/g, ': <span class="jb">$1</span>');
}

onMounted(doSearch);
</script>

<style scoped>
.empty { text-align: center; color: var(--text3); padding: 40px 0; font-size: 0.9rem; }
.field { padding: 4px 6px; border: 1px solid var(--border); border-radius: 4px; background: var(--bg); font-size: 0.78rem; width:100%; }
.btn { padding: 5px 14px; border: 1px solid var(--border); border-radius: 6px; background: var(--bg); font-size: 0.82rem; cursor: pointer; color: var(--text); }
.btn-sm { padding: 2px 10px; font-size: 0.75rem; border: 1px solid var(--border); border-radius: 4px; background: var(--bg); cursor: pointer; color: var(--text); }
.btn-sm:disabled { opacity: 0.4; cursor: not-allowed; }

.filter-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 6px 12px; padding: 8px 0; }
.fg { display: flex; flex-direction: column; gap: 2px; }
.fg label { font-size: 0.72rem; color: var(--text3); }

.table-wrap { flex: 1; overflow: auto; min-height: 0; }
.data-table { width: 100%; border-collapse: collapse; font-size: 0.8rem; }
.data-table th, .data-table td { padding: 5px 8px; border-bottom: 1px solid var(--border); text-align: left; white-space: nowrap; }
.data-table th { background: var(--bg2); position: sticky; top: 0; z-index: 1; font-weight: 600; color: var(--text2); }
.data-table code { font-size: 0.72rem; }
.sortable { cursor: pointer; user-select: none; }
.sortable:hover { color: var(--accent); }

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

.hl-json { font-size: 0.75rem; white-space: pre; margin: 0; font-family: "Cascadia Code", "Fira Code", "Consolas", monospace; color: var(--text2); }
.hl-json :deep(.jk) { color: #0550ae; }
.hl-json :deep(.js) { color: #0a3069; }
.hl-json :deep(.jn) { color: #0550ae; }
.hl-json :deep(.jb) { color: #cf222e; }
</style>
