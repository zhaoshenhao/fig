<template>
  <div style="display:flex;flex-direction:column;height:calc(100vh - 80px)">
    <div v-if="!sessions.length && !loading" class="empty">暂无聊天记录</div>
    <div v-else-if="!sessions.length" class="empty">加载中...</div>
    <template v-else>
      <div style="margin-bottom:8px;flex-shrink:0">
        <button class="btn" @click="exportCSV">导出 CSV</button>
      </div>

      <div class="split-area">
        <div class="split-top sess-list">
          <div v-for="sess in sessions" :key="sess.chat_id" class="sess-item">
            <details @toggle="e => { if (e.target.open) loadTurns(sess); }">
              <summary class="sess-summary">
                <code>{{ sess.chat_id?.slice(0,16) }}...</code>
                <span>{{ sess.turn_count || 0 }}轮</span>
                <span>{{ ((sess.total_duration_ms||0)/1000).toFixed(1) }}s</span>
                <span class="sess-date">{{ sess.last_at }}</span>
              </summary>
              <div v-if="sess._loading" class="empty" style="padding:10px">加载中...</div>
              <div v-else>
                <div v-for="turn in (sess.turns || [])" :key="turn.turn_id" style="margin-bottom:8px">
                  <div class="turn-hd" @click="selectTurn(turn)">
                    Turn {{ turn.turn_id }} | {{ turn.workflow_name }} | {{ turn.node_count }}节点 | {{ ((turn.duration_ms||0)/1000).toFixed(2) }}s
                  </div>
                  <div v-if="turn._wfNodes?.length" style="margin:4px 0;height:240px">
                    <DAGView :nodes="turn._wfNodes" :nodeData="turn._nodeMap" :height="240" @selectNode="onSelectNode" />
                  </div>
                </div>
              </div>
            </details>
          </div>
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
  </div>
</template>

<script setup>
import { ref, onMounted, inject } from "vue";
import { api } from "../api.js";
import DAGView from "../components/DAGView.vue";

const toast = inject("toast");
const sessions = ref([]);
const loading = ref(true);
const outTab = ref("input");
const nodePanel = ref(null);

async function load() {
  try {
    const d = await api.get("/sessions", { limit: 50 });
    sessions.value = (d.sessions || []).map(s => ({ ...s, turns: null, _loading: false }));
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
  } catch (e) { toast("加载轮次失败: " + e.message, "error"); }
  sess._loading = false;
}

function selectTurn(turn) { /* placeholder */ }

function onSelectNode(data) {
  const nd = findNodeData(data.name);
  nodePanel.value = {
    name: data.name,
    input: nd.input || "(无)",
    output: nd.output || "(无)",
  };
  outTab.value = nd.output ? "output" : "input";
}

function findNodeData(name) {
  for (const sess of sessions.value) {
    for (const turn of (sess.turns || [])) {
      const nd = turn._nodeData?.[name];
      if (nd) return nd;
    }
  }
  return {};
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

onMounted(load);
</script>

<style scoped>
.empty { text-align: center; color: var(--text3); padding: 40px 0; font-size: 0.9rem; }
.btn { padding: 5px 14px; border: 1px solid var(--border); border-radius: 6px; background: var(--bg); font-size: 0.82rem; cursor: pointer; color: var(--text); }

.split-area { flex: 1; display: flex; flex-direction: column; min-height: 0; }
.split-top { flex: 1; min-height: 0; overflow-y: auto; margin-bottom: 8px; }
.split-bottom { flex: 1; min-height: 0; border: 1px solid var(--border); border-radius: 8px; overflow: hidden; display: flex; flex-direction: column; }
.split-bottom.flex-center { align-items: center; justify-content: center; }

.sess-item { margin-bottom: 4px; }
.sess-summary {
  cursor: pointer; padding: 6px 8px; border-radius: 4px; background: var(--bg2);
  display: flex; gap: 12px; align-items: center; font-size: 0.8rem;
}
.sess-summary:hover { background: var(--bg3); }
.sess-summary code { font-size: 0.72rem; }
.sess-date { color: var(--text3); font-size: 0.7rem; }
.turn-hd {
  font-size: 0.78rem; font-weight: 600; padding: 4px 8px; background: var(--bg2);
  border-radius: 4px; margin: 6px 0 4px; cursor: default;
}

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
