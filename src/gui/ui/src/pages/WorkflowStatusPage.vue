<template>
  <div>
    <div v-if="loading" class="empty">加载中...</div>
    <div v-else-if="!workflows.length" class="empty">暂无已注册的工作流</div>
    <div v-for="wf in workflows" :key="wf.name" style="margin-bottom:24px">
      <h3 style="font-size:0.9rem;font-weight:600;margin-bottom:4px">
        {{ wf.name }}
        <span style="color:var(--text3);font-weight:400;font-size:0.78rem">— {{ wf.description }}</span>
      </h3>
      <div class="wf-meta">
        <span>集合: <code>{{ wf.collections?.join(", ") || "default" }}</code></span>
        <span>模式: <code>{{ wf.return_mode || "full" }}</code></span>
      </div>
      <div v-if="wf.nodes?.length" style="margin:8px 0">
        <DAGView :nodes="wf.nodes" :height="320" @selectNode="onSelect" />
      </div>
      <div v-if="wf.nodes?.length" class="node-grid">
        <button
          v-for="n in wf.nodes" :key="n.name"
          class="node-tag"
          :style="{ borderLeftColor: toolColor(n.tool || '') }"
          @click="openNodeConfig(wf.name, n)"
        >
          <b>{{ n.name }}</b>
          <span style="color:var(--text3);font-size:0.7rem">{{ n.tool || "-" }}</span>
        </button>
      </div>
    </div>

    <h3 style="font-size:0.85rem;font-weight:600;margin-top:16px">LLM</h3>
    <div v-if="llmDefault" style="font-size:0.8rem;color:var(--text2);margin:4px 0">
      默认: <code>{{ llmDefault }}</code>
    </div>

    <h3 style="font-size:0.85rem;font-weight:600;margin-top:12px">Embedding</h3>
    <div v-if="embedDefault" style="font-size:0.8rem;color:var(--text2);margin:4px 0">
      默认: <code>{{ embedDefault }}</code>
    </div>

    <div v-if="nodeConfig" class="modal-overlay" @click.self="nodeConfig=null">
      <div class="modal-card">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
          <b>{{ nodeConfig.name }}</b>
          <button class="btn" @click="nodeConfig=null">✕</button>
        </div>
        <pre class="cfg-json">{{ formatJSON(nodeConfig.config) }}</pre>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, inject } from "vue";
import { api } from "../api.js";
import DAGView from "../components/DAGView.vue";

let _cache = null;

const toast = inject("toast");
const workflows = ref([]);
const loading = ref(true);
const llmDefault = ref("");
const embedDefault = ref("");
const nodeConfig = ref(null);

const TOOL_COLORS = {
  llm: "#10b981", rag_search: "#3b82f6", router: "#8b5cf6", merge: "#f59e0b",
  db_query: "#06b6d4", api_call: "#ef4444", web_search: "#ec4899",
  extract_llm: "#6366f1", extract_regex: "#14b8a6", code: "#6b7280",
};
function toolColor(t) { return TOOL_COLORS[t] || "#6b7280"; }

async function load() {
  if (_cache) {
    workflows.value = _cache.workflows;
    llmDefault.value = _cache.llmDefault;
    embedDefault.value = _cache.embedDefault;
    loading.value = false;
    return;
  }
  try {
    const d = await api.get("/ready");
    const wl = await api.get("/workflows");
    const list = wl.workflows || [];

    const details = await Promise.all(
      list.map(w => api.get(`/workflows/${w.name}`).catch(() => null))
    );

    const wfs = details.filter(Boolean).map(d => ({
      ...d,
      nodes: (d.nodes || []).map(n => ({ ...n, tool: n.tool || "" })),
    }));

    _cache = {
      workflows: wfs,
      llmDefault: d.llm_default || "",
      embedDefault: d.embed_default || "",
    };

    workflows.value = _cache.workflows;
    llmDefault.value = _cache.llmDefault;
    embedDefault.value = _cache.embedDefault;
  } catch (e) {
    toast("加载失败: " + e.message, "error");
  }
  loading.value = false;
}

function onSelect(n) {
  for (const wf of workflows.value) {
    for (const node of wf.nodes) {
      if (node.name === n.name) {
        nodeConfig.value = {
          name: node.name,
          config: node.config || { tool: node.tool, name: node.name },
        };
        return;
      }
    }
  }
}
function openNodeConfig(wfName, node) {
  nodeConfig.value = {
    name: node.name,
    config: node.config || { tool: node.tool, name: node.name },
  };
}
function formatJSON(obj) {
  try { return JSON.stringify(obj, null, 2); } catch { return String(obj); }
}

onMounted(load);
</script>

<style scoped>
.empty { text-align: center; color: var(--text3); padding: 40px 0; font-size: 0.9rem; }
.wf-meta { font-size: 0.75rem; color: var(--text3); display: flex; gap: 16px; margin-bottom: 6px; }
.wf-meta code { font-size: 0.72rem; background: var(--bg2); padding: 1px 5px; border-radius: 3px; }
.node-grid { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px; }
.node-tag {
  padding: 4px 10px; border: 1px solid var(--border); border-radius: 6px;
  border-left: 3px solid #6b7280; background: var(--bg);
  font-size: 0.75rem; cursor: pointer; display: flex; gap: 6px; align-items: center;
}
.node-tag:hover { background: var(--bg2); }
.modal-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.35);
  display: flex; align-items: center; justify-content: center; z-index: 500;
}
.modal-card {
  background: var(--bg); border-radius: 10px; padding: 16px;
  max-width: 500px; width: 90%; max-height: 70vh; overflow-y: auto;
  box-shadow: var(--shadow-lg);
}
.cfg-json { font-size: 0.72rem; white-space: pre-wrap; background: var(--bg2); padding: 10px; border-radius: 6px; }
.btn { padding: 4px 10px; border: 1px solid var(--border); border-radius: 4px; background: var(--bg); cursor: pointer; }
</style>
