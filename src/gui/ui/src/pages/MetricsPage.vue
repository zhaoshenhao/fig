<template>
  <div style="display:flex;flex-direction:column;height:calc(100vh - 80px)">
    <div style="flex-shrink:0;margin-bottom:8px">
      <details style="font-size:0.82rem">
        <summary style="cursor:pointer;padding:4px 0;color:var(--text2)">搜索过滤</summary>
        <div class="filter-grid">
          <div class="fg">
            <label>时间范围</label>
            <select v-model="f.timeRange" class="field">
              <option value="">全部</option>
              <option v-for="p in TIME_PRESETS" :key="p.value" :value="p.value">{{ p.label }}</option>
              <option value="custom">自定义</option>
            </select>
          </div>
          <div class="fg" v-if="f.timeRange === 'custom'">
            <label>开始</label><input type="datetime-local" v-model="f.timeFrom" class="field" />
          </div>
          <div class="fg" v-if="f.timeRange === 'custom'">
            <label>结束</label><input type="datetime-local" v-model="f.timeTo" class="field" />
          </div>
          <div class="fg">
            <label>工作流</label><input v-model="f.workflow" class="field" placeholder="部分匹配..." />
          </div>
          <div class="fg">
            <label>节点名</label><input v-model="f.node" class="field" placeholder="部分匹配..." />
          </div>
          <div class="fg">
            <label>工具名</label><input v-model="f.tool" class="field" placeholder="部分匹配..." />
          </div>
          <div class="fg">
            <label>输入</label><input v-model="f.input" class="field" placeholder="部分匹配..." />
          </div>
          <div class="fg">
            <label>输出</label><input v-model="f.output" class="field" placeholder="部分匹配..." />
          </div>
          <div class="fg">
            <label>耗时</label>
            <select v-model="f.duration" class="field">
              <option value="">全部</option>
              <option value="1">&lt; 1s</option>
              <option value="2">1-5s</option>
              <option value="3">5-10s</option>
              <option value="4">&gt; 10s</option>
            </select>
          </div>
          <div class="fg" style="align-self:flex-end">
            <button class="btn" @click="doSearch">搜索</button>
            <button class="btn" @click="resetFilters" style="margin-left:4px">重置</button>
          </div>
        </div>
      </details>
    </div>

    <div class="split-area">
      <div class="split-top">
        <div v-if="loading" class="empty">加载中...</div>
        <div v-else-if="!filtered.length" class="empty" style="padding:10px">暂无匹配的记录</div>
        <template v-else>
          <div class="table-wrap">
            <table class="data-table">
              <thead>
                <tr>
                  <th @click="toggleSort('chat_id')" class="sortable">会话 ID {{ sortIcon('chat_id') }}</th>
                  <th @click="toggleSort('workflow_name')" class="sortable">工作流 {{ sortIcon('workflow_name') }}</th>
                  <th @click="toggleSort('turn_count')" class="sortable">轮次 {{ sortIcon('turn_count') }}</th>
                  <th @click="toggleSort('total_duration_ms')" class="sortable">总耗时 {{ sortIcon('total_duration_ms') }}</th>
                  <th @click="toggleSort('first_at')" class="sortable">开始时间 {{ sortIcon('first_at') }}</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in pageRows" :key="row.chat_id" :class="{ selected: selectedSess === row.chat_id }">
                  <td><code>{{ row.chat_id?.slice(0,16) }}...</code></td>
                  <td>{{ row.workflow_name || "-" }}</td>
                  <td>{{ row.turn_count }}</td>
                  <td>{{ ((row.total_duration_ms||0)/1000).toFixed(1) }}s</td>
                  <td style="font-size:0.75rem;color:var(--text3)">{{ row.first_at }}</td>
                  <td><button class="btn-sm" @click="viewSession(row)">查看</button></td>
                </tr>
              </tbody>
            </table>
          </div>
          <div class="pager">
            <button class="btn-sm" :disabled="page <= 1" @click="page--">上一页</button>
            <span>{{ page }} / {{ maxPage }} (共 {{ filtered.length }})</span>
            <button class="btn-sm" :disabled="page >= maxPage" @click="page++">下一页</button>
          </div>
        </template>
      </div>

      <div class="split-bottom" v-if="turnList.length">
        <div class="panel-tabs">
          <button :class="['tab', { active: detailTab === 'dag' }]" @click="detailTab='dag'">DAG</button>
          <button :class="['tab', { active: detailTab === 'io' }]" @click="detailTab='io'">输入/输出</button>
          <select v-model="detailTurnId" class="field" style="margin-left:8px;font-size:0.78rem">
            <option v-for="t in turnList" :key="t.turn_id" :value="t.turn_id">Turn {{ t.turn_id }}</option>
          </select>
          <button class="tab close" @click="turnList=[];selectedSess=''">✕</button>
        </div>

        <div v-if="detailTab === 'dag' && detailTurn?._wfNodes?.length" style="flex:1;min-height:0">
          <DAGView :nodes="detailTurn._wfNodes" :nodeData="detailTurn._nodeMap" height="100%" @selectNode="onSelectNode" />
        </div>
        <div v-else-if="detailTab === 'dag'" class="empty" style="padding:10px">无 DAG 数据</div>

        <div v-else-if="detailTab === 'io'" class="panel-body scroll" style="flex:1">
          <div v-if="!ioSelected" class="empty" style="padding:10px">点击上方 DAG 节点查看输入/输出</div>
          <template v-else>
            <div class="io-section"><b>输入</b><pre class="hl-json" v-html="highlightJSON(ioSelected.input)"></pre></div>
            <div class="io-section"><b>输出</b><pre class="hl-json" v-html="highlightJSON(ioSelected.output)"></pre></div>
          </template>
        </div>
      </div>
      <div v-else class="split-bottom flex-center">
        <span class="empty" style="padding:20px">选择一条记录查看详情</span>
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

