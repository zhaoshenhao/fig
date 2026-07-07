<template>
  <div>
    <div v-if="loading" class="empty">加载中...</div>
    <div v-else-if="!workflows.length" class="empty">暂无已注册的工作流</div>
    <template v-else>
      <div class="row" style="margin-bottom:12px">
        <select v-model="selected" class="field" style="flex:1">
          <option v-for="wf in workflows" :key="wf.name" :value="wf.name">{{ wf.name }} — {{ wf.description }}</option>
        </select>
      </div>

      <template v-if="currentWf">
        <div class="wf-meta">
          <span>集合: <code>{{ currentWf.collections?.join(", ") || "default" }}</code></span>
          <span>模式: <code>{{ currentWf.return_mode || "full" }}</code></span>
        </div>
        <div v-if="currentWf.nodes?.length" style="margin:8px 0">
          <DAGView :nodes="currentWf.nodes" :height="500" @selectNode="onSelectNode" />
        </div>

        <div v-if="nodeInfo" class="node-panel">
          <div class="panel-tabs">
            <button :class="['tab', { active: tab === 'status' }]" @click="tab='status'">状态</button>
            <button :class="['tab', { active: tab === 'config' }]" @click="tab='config'">配置</button>
            <button class="tab close" @click="nodeInfo=null">✕</button>
          </div>
          <div v-if="tab === 'status'" class="panel-body">
            <div class="prop"><span>名称</span> {{ nodeInfo.name }}</div>
            <div class="prop"><span>工具</span> {{ nodeInfo.tool || "-" }}</div>
            <div class="prop" v-if="nodeInfo.dur !== undefined"><span>耗时</span> {{ nodeInfo.dur }}ms</div>
            <div class="prop"><span>状态</span> {{ nodeInfo.status || "-" }}</div>
            <div class="prop" v-if="nodeInfo.next?.length"><span>后继</span> {{ nodeInfo.next.join(", ") }}</div>
          </div>
          <div v-else class="panel-body">
            <pre class="cfg-json">{{ formatJSON(nodeInfo.config) }}</pre>
          </div>
        </div>
      </template>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, inject } from "vue";
import { api } from "../api.js";
import DAGView from "../components/DAGView.vue";

let _cache = null;

const toast = inject("toast");
const workflows = ref([]);
const loading = ref(true);
const selected = ref("");
const tab = ref("status");
const nodeInfo = ref(null);

const currentWf = computed(() => workflows.value.find(w => w.name === selected.value) || null);

async function load() {
  if (_cache) {
    workflows.value = _cache;
    if (!selected.value && _cache.length) selected.value = _cache[0].name;
    loading.value = false;
    return;
  }
  try {
    const wl = await api.get("/workflows");
    const list = wl.workflows || [];
    const details = await Promise.all(
      list.map(w => api.get(`/workflows/${w.name}`).catch(() => null))
    );
    _cache = details.filter(Boolean).map(d => ({
      ...d,
      nodes: (d.nodes || []).map(n => ({ ...n, tool: n.tool || "" })),
    }));
    workflows.value = _cache;
    if (_cache.length) selected.value = _cache[0].name;
  } catch (e) {
    toast("加载失败: " + e.message, "error");
  }
  loading.value = false;
}

function onSelectNode(data) {
  const node = currentWf.value?.nodes?.find(n => n.name === data.name);
  nodeInfo.value = {
    name: data.name,
    tool: data.tool || (node?.tool) || "",
    dur: data.dur,
    status: data.status || "pending",
    next: data.next || [],
    config: node?.config || {},
  };
  tab.value = "status";
}

function formatJSON(obj) {
  try { return JSON.stringify(obj, null, 2); } catch { return String(obj); }
}

onMounted(load);
</script>

<style scoped>
.empty { text-align: center; color: var(--text3); padding: 40px 0; font-size: 0.9rem; }
.row { display: flex; gap: 8px; align-items: center; }
.field { padding: 5px 8px; border: 1px solid var(--border); border-radius: 6px; background: var(--bg); font-size: 0.82rem; }
.wf-meta { font-size: 0.75rem; color: var(--text3); display: flex; gap: 16px; margin-bottom: 6px; }
.wf-meta code { font-size: 0.72rem; background: var(--bg2); padding: 1px 5px; border-radius: 3px; }

.node-panel {
  margin-top: 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
}
.panel-tabs {
  display: flex;
  gap: 0;
  background: var(--bg2);
  border-bottom: 1px solid var(--border);
}
.tab {
  padding: 6px 16px;
  border: none;
  background: none;
  font-size: 0.82rem;
  cursor: pointer;
  color: var(--text2);
  border-bottom: 2px solid transparent;
}
.tab.active {
  color: var(--accent);
  border-bottom-color: var(--accent);
  font-weight: 600;
}
.tab.close {
  margin-left: auto;
  padding: 6px 12px;
  color: var(--text3);
}
.panel-body {
  padding: 10px 14px;
  max-height: 300px;
  overflow-y: auto;
}
.prop { font-size: 0.8rem; margin-bottom: 4px; color: var(--text); }
.prop span { color: var(--text3); margin-right: 8px; font-weight: 600; }
.cfg-json { font-size: 0.75rem; white-space: pre-wrap; color: var(--text2); }
</style>
