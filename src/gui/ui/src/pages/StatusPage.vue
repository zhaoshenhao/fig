<template>
  <div class="status-page">
    <div class="top-bar">
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

    <div class="content">
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
          <div class="prop"><span class="prop-label">版本</span><span class="prop-value">{{ data.process.version }}</span></div>
          <div class="prop"><span class="prop-label">Python</span><span class="prop-value">{{ data.process.python }}</span></div>
          <div class="prop"><span class="prop-label">运行时长</span><span class="prop-value">{{ uptime }}</span></div>
          <div class="prop"><span class="prop-label">内存</span><span class="prop-value">{{ memDisplay }}</span></div>
          <div class="prop"><span class="prop-label">工作流数</span><span class="prop-value">{{ data.process.workflow_count }}</span></div>
          <div class="prop"><span class="prop-label">工作流</span><span class="prop-value">{{ workflowList }}</span></div>
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
  llm: "LLM 大模型",
  embedding: "Embedding 向量化",
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

const memDisplay = computed(() => {
  const m = data.value?.process?.memory_mb;
  if (!m || m <= 0) return "-";
  return m < 1024 ? `${m} MB` : `${(m / 1024).toFixed(1)} GB`;
});

const workflowList = computed(() => {
  const w = data.value?.process?.workflows;
  return w?.length ? w.join(", ") : "-";
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
.status-page { display: flex; flex-direction: column; height: calc(100vh - 80px); }
.top-bar { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; flex-shrink: 0; padding: 8px 0; margin-bottom: 12px; border-bottom: 1px solid var(--border); }
.check { font-size: 0.8rem; display: flex; align-items: center; gap: 4px; cursor: pointer; color: var(--text2); }
.muted { font-size: 0.75rem; color: var(--text3); margin-left: auto; }
.btn { padding: 6px 16px; border: 1px solid var(--border); border-radius: 6px; background: var(--bg); font-size: 0.82rem; cursor: pointer; color: var(--text); transition: opacity 0.2s; }
.btn:hover { background: var(--bg3); }
.btn:disabled { opacity: 0.4; cursor: not-allowed; }
.content { flex: 1; overflow: auto; min-height: 0; }
.empty { text-align: center; color: var(--text3); padding: 60px 0; font-size: 0.9rem; }

.overall { display: inline-flex; align-items: center; gap: 8px; font-weight: 600; font-size: 0.95rem; padding: 6px 16px; border-radius: 8px; background: var(--bg2); }
.overall.ok { color: var(--success); }
.overall.degraded { color: var(--danger); }
.overall .dot { width: 10px; height: 10px; border-radius: 50%; background: currentColor; }

.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; margin-bottom: 16px; }
.card { border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px; background: var(--bg); border-left: 4px solid var(--text3); transition: box-shadow 0.2s; }
.card:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
.card.ok { border-left-color: var(--success); }
.card.error { border-left-color: var(--danger); }
.card-hd { display: flex; align-items: center; gap: 10px; font-size: 0.9rem; }
.card-hd .dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; background: var(--text3); }
.card.ok .dot { background: var(--success); }
.card.error .dot { background: var(--danger); }
.card-hd .lat { margin-left: auto; font-size: 0.72rem; color: var(--text3); flex-shrink: 0; }
.card-detail { font-size: 0.78rem; color: var(--text2); margin-top: 8px; word-break: break-word; line-height: 1.5; }

.sec { margin: 20px 0 10px; font-size: 0.92rem; font-weight: 600; color: var(--text); }
.proc { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 8px 20px; }
.prop { font-size: 0.84rem; color: var(--text); display: flex; align-items: center; gap: 10px; padding: 6px 0; border-bottom: 1px solid var(--bg2); }
.prop-label { color: var(--text3); font-weight: 600; min-width: 72px; flex-shrink: 0; }
.prop-value { color: var(--text); }
</style>
