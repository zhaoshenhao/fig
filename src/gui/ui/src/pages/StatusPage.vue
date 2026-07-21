<template>
  <div style="display:flex;flex-direction:column;height:calc(100vh - 80px)">
    <div class="row" style="flex-shrink:0;margin-bottom:10px">
      <div :class="['overall', data?.status]">
        <span class="dot"></span>
        {{ overallLabel }}
      </div>
      <label class="check">
        <input type="checkbox" v-model="auto" @change="toggleAuto" /> 自动刷新 (10s)
      </label>
      <button class="btn" @click="load" :disabled="loading">{{ loading ? "刷新中..." : "刷新" }}</button>
      <span v-if="lastAt" class="muted">更新于 {{ lastAt }}</span>
    </div>

    <div class="scroll">
      <div v-if="err" class="empty">加载失败：{{ err }}</div>
      <template v-else-if="data">
        <div class="cards">
          <div v-for="c in componentList" :key="c.key" :class="['card', c.status]">
            <div class="card-hd">
              <span class="dot"></span>
              <b>{{ c.label }}</b>
              <span class="lat" v-if="c.latency_ms !== undefined">{{ c.latency_ms }}ms</span>
            </div>
            <div class="card-detail">{{ c.detail || "-" }}</div>
          </div>
        </div>

        <h4 class="sec">进程信息</h4>
        <div class="proc">
          <div class="prop"><span>版本</span>{{ data.process.version }}</div>
          <div class="prop"><span>Python</span>{{ data.process.python }}</div>
          <div class="prop"><span>运行时长</span>{{ uptime }}</div>
          <div class="prop"><span>内存</span>{{ data.process.memory_mb || '-' }} MB</div>
          <div class="prop"><span>工作流数</span>{{ data.process.workflow_count }}</div>
          <div class="prop"><span>工作流</span>{{ (data.process.workflows || []).join(", ") || "-" }}</div>
        </div>
      </template>
      <div v-else class="empty">加载中...</div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, inject } from "vue";
import { api } from "../api.js";

const toast = inject("toast");
const data = ref(null);
const err = ref("");
const loading = ref(false);
const lastAt = ref("");
const auto = ref(false);
let _timer = 0;

const LABELS = {
  qdrant: "Qdrant 向量库",
  llm: "LLM",
  embedding: "Embedding",
  metrics_store: "Metrics 存储",
  session_store: "会话存储",
  db_pools: "DB 连接池",
};

const overallLabel = computed(() => {
  if (!data.value) return "未知";
  return data.value.status === "ok" ? "系统正常" : "存在异常";
});

const componentList = computed(() => {
  if (!data.value?.components) return [];
  return Object.entries(data.value.components).map(([key, v]) => ({
    key, label: LABELS[key] || key, ...v,
  }));
});

const uptime = computed(() => {
  const s = data.value?.process?.uptime_seconds || 0;
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = Math.floor(s % 60);
  return `${h}h ${m}m ${sec}s`;
});

async function load() {
  loading.value = true;
  err.value = "";
  try {
    data.value = await api.get("/status");
    lastAt.value = new Date().toLocaleTimeString("zh-CN", { hour12: false });
  } catch (e) {
    err.value = e.message;
    toast("状态加载失败: " + e.message, "error");
  }
  loading.value = false;
}

function toggleAuto() {
  clearInterval(_timer);
  if (auto.value) _timer = setInterval(load, 10000);
}

onMounted(load);
onUnmounted(() => clearInterval(_timer));
</script>

<style scoped>
.row { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
.check { font-size: 0.8rem; display: flex; align-items: center; gap: 4px; cursor: pointer; color: var(--text2); }
.muted { font-size: 0.75rem; color: var(--text3); }
.btn { padding: 5px 14px; border: 1px solid var(--border); border-radius: 6px; background: var(--bg); font-size: 0.82rem; cursor: pointer; color: var(--text); }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.scroll { flex: 1; overflow: auto; min-height: 0; }
.empty { text-align: center; color: var(--text3); padding: 40px 0; font-size: 0.9rem; }

.overall { display: flex; align-items: center; gap: 8px; font-weight: 600; font-size: 0.95rem; padding: 6px 14px; border-radius: 8px; background: var(--bg2); }
.overall.ok { color: var(--success); }
.overall.degraded { color: var(--danger); }
.overall .dot { width: 10px; height: 10px; border-radius: 50%; background: currentColor; }

.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 10px; }
.card { border: 1px solid var(--border); border-radius: 8px; padding: 10px 12px; background: var(--bg); border-left: 4px solid var(--text3); }
.card.ok { border-left-color: var(--success); }
.card.error { border-left-color: var(--danger); }
.card-hd { display: flex; align-items: center; gap: 8px; font-size: 0.88rem; }
.card-hd .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--text3); }
.card.ok .dot { background: var(--success); }
.card.error .dot { background: var(--danger); }
.card-hd .lat { margin-left: auto; font-size: 0.72rem; color: var(--text3); }
.card-detail { font-size: 0.75rem; color: var(--text2); margin-top: 6px; word-break: break-word; }

.sec { margin: 16px 0 8px; font-size: 0.9rem; color: var(--text2); }
.proc { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 6px 16px; }
.prop { font-size: 0.82rem; color: var(--text); display: flex; gap: 8px; }
.prop span:first-child { color: var(--text3); font-weight: 600; min-width: 72px; }
</style>
