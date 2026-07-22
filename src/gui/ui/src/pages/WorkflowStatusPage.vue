<template>
  <div style="display:flex;flex-direction:column;height:calc(100vh - 80px)">
    <div v-if="loading" class="empty">加载中...</div>
    <div v-else-if="!workflows.length" class="empty">暂无已注册的工作流</div>
    <template v-else>
      <div class="row" style="margin-bottom:8px;flex-shrink:0">
        <select v-model="selected" class="field" style="flex:1">
          <option v-for="wf in workflows" :key="wf.name" :value="wf.name">{{ wf.name }} — {{ wf.description }}</option>
        </select>
        <button class="btn" @click="refresh" :disabled="loading">刷新</button>
        <button class="btn" @click="reload" :disabled="reloading">{{ reloading ? "重载中..." : "热重载" }}</button>
      </div>

      <template v-if="currentWf">
        <div class="wf-meta">
          <span>集合: <code>{{ currentWf.collections?.join(", ") || "default" }}</code></span>
          <span>模式: <code>{{ currentWf.return_mode || "full" }}</code></span>
        </div>

        <div class="split-area">
          <div class="split-top">
            <DAGView v-if="currentWf.nodes?.length" :nodes="currentWf.nodes" height="100%" @selectNode="onSelectNode" />
          </div>
          <div class="split-bottom">
            <div class="panel-tabs">
              <button :class="['tab', { active: tab === 'status' }]" @click="tab='status'">状态</button>
              <button :class="['tab', { active: tab === 'config' }]" @click="tab='config'">配置</button>
              <button :class="['tab', { active: tab === 'yaml' }]" @click="tab='yaml'">工作流配置</button>
            </div>
            <div v-if="tab === 'status'" class="panel-body">
              <div v-if="!nodeInfo" class="empty" style="padding:20px">点击 DAG 节点查看详情</div>
              <template v-else>
                <div class="prop"><span>名称</span> {{ nodeInfo.name }}</div>
                <div class="prop"><span>工具</span> {{ nodeInfo.tool || "-" }}</div>
                <div class="prop" v-if="nodeInfo.dur !== undefined"><span>耗时</span> {{ nodeInfo.dur }}ms</div>
                <div class="prop"><span>状态</span> {{ nodeInfo.status || "-" }}</div>
                <div class="prop" v-if="nodeInfo.next?.length"><span>后继</span> {{ nodeInfo.next.join(", ") }}</div>
              </template>
            </div>
            <div v-else-if="tab === 'config'" class="panel-body scroll">
              <div v-if="!nodeInfo" class="empty" style="padding:20px">点击 DAG 节点查看详情</div>
              <pre v-else class="cfg-json" v-html="highlighted"></pre>
            </div>
            <div v-else-if="tab === 'yaml'" class="panel-body scroll">
              <div v-if="yamlLoading" class="empty" style="padding:20px">加载中...</div>
              <pre v-else class="yaml-display" v-html="highlightedYaml"></pre>
            </div>
          </div>
        </div>
      </template>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, inject } from "vue";
import { api } from "../api.js";
import DAGView from "../components/DAGView.vue";

let _cache = null;

const toast = inject("toast");
const workflows = ref([]);
const loading = ref(true);
const reloading = ref(false);
const selected = ref("");
const tab = ref("status");
const nodeInfo = ref(null);
const yamlContent = ref("");
const yamlLoading = ref(false);

const currentWf = computed(() => workflows.value.find(w => w.name === selected.value) || null);