const loading = ref(true);
const sessions = ref([]);
const expanded = ref({});
const page = ref(1);
const pageSize = ref(15);
const sortBy = ref("");
const sortDir = ref("asc");

const selectedSess = ref("");
const turnList = ref([]);
const detailTab = ref("dag");
const detailTurnId = ref(0);
const ioSelected = ref(null);

const f = ref({
  timeRange: "", timeFrom: "", timeTo: "",
  workflow: "", node: "", tool: "", input: "", output: "", duration: "",
});

const DURATION_RANGES = [
  [0, 1000], [1001, 5000], [5001, 10000], [10001, Infinity],
];

function parseTimePreset(p) {
  const now = Date.now();
  const m = { m: 60000, h: 3600000, d: 86400000, w: 604800000, M: 2592000000 };
  for (const [k, v] of Object.entries(m)) {
    if (p.endsWith(k)) { const n = parseInt(p); return new Date(now - n * v); }
  }
  return null;
}

function matchRow(row) {
  const vals = [row.chat_id, row.workflow_name, row.turn_workflows?.join(" "),
    row.turn_nodes?.join(" "), row.turn_tools?.join(" "),
    row.turn_inputs?.join(" "), row.turn_outputs?.join(" ")];
  const text = vals.filter(Boolean).join(" ").toLowerCase();

  if (f.value.workflow && !text.includes(f.value.workflow.toLowerCase())) return false;
  if (f.value.node && !text.includes(f.value.node.toLowerCase())) return false;
  if (f.value.tool && !text.includes(f.value.tool.toLowerCase())) return false;
  if (f.value.input && !text.includes(f.value.input.toLowerCase())) return false;
  if (f.value.output && !text.includes(f.value.output.toLowerCase())) return false;

  if (f.value.timeRange) {
    const from = f.value.timeRange === "custom"
      ? (f.value.timeFrom ? new Date(f.value.timeFrom).getTime() : 0)
      : parseTimePreset(f.value.timeRange)?.getTime() || 0;
    const to = f.value.timeRange === "custom" && f.value.timeTo
      ? new Date(f.value.timeTo).getTime() : Infinity;
    const rowTime = new Date(row.first_at || 0).getTime();
    if (rowTime < from || rowTime > to) return false;
  }

  if (f.value.duration) {
    const [lo, hi] = DURATION_RANGES[parseInt(f.value.duration) - 1] || [0, Infinity];
    const d = row.total_duration_ms || 0;
    if (d < lo || d > hi) return false;
  }
  return true;
}

