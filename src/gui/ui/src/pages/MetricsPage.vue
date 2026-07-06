<template>
  <div>
    <div v-if="!sessions.length && !loading" class="empty">暂无运行记录</div>

    <div v-if="sessions.length" style="margin-bottom:10px">
      <button class="btn" @click="exportSessionsCSV">CSV 导出</button>
    </div>

    <div v-for="sess in sessions" :key="sess.chat_id" class="sess-item">
      <details @toggle="onToggle(sess, $event)">
        <summary class="sess-summary">
          <code>{{ sess.chat_id?.slice(0,16) }}...</code>
          <span>{{ sess.turn_count || 0 }}轮</span>
          <span>{{ ((sess.total_duration_ms||0)/1000).toFixed(1) }}s</span>
          <span style="color:var(--text3);font-size:0.7rem">{{ sess.last_at }}</span>
        </summary>
        <div v-if="sess.turns" style="padding:6px 0">
          <div v-if="sess._loading">加载中...</div>
          <div v-for="turn in (sess.turns || [])" :key="turn.turn_id" style="margin-bottom:12px">
            <div class="turn-header">
              Turn {{ turn.turn_id }} | {{ turn.workflow_name }} | {{ turn.node_count }}节点 | {{ ((turn.duration_ms||0)/1000).toFixed(2) }}s
            </div>
            <div v-if="turn.nodes && turn._wfNodes" style="margin-top:4px">
              <DAGView :nodes="turn._wfNodes" :nodeData="turn._nodeMap" :height="240" />
            </div>
            <details v-if="turn.nodes?.length" style="margin-top:4px">
              <summary style="cursor:pointer;font-size:0.78rem;color:var(--text2)">详情 ({{ turn.nodes.length }}节点)</summary>
              <div v-for="nd in turn.nodes" :key="nd.node_name" class="node-detail">
                <div class="node-hd">
                  <span :class="['dot', nd.status==='ok'?'ok':'fail']"></span>
                  <b>{{ nd.node_name }}</b>
                  <code>{{ nd.tool_name || "-" }}</code>
                  <span style="color:var(--text3);font-size:0.7rem">{{ (nd.duration_ms||0).toFixed(0) }}ms</span>
                </div>
                <div v-if="nd.input_data" class="nd-sec"><span>输入</span><pre>{{ nd.input_data?.slice(0,300) }}</pre></div>
                <div v-if="nd.output_text" class="nd-sec"><span>输出</span><pre>{{ nd.output_text?.slice(0,300) }}</pre></div>
                <div v-if="nd.error_message" class="nd-sec err">{{ nd.error_message }}</div>
              </div>
            </details>
          </div>
        </div>
      </details>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, inject } from "vue";
import { api } from "../api.js";
import DAGView from "../components/DAGView.vue";

const toast = inject("toast");
const sessions = ref([]);
const loading = ref(true);

async function load() {
  try {
    const d = await api.get("/sessions", { limit: 50 });
    sessions.value = (d.sessions || []).map(s => ({
      ...s,
      turns: null,
      _loading: false,
    }));
  } catch (e) { toast("无法加载会话", "error"); }
  loading.value = false;
}

async function onToggle(sess, evt) {
  if (!evt.target.open || sess.turns) return;
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
        for (const n of (td.nodes || [])) {
          nodeMap[n.node_name] = {
            status: n.status === "ok" ? "executed" : "failed",
            tool: n.tool_name || "",
            duration_ms: n.duration_ms || 0,
          };
        }

        turnsWithNodes.push({
          ...t,
          nodes: td.nodes || [],
          _wfNodes: wfNodes,
          _nodeMap: nodeMap,
        });
      } catch (_) {
        turnsWithNodes.push({ ...t, nodes: [], _wfNodes: [], _nodeMap: {} });
      }
    }
    sess.turns = turnsWithNodes;
  } catch (e) { toast("加载轮次失败: " + e.message, "error"); }
  sess._loading = false;
}

function exportSessionsCSV() {
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
.btn { padding: 5px 14px; border: 1px solid var(--border); border-radius: 6px; background: var(--bg); font-size: 0.82rem; cursor: pointer; }
.sess-item { margin-bottom: 6px; }
.sess-summary {
  cursor: pointer; padding: 6px 8px; border-radius: 4px; background: var(--bg2);
  display: flex; gap: 12px; align-items: center; font-size: 0.8rem;
}
.sess-summary:hover { background: var(--bg3); }
.sess-summary code { font-size: 0.72rem; }
.turn-header { font-size: 0.78rem; font-weight: 600; color: var(--text); padding: 4px 8px; background: var(--bg2); border-radius: 4px; margin: 4px 0; }
.node-detail { border-left: 2px solid var(--border); margin: 4px 0 4px 8px; padding: 4px 8px; }
.node-hd { display: flex; gap: 8px; align-items: center; font-size: 0.78rem; }
.node-hd code { font-size: 0.7rem; background: var(--bg2); padding: 1px 5px; border-radius: 3px; }
.dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.dot.ok { background: #4caf50; }
.dot.fail { background: #f44336; }
.nd-sec { margin: 3px 0; font-size: 0.72rem; }
.nd-sec span { color: var(--text3); font-weight: 600; }
.nd-sec pre { font-size: 0.7rem; white-space: pre-wrap; background: var(--bg2); padding: 4px 8px; border-radius: 4px; margin: 2px 0; max-height: 120px; overflow-y: auto; }
.nd-sec.err { color: #f44336; font-size: 0.72rem; }
</style>
