<template>
  <div style="display:flex;flex-direction:column;height:calc(100vh - 80px)">
    <div v-if="!sessions.length && !loading" class="empty">暂无聊天记录</div>
    <div v-else-if="!sessions.length" class="empty">加载中...</div>
    <template v-else>
      <div style="margin-bottom:8px;flex-shrink:0;display:flex;gap:8px;align-items:center">
        <select v-model="selectedSess" class="field" style="flex:1">
          <option v-for="s in sessions" :key="s.chat_id" :value="s.chat_id">
            {{ s.chat_id?.slice(0,16) }}... | {{ s.turn_count || 0 }}轮 | {{ ((s.total_duration_ms||0)/1000).toFixed(1) }}s
          </option>
        </select>
        <button class="btn" @click="exportCSV">导出 CSV</button>
      </div>

      <template v-if="currentSess">
        <div style="margin-bottom:8px;flex-shrink:0">
          <select v-model="selectedTurn" class="field" style="width:auto">
            <option v-for="t in (currentSess.turns || [])" :key="t.turn_id" :value="t.turn_id">
              Turn {{ t.turn_id }} | {{ t.workflow_name }} | {{ ((t.duration_ms||0)/1000).toFixed(2) }}s
            </option>
          </select>
        </div>

        <template v-if="currentTurn">
          <div class="split-area">
            <div class="split-top">
              <DAGView v-if="currentTurn._wfNodes?.length" :nodes="currentTurn._wfNodes" :nodeData="currentTurn._nodeMap" height="100%" @selectNode="onSelectNode" />
              <div v-else class="empty" style="padding:10px">无 DAG 数据</div>
            </div>
            <div class="split-bottom" v-if="nodePanel">
              <div class="panel-tabs">
                <button :class="['tab', { active: outTab === 'input' }]" @click="outTab='input'">输入</button>
                <button :class="['tab', { active: outTab === 'output' }]" @click="outTab='output'">输出</button>
                <button class="tab close" @click="nodePanel=null">✕</button>
              </div>
              <div class="panel-body scroll">
                <pre class="hl-json" v-html="highlightJSON(outTab === 'input' ? nodePanel.input : nodePanel.output)"></pre>
              </div>
            </div>
            <div v-else class="split-bottom flex-center">
              <span class="empty" style="padding:20px">点击 DAG 节点查看详情</span>
            </div>
          </div>
        </template>
      </template>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, inject } from "vue";
import { api } from "../api.js";
import DAGView from "../components/DAGView.vue";

const toast = inject("toast");
const sessions = ref([]);
const loading = ref(true);
const selectedSess = ref("");
const selectedTurn = ref(0);
const outTab = ref("input");
const nodePanel = ref(null);

const currentSess = computed(() => sessions.value.find(s => s.chat_id === selectedSess.value) || null);
const currentTurn = computed(() => {
  const turns = currentSess.value?.turns || [];
  return turns.find(t => t.turn_id === selectedTurn.value) || null;
});

async function load() {
  try {
    const d = await api.get("/sessions", { limit: 50 });
    sessions.value = (d.sessions || []).map(s => ({ ...s, turns: null, _loading: false }));
    if (sessions.value.length) selectedSess.value = sessions.value[0].chat_id;
  } catch (e) { toast("无法加载", "error"); }
  loading.value = false;
}

async function loadTurns(sess) {
  if (sess.turns) return;
  sess._loading = true;
  try {
    const d = await api.get(`/sessions/${sess.chat_id}`);
    const turnsWithNodes = [];
    for (const t of (d.turns || [])) {
      try {
        const td = await api.get(`/sessions/${sess.chat_id}/turns/${t.turn_id}`);
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
    sess.turns = turnsWithNodes;
    if (turnsWithNodes.length) {
      selectedTurn.value = turnsWithNodes[0].turn_id;
    }
  } catch (e) { toast("加载轮次失败: " + e.message, "error"); }
  sess._loading = false;
}

function onSelectNode(data) {
  const turn = currentTurn.value;
  const nd = turn?._nodeData?.[data.name] || {};
  nodePanel.value = {
    name: data.name,
    input: nd.input || "(无)",
    output: nd.output || "(无)",
  };
  outTab.value = "output";
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

function exportCSV() {
  let csv = "chat_id,turns,total_duration_ms,first_at,last_at\n";
  for (const s of sessions.value) {
    csv += `"${s.chat_id}","${s.turn_count||0}","${s.total_duration_ms||""}","${s.first_at||""}","${s.last_at||""}"\n`;
  }
  const blob = new Blob([csv], { type: "text/csv" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "sessions.csv";
  a.click();
  URL.revokeObjectURL(a.href);
}

const loadTurnsWatcher = computed(() => {
  if (currentSess.value) loadTurns(currentSess.value);
  return selectedSess.value;
});

onMounted(load);
</script>

<style scoped>
.empty { text-align: center; color: var(--text3); padding: 40px 0; font-size: 0.9rem; }
.field { padding: 5px 8px; border: 1px solid var(--border); border-radius: 6px; background: var(--bg); font-size: 0.82rem; }
.btn { padding: 5px 14px; border: 1px solid var(--border); border-radius: 6px; background: var(--bg); font-size: 0.82rem; cursor: pointer; color: var(--text); }

.split-area { flex: 1; display: flex; flex-direction: column; min-height: 0; }
.split-top { flex: 1; min-height: 0; margin-bottom: 8px; }
.split-bottom { flex: 1; min-height: 0; border: 1px solid var(--border); border-radius: 8px; overflow: hidden; display: flex; flex-direction: column; }
.split-bottom.flex-center { align-items: center; justify-content: center; }

.panel-tabs { display: flex; gap: 0; background: var(--bg2); border-bottom: 1px solid var(--border); flex-shrink: 0; }
.tab { padding: 6px 16px; border: none; background: none; font-size: 0.82rem; cursor: pointer; color: var(--text2); border-bottom: 2px solid transparent; }
.tab.active { color: var(--accent); border-bottom-color: var(--accent); font-weight: 600; }
.tab.close { margin-left: auto; padding: 6px 12px; color: var(--text3); }
.panel-body { padding: 10px 14px; flex: 1; }
.panel-body.scroll { overflow: auto; }

.hl-json { font-size: 0.75rem; white-space: pre; margin: 0; font-family: "Cascadia Code", "Fira Code", "Consolas", monospace; color: var(--text2); }
.hl-json :deep(.jk) { color: #0550ae; }
.hl-json :deep(.js) { color: #0a3069; }
.hl-json :deep(.jn) { color: #0550ae; }
.hl-json :deep(.jb) { color: #cf222e; }
</style>