const filtered = computed(() => {
  let rows = sessions.value.filter(matchRow);
  if (sortBy.value) {
    rows = [...rows].sort((a, b) => {
      const va = a[sortBy.value] ?? "", vb = b[sortBy.value] ?? "";
      const cmp = typeof va === "number" ? va - vb : String(va).localeCompare(String(vb));
      return sortDir.value === "desc" ? -cmp : cmp;
    });
  }
  return rows;
});

const maxPage = computed(() => Math.max(1, Math.ceil(filtered.value.length / pageSize.value)));
const pageRows = computed(() => {
  const start = (page.value - 1) * pageSize.value;
  return filtered.value.slice(start, start + pageSize.value);
});

const detailTurn = computed(() => turnList.value.find(t => t.turn_id === detailTurnId.value) || null);

function toggleSort(col) {
  if (sortBy.value === col) { sortDir.value = sortDir.value === "asc" ? "desc" : "asc"; }
  else { sortBy.value = col; sortDir.value = "asc"; }
}
function sortIcon(col) {
  if (sortBy.value !== col) return "";
  return sortDir.value === "asc" ? "▲" : "▼";
}

function doSearch() { page.value = 1; }
function resetFilters() {
  f.value = { timeRange: "", timeFrom: "", timeTo: "", workflow: "", node: "", tool: "", input: "", output: "", duration: "" };
  page.value = 1;
}

async function load() {
  try {
    const d = await api.get("/sessions", { limit: 200 });
    sessions.value = (d.sessions || []).map(s => ({
      ...s, workflow_name: "", turn_workflows: [], turn_nodes: [], turn_tools: [], turn_inputs: [], turn_outputs: [],
    }));
    for (const s of sessions.value) {
      try {
        const td = await api.get(`/sessions/${s.chat_id}`);
        const wfs = [], nodes = [], tools = [], inputs = [], outputs = [];
        for (const t of (td.turns || [])) {
          if (t.workflow_name) wfs.push(t.workflow_name);
          try {
            const nd = await api.get(`/sessions/${s.chat_id}/turns/${t.turn_id}`);
            for (const n of (nd.nodes || [])) {
              if (n.node_name) nodes.push(n.node_name);
              if (n.tool_name) tools.push(n.tool_name);
              if (n.input_data) inputs.push(String(n.input_data).slice(0, 200));
              if (n.output_text) outputs.push(String(n.output_text).slice(0, 200));
            }
          } catch (_) {}
        }
        s.workflow_name = [...new Set(wfs)].join(", ");
        s.turn_workflows = wfs;
        s.turn_nodes = nodes;
        s.turn_tools = tools;
        s.turn_inputs = inputs;
        s.turn_outputs = outputs;
      } catch (_) {}
    }
  } catch (e) { toast("无法加载", "error"); }
  loading.value = false;
}

async function viewSession(row) {
  selectedSess.value = row.chat_id;
  try {
    const d = await api.get(`/sessions/${row.chat_id}`);
    const turnsWithNodes = [];
    for (const t of (d.turns || [])) {
      try {
        const td = await api.get(`/sessions/${row.chat_id}/turns/${t.turn_id}`);
        const wfName = td.run?.workflow_name || t.workflow_name;
        let wfNodes = [];
        try {
          const wf = await api.get(`/workflows/${wfName}`);
          wfNodes = (wf.nodes || []).map(n => ({ ...n, tool: n.tool || "" }));
        } catch (_) {}
        const nodeMap = {};
        const nodeData = {};
        for (const n of (td.nodes || [])) {
          const status = n.status === "ok" ? "executed" : "failed";
          nodeMap[n.node_name] = status;
          nodeData[n.node_name] = {
            status,
            tool: n.tool_name || "",
            duration_ms: n.duration_ms || 0,
            input: n.input_data || "",
            output: n.output_text || "",
          };
        }
        turnsWithNodes.push({
          ...t, nodes: td.nodes || [], _wfNodes: wfNodes, _nodeMap: nodeMap, _nodeData: nodeData,
        });
      } catch (_) {
        turnsWithNodes.push({ ...t, nodes: [], _wfNodes: [], _nodeMap: {}, _nodeData: {} });
      }
    }
    turnList.value = turnsWithNodes;
    detailTurnId.value = turnsWithNodes[0]?.turn_id || 0;
    detailTab.value = "dag";
    ioSelected.value = null;
  } catch (e) { toast("加载详情失败: " + e.message, "error"); }
}