const highlighted = computed(() => {
  if (!nodeInfo.value?.config) return "";
  const json = JSON.stringify(nodeInfo.value.config, null, 2);
  return json
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/("(?:[^"\\]|\\.)*")\s*:/g, '<span class="jk">$1</span>:')
    .replace(/: ("(?:[^"\\]|\\.)*")/g, ': <span class="js">$1</span>')
    .replace(/: (\d+\.?\d*)/g, ': <span class="jn">$1</span>')
    .replace(/: (true|false|null)/g, ': <span class="jb">$1</span>');
});
const highlightedYaml = computed(() => {
  if (!yamlContent.value) return "";
  return yamlContent.value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/("(?:[^"\\]|\\.)*")/g, '<span class="ys">$1</span>')
    .replace(/('(?:[^'\\]|\\.)*')/g, '<span class="ys">$1</span>')
    .replace(/(\s*#.*)$/gm, '<span class="yc">$1</span>')
    .replace(/^(\s*)([\w][\w_.-]*?)(\s*:)/gm, '$1<span class="yk">$2</span>$3')
    .replace(/\b(\d+\.?\d*)\b/g, '<span class="yn">$1</span>')
    .replace(/\b(true|false|yes|no|on|off|null)\b/g, '<span class="yb">$1</span>');
});

async function loadYaml() {
  if (!selected.value) return;
  yamlLoading.value = true;
  try {
    const resp = await api.get(`/api/v1/workflows/${selected.value}/yaml`);
    yamlContent.value = resp.content || "";
  } catch (e) {
    yamlContent.value = "";
  }
  yamlLoading.value = false;
}

async function load() {
  if (_cache) {
    workflows.value = _cache;
    if (!selected.value && _cache.length) selected.value = _cache[0].name;
    loading.value = false;
    return;
  }
  try {
    const wl = await api.get("/api/v1/workflows");
    const list = wl.workflows || [];
    const details = await Promise.all(
      list.map(w => api.get(`/api/v1/workflows/${w.name}`).catch(() => null))
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
  if (node?.config) tab.value = "config";
  else tab.value = "status";
}

onMounted(load);
watch(selected, () => { if (selected.value) loadYaml(); });

async function refresh() {
  _cache = null;
  loading.value = true;
  await load();
}

async function reload() {
  if (!window.confirm("确定要热重载配置？重载期间其他请求将短暂返回 503。")) return;
  reloading.value = true;
  try {
    await api.post("/reload", {});
    toast("配置已热重载", "success");
  } catch (e) {
    toast("重载失败: " + e.message, "error");
  }
  // 重载后刷新页面数据
  _cache = null;
  loading.value = true;
  await load();
  reloading.value = false;
}

</script>

<style scoped>
.empty { text-align: center; color: var(--text3); padding: 40px 0; font-size: 0.9rem; }
.row { display: flex; gap: 8px; align-items: center; }
.field { padding: 5px 8px; border: 1px solid var(--border); border-radius: 6px; background: var(--bg); font-size: 0.82rem; }
.btn { padding: 5px 14px; border: 1px solid var(--border); border-radius: 6px; background: var(--bg); font-size: 0.82rem; cursor: pointer; color: var(--text); }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.wf-meta { font-size: 0.75rem; color: var(--text3); display: flex; gap: 16px; margin-bottom: 6px; }
.wf-meta code { font-size: 0.72rem; background: var(--bg2); padding: 1px 5px; border-radius: 3px; }

.split-area { flex: 1; display: flex; flex-direction: column; min-height: 0; }
.split-top { flex: 1; min-height: 0; margin-bottom: 8px; }
.split-bottom { flex: 1; min-height: 0; border: 1px solid var(--border); border-radius: 8px; overflow: hidden; display: flex; flex-direction: column; }

.panel-tabs {
  display: flex; gap: 0; background: var(--bg2); border-bottom: 1px solid var(--border); flex-shrink: 0;
}
.tab {
  padding: 6px 16px; border: none; background: none; font-size: 0.82rem; cursor: pointer;
  color: var(--text2); border-bottom: 2px solid transparent;
}
.tab.active { color: var(--accent); border-bottom-color: var(--accent); font-weight: 600; }

.panel-body { padding: 10px 14px; overflow-y: auto; flex: 1; }
.panel-body.scroll { overflow: auto; }
.prop { font-size: 0.8rem; margin-bottom: 4px; color: var(--text); }
.prop span { color: var(--text3); margin-right: 8px; font-weight: 600; }

.cfg-json {
  font-size: 0.75rem; white-space: pre; margin: 0; font-family: "Cascadia Code", "Fira Code", "Consolas", monospace;
  color: var(--text2);
}
.cfg-json :deep(.jk) { color: var(--hl-key); }
.cfg-json :deep(.js) { color: var(--hl-string); }
.cfg-json :deep(.jn) { color: var(--hl-number); }
.cfg-json :deep(.jb) { color: var(--hl-bool); }

.yaml-display {
  font-size: 0.75rem; white-space: pre; margin: 0;
  font-family: "Cascadia Code", "Fira Code", "Consolas", monospace;
  color: var(--text2);
}
.yaml-display :deep(.yc) { color: var(--hl-comment); font-style: italic; }
.yaml-display :deep(.yk) { color: var(--hl-key); }
.yaml-display :deep(.ys) { color: var(--hl-string); }
.yaml-display :deep(.yn) { color: var(--hl-number); }
.yaml-display :deep(.yb) { color: var(--hl-bool); }
</style>