function onSelectNode(data) {
  const turn = detailTurn.value;
  const nd = turn?._nodeData?.[data.name] || {};
  ioSelected.value = { input: nd.input || "(无)", output: nd.output || "(无)" };
  detailTab.value = "io";
}

function highlightJSON(text) {
  if (!text || text === "(无)") return '<span style="color:var(--text3)">(无)</span>';
  try { JSON.parse(text); } catch { return text; }
  const fmt = typeof text === "string" ? text : JSON.stringify(text, null, 2);
  return fmt
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/("(?:[^"\\]|\\.)*")\s*:/g, '<span class="jk">$1</span>:')
    .replace(/: ("(?:[^"\\]|\\.)*")/g, ': <span class="js">$1</span>')
    .replace(/: (\d+\.?\d*)/g, ': <span class="jn">$1</span>')
    .replace(/: (true|false|null)/g, ': <span class="jb">$1</span>');
}

onMounted(load);
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

.split-area { flex: 1; display: flex; flex-direction: column; min-height: 0; }
.split-top { flex: 1; min-height: 0; display: flex; flex-direction: column; overflow: hidden; }
.split-bottom { flex: 1; min-height: 0; border: 1px solid var(--border); border-radius: 8px; overflow: hidden; display: flex; flex-direction: column; }
.split-bottom.flex-center { align-items: center; justify-content: center; }

.table-wrap { flex: 1; overflow: auto; }
.data-table { width: 100%; border-collapse: collapse; font-size: 0.8rem; }
.data-table th, .data-table td { padding: 5px 8px; border-bottom: 1px solid var(--border); text-align: left; white-space: nowrap; }
.data-table th { background: var(--bg2); position: sticky; top: 0; z-index: 1; font-weight: 600; color: var(--text2); }
.data-table code { font-size: 0.72rem; }
.sortable { cursor: pointer; user-select: none; }
.sortable:hover { color: var(--accent); }
tr.selected { background: var(--bg3); }

.pager { display: flex; gap: 8px; align-items: center; justify-content: center; padding: 6px 0; font-size: 0.8rem; color: var(--text2); }

.panel-tabs { display: flex; gap: 0; background: var(--bg2); border-bottom: 1px solid var(--border); flex-shrink: 0; align-items: center; }
.tab { padding: 6px 16px; border: none; background: none; font-size: 0.82rem; cursor: pointer; color: var(--text2); border-bottom: 2px solid transparent; }
.tab.active { color: var(--accent); border-bottom-color: var(--accent); font-weight: 600; }
.tab.close { margin-left: auto; padding: 6px 12px; color: var(--text3); }
.panel-body { padding: 10px 14px; }
.panel-body.scroll { overflow: auto; }

.io-section { margin-bottom: 12px; }
.io-section b { font-size: 0.82rem; color: var(--text); }
.hl-json { font-size: 0.75rem; white-space: pre; margin: 4px 0 0; font-family: "Cascadia Code", "Fira Code", "Consolas", monospace; color: var(--text2); max-height: 200px; overflow: auto; }
.hl-json :deep(.jk) { color: #0550ae; }
.hl-json :deep(.js) { color: #0a3069; }
.hl-json :deep(.jn) { color: #0550ae; }
.hl-json :deep(.jb) { color: #cf222e; }
</style>
