<template>
  <div style="display:flex;flex-direction:column;height:calc(100vh - 80px)">
    <div class="tabs" style="flex-shrink:0">
      <button :class="['tab', {active: tab==='overview'}]" @click="tab='overview'">总览</button>
      <button :class="['tab', {active: tab==='charts'}]" @click="tab='charts'">图表</button>
    </div>

    <!-- ============ 总览 ============ -->
    <template v-if="tab === 'overview'">
      <div class="row" style="flex-shrink:0;margin:8px 0">
        <div style="flex:1"></div>
        <button class="btn" @click="refreshSummary" :disabled="loading">{{ loading ? "刷新中..." : "刷新" }}</button>
      </div>
      <div class="scroll">
        <div v-if="summary" class="dash">
          <div class="ov-cards">
            <div class="ov"><div class="ov-v">{{ summary.overview.total_runs }}</div><div class="ov-l">总请求</div></div>
            <div class="ov"><div class="ov-v">{{ summary.overview.total_sessions }}</div><div class="ov-l">会话数</div></div>
            <div class="ov"><div class="ov-v" :class="{bad: summary.overview.error_rate > 0}">{{ (summary.overview.error_rate*100).toFixed(1) }}%</div><div class="ov-l">错误率</div></div>
            <div class="ov"><div class="ov-v">{{ Math.round(summary.overview.avg_ms) }}<small>ms</small></div><div class="ov-l">平均耗时</div></div>
            <div class="ov"><div class="ov-v">{{ Math.round(summary.overview.p50_ms) }}<small>ms</small></div><div class="ov-l">P50</div></div>
            <div class="ov"><div class="ov-v">{{ Math.round(summary.overview.p95_ms) }}<small>ms</small></div><div class="ov-l">P95</div></div>
            <div class="ov"><div class="ov-v">{{ Math.round(summary.overview.p99_ms) }}<small>ms</small></div><div class="ov-l">P99</div></div>
            <div class="ov"><div class="ov-v">{{ tokTotal }}</div><div class="ov-l">Tokens</div></div>
            <div class="ov">
              <div class="ov-v">{{ costDisplay }}</div>
              <div class="ov-l">费用（估算）</div>
            </div>
            <div class="ov">
              <div class="ov-v">{{ (summary.overview.rating_rate*100).toFixed(0) }}%</div>
              <div class="ov-l">评价率 ({{ summary.overview.feedback_total }}/{{ summary.overview.total_runs }})</div>
            </div>
            <div class="ov">
              <div class="ov-v" :class="{good: summary.overview.feedback_total > 0}">
                {{ summary.overview.feedback_total ? (summary.overview.satisfaction_rate*100).toFixed(0)+'%' : '-' }}
              </div>
              <div class="ov-l">好评率 ({{ summary.overview.feedback_up }}👍/{{ summary.overview.feedback_down }}👎)</div>
            </div>
            <div class="ov">
              <div class="ov-v">{{ (summary.overview.feedback_rate*100).toFixed(0) }}%</div>
              <div class="ov-l">反馈率（含文字）</div>
            </div>
          </div>

          <div v-if="!summary.by_workflow.length" class="empty" style="padding:20px">暂无数据</div>

          <div v-for="w in summary.by_workflow" :key="w.workflow_name" class="wf-block">
            <div class="wf-title">
              <span class="wf-name">{{ w.workflow_name }}</span>
              <span class="wf-badge">{{ w.runs }} 请求</span>
            </div>

            <div class="metric-row">
              <div class="mchip"><span class="mv">{{ w.runs }}</span><span class="ml">总请求</span></div>
              <div class="mchip"><span class="mv">{{ w.sessions }}</span><span class="ml">总会话</span></div>
              <div class="mchip"><span class="mv" :class="{bad: w.error_rate>0}">{{ (w.error_rate*100).toFixed(1) }}%</span><span class="ml">错误率</span></div>
              <div class="mchip"><span class="mv">{{ Math.round(w.avg_ms) }}<small>ms</small></span><span class="ml">平均耗时</span></div>
              <div class="mchip"><span class="mv">{{ Math.round(w.p95_ms) }}<small>ms</small></span><span class="ml">P95 延迟</span></div>
              <div class="mchip"><span class="mv">{{ w.tokens }}</span><span class="ml">总 Token</span></div>
              <div class="mchip">
                <span class="mv">{{ w.cost_estimated < 0.01 ? '¥' + (w.cost_estimated||0).toFixed(4) : '¥' + (w.cost_estimated||0).toFixed(2) }}</span>
                <span class="ml">费用（估算）</span>
              </div>
              <div class="mchip"><span class="mv">{{ (w.rating_rate*100).toFixed(0) }}%</span><span class="ml">评价率 ({{ w.feedback_total }}/{{ w.runs }})</span></div>
              <div class="mchip"><span class="mv" :class="{good: w.feedback_total>0}">{{ w.feedback_total ? (w.satisfaction_rate*100).toFixed(0)+'%' : '-' }}</span><span class="ml">好评率 ({{ w.feedback_up }}👍/{{ w.feedback_down }}👎)</span></div>
              <div class="mchip"><span class="mv">{{ (w.feedback_rate*100).toFixed(0) }}%</span><span class="ml">反馈率（含文字）</span></div>
            </div>

            <div class="sub-cols">
              <div class="sub">
                <div class="sub-h">节点</div>
                <table class="mtable">
                  <thead><tr><th>节点</th><th>请求</th><th>平均</th><th>P95</th><th>错误率</th></tr></thead>
                  <tbody>
                    <tr v-for="n in (summary.wf_nodes[w.workflow_name] || [])" :key="n.node_name">
                      <td>{{ n.node_name }}</td>
                      <td>{{ n.calls }}</td>
                      <td>{{ Math.round(n.avg_ms) }}ms</td>
                      <td>{{ Math.round(n.p95_ms) }}ms</td>
                      <td :class="{bad: n.error_rate>0}">{{ (n.error_rate*100).toFixed(1) }}%</td>
                    </tr>
                    <tr v-if="!(summary.wf_nodes[w.workflow_name] || []).length"><td colspan="5" class="none">无</td></tr>
                  </tbody>
                </table>
              </div>
              <div class="sub">
                <div class="sub-h">工具</div>
                <table class="mtable">
                  <thead><tr><th>工具</th><th>请求</th><th>平均</th><th>P95</th><th>错误率</th></tr></thead>
                  <tbody>
                    <tr v-for="t in (summary.wf_tools[w.workflow_name] || [])" :key="t.tool_name">
                      <td>{{ t.tool_name || '-' }}</td>
                      <td>{{ t.calls }}</td>
                      <td>{{ Math.round(t.avg_ms) }}ms</td>
                      <td>{{ Math.round(t.p95_ms) }}ms</td>
                      <td :class="{bad: t.error_rate>0}">{{ (t.error_rate*100).toFixed(1) }}%</td>
                    </tr>
                    <tr v-if="!(summary.wf_tools[w.workflow_name] || []).length"><td colspan="5" class="none">无</td></tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
        <div v-else-if="err" class="empty">加载失败：{{ err }}</div>
        <div v-else class="empty">加载中...</div>
      </div>
    </template>

    <!-- ============ 图表 ============ -->
    <template v-else-if="tab === 'charts'">
      <div class="row" style="flex-shrink:0;flex-wrap:wrap;gap:8px;margin:8px 0">
        <select v-model="cWorkflow" class="field" @change="loadTimeseries">
          <option value="">选择工作流...</option>
          <option v-for="w in workflows" :key="w.name" :value="w.name">{{ w.name }}</option>
        </select>
        <select v-model="timeRange" class="field" @change="onTimePreset">
          <option v-for="p in TIME_PRESETS" :key="p.value" :value="p.value">{{ p.label }}</option>
          <option value="custom">自定义</option>
        </select>
        <template v-if="timeRange === 'custom'">
          <input type="datetime-local" v-model="timeFrom" class="field" />
          <input type="datetime-local" v-model="timeTo" class="field" />
        </template>
        <button class="btn" @click="loadTimeseries" :disabled="!cWorkflow || tsLoading">
          {{ tsLoading ? "加载中..." : "刷新" }}
        </button>
      </div>

      <div class="scroll">
        <div v-if="!cWorkflow" class="empty">请选择一个工作流</div>
        <div v-else-if="ts && !ts.buckets.length" class="empty">该时间范围内暂无数据</div>
        <template v-else-if="ts">
          <div class="sec-h">工作流：{{ ts.workflow }}</div>
          <div class="chart-grid">
            <LineChart title="活跃 Session 数" unit="/分钟" :labels="ts.buckets" :series="wfSeries('active_sessions')" />
            <LineChart title="请求轮次（每分钟）" unit="次/分钟" :labels="ts.buckets" :series="wfSeries('requests')" />
            <LineChart title="平均延迟" unit="ms" :labels="ts.buckets" :series="wfSeries('avg_ms')" />
            <LineChart title="P95 延迟" unit="ms" :labels="ts.buckets" :series="wfSeries('p95_ms')" />
            <LineChart title="好评率" unit="%" :labels="ts.buckets" :series="satisfactionSeries()" />
            <LineChart title="反馈量（每分钟）" unit="次/分钟" :labels="ts.buckets" :series="feedbackCountSeries()" />
          </div>

          <div class="sec-h">节点（按 node）</div>
          <div class="chart-grid">
            <LineChart title="节点请求（每分钟）" unit="次/分钟" :labels="ts.buckets" :series="groupSeries('nodes','requests')" />
            <LineChart title="节点平均延迟" unit="ms" :labels="ts.buckets" :series="groupSeries('nodes','avg_ms')" />
            <LineChart title="节点 P95 延迟" unit="ms" :labels="ts.buckets" :series="groupSeries('nodes','p95_ms')" />
          </div>

          <div class="sec-h">工具（按 tool）</div>
          <div class="chart-grid">
            <LineChart title="工具请求（每分钟）" unit="次/分钟" :labels="ts.buckets" :series="groupSeries('tools','requests')" />
            <LineChart title="工具平均延迟" unit="ms" :labels="ts.buckets" :series="groupSeries('tools','avg_ms')" />
            <LineChart title="工具 P95 延迟" unit="ms" :labels="ts.buckets" :series="groupSeries('tools','p95_ms')" />
          </div>
        </template>
        <div v-else class="empty">加载中...</div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, inject } from "vue";
import { api } from "../api.js";
import LineChart from "../components/LineChart.vue";

const toast = inject("toast");
const tab = ref("overview");

/* ---------- 总览 ---------- */
const summary = ref(null);
const loading = ref(false);
const err = ref("");
const tokTotal = computed(() => {
  const o = summary.value?.overview || {};
  return (o.prompt_tokens || 0) + (o.completion_tokens || 0);
});
const costDisplay = computed(() => {
  const c = (summary.value?.overview || {}).cost_estimated || 0;
  return c < 0.01 ? '￥' + c.toFixed(4) : '￥' + c.toFixed(2);
});
async function refreshSummary() {
  loading.value = true; err.value = "";
  try { summary.value = await api.get("/metrics/summary"); }
  catch (e) { err.value = e.message; toast("仪表盘加载失败: " + e.message, "error"); }
  loading.value = false;
}

/* ---------- 图表 ---------- */
const TIME_PRESETS = [
  { label: "最后 15 分钟", value: "15m" }, { label: "最后 30 分钟", value: "30m" },
  { label: "最后 1 小时", value: "1h" }, { label: "最后 2 小时", value: "2h" },
  { label: "最后 4 小时", value: "4h" }, { label: "最后 12 小时", value: "12h" },
  { label: "最后 24 小时", value: "24h" }, { label: "最后 3 天", value: "3d" },
  { label: "最后 7 天", value: "7d" },
];
const workflows = ref([]);
const cWorkflow = ref("");
const timeRange = ref("1h");
const timeFrom = ref("");
const timeTo = ref("");
const ts = ref(null);
const tsLoading = ref(false);

function toDbTime(d) {
  if (isNaN(d.getTime())) return "";
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getUTCFullYear()}-${p(d.getUTCMonth() + 1)}-${p(d.getUTCDate())} ` +
         `${p(d.getUTCHours())}:${p(d.getUTCMinutes())}:${p(d.getUTCSeconds())}`;
}
function parseTimePreset(pv) {
  const now = Date.now();
  const m = { m: 60000, h: 3600000, d: 86400000, w: 604800000 };
  for (const [k, v] of Object.entries(m)) {
    if (pv.endsWith(k)) { const num = parseInt(pv); return toDbTime(new Date(now - num * v)); }
  }
  return "";
}
function onTimePreset() {
  if (timeRange.value !== "custom") loadTimeseries();
}

async function loadWorkflows() {
  try {
    const d = await api.get("/api/v1/workflows");
    workflows.value = d.workflows || [];
  } catch (e) { toast("加载工作流失败: " + e.message, "error"); }
}

async function loadTimeseries() {
  if (!cWorkflow.value) return;
  tsLoading.value = true;
  try {
    const params = { workflow: cWorkflow.value };
    if (timeRange.value === "custom") {
      if (timeFrom.value) params.time_from = toDbTime(new Date(timeFrom.value));
      if (timeTo.value) params.time_to = toDbTime(new Date(timeTo.value));
    } else {
      const f = parseTimePreset(timeRange.value);
      if (f) params.time_from = f;
    }
    ts.value = await api.get("/metrics/timeseries", params);
  } catch (e) { toast("图表加载失败: " + e.message, "error"); }
  tsLoading.value = false;
}

function wfSeries(metric) {
  if (!ts.value) return [];
  return [{ name: ts.value.workflow, points: ts.value.workflow_series[metric] || [] }];
}
function satisfactionSeries() {
  if (!ts.value) return [];
  // satisfaction 为 0..1 或 null，转百分比
  const pts = (ts.value.workflow_series.satisfaction || [])
    .map(v => (v === null || v === undefined) ? null : Math.round(v * 100));
  return [{ name: "好评率", points: pts }];
}
function feedbackCountSeries() {
  if (!ts.value) return [];
  const ws = ts.value.workflow_series;
  return [
    { name: "👍 好评", points: ws.feedback_up || [] },
    { name: "👎 差评", points: ws.feedback_down || [] },
  ];
}
function groupSeries(group, metric) {
  if (!ts.value) return [];
  const g = ts.value[group] || {};
  return Object.entries(g).map(([name, s]) => ({ name, points: s[metric] || [] }));
}

onMounted(() => {
  refreshSummary();
  loadWorkflows();
});
</script>

<style scoped>
.tabs { display: flex; gap: 0; border-bottom: 1px solid var(--border); }
.tab { padding: 8px 18px; border: none; background: none; font-size: 0.85rem; cursor: pointer; color: var(--text2); border-bottom: 2px solid transparent; }
.tab.active { color: var(--accent); border-bottom-color: var(--accent); font-weight: 600; }

.row { display: flex; gap: 8px; align-items: center; }
.field { padding: 5px 8px; border: 1px solid var(--border); border-radius: 6px; background: var(--bg); font-size: 0.82rem; color: var(--text); }
.btn { padding: 5px 14px; border: 1px solid var(--border); border-radius: 6px; background: var(--bg); font-size: 0.82rem; cursor: pointer; color: var(--text); }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.scroll { flex: 1; overflow: auto; min-height: 0; }
.empty { text-align: center; color: var(--text3); padding: 30px 0; font-size: 0.85rem; }

.dash { padding: 4px 0; }
.ov-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(110px, 1fr)); gap: 8px; margin-bottom: 14px; }
.ov { background: var(--bg2); border: 1px solid var(--border); border-radius: 8px; padding: 10px; text-align: center; }
.ov-v { font-size: 1.25rem; font-weight: 700; color: var(--text); }
.ov-v small { font-size: 0.65rem; color: var(--text3); }
.ov-v.bad { color: var(--danger); }
.ov-v.good { color: var(--success); }
.muted { font-size: 0.75rem; color: var(--text3); align-self: center; }
.fb-card { border: 1px solid var(--border); border-radius: 8px; padding: 8px 12px; margin-bottom: 8px; background: var(--bg); }
.fb-head { display: flex; align-items: center; gap: 10px; margin-bottom: 4px; flex-wrap: wrap; }
.fb-badge { font-size: 0.72rem; font-weight: 600; padding: 1px 8px; border-radius: 10px; }
.fb-badge.up { background: #dcfce7; color: #166534; }
.fb-badge.down { background: #fee2e2; color: #991b1b; }
.fb-wf { font-size: 0.75rem; color: var(--text2); background: var(--bg2); padding: 1px 6px; border-radius: 4px; }
.fb-time { font-size: 0.68rem; color: var(--text3); }
.fb-qa { font-size: 0.8rem; color: var(--text); margin: 2px 0; word-break: break-word; }
.fb-qa b { color: var(--text3); }
.fb-extra { font-size: 0.78rem; color: var(--text2); background: var(--bg2); padding: 3px 6px; border-radius: 4px; margin-top: 3px; }
.fb-extra.corr { border-left: 3px solid var(--accent); }
.ov-l { font-size: 0.7rem; color: var(--text3); margin-top: 2px; }

.wf-block { border: 1px solid var(--border); border-radius: 8px; padding: 10px 12px; margin-bottom: 12px; background: var(--bg); }
.wf-title { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.wf-name { font-size: 0.92rem; font-weight: 700; color: var(--text); }
.wf-badge { font-size: 0.68rem; color: var(--text3); background: var(--bg2); padding: 1px 8px; border-radius: 10px; }
.metric-row { display: grid; grid-template-columns: repeat(auto-fill, minmax(90px, 1fr)); gap: 8px; margin-bottom: 10px; }
.mchip { background: var(--bg2); border: 1px solid var(--border); border-radius: 6px; padding: 6px 8px; text-align: center; }
.mchip .mv { display: block; font-size: 0.95rem; font-weight: 700; color: var(--text); }
.mchip .mv small { font-size: 0.6rem; color: var(--text3); }
.mchip .mv.bad { color: var(--danger); }
.mchip .mv.good { color: var(--success); }
.mchip .ml { font-size: 0.64rem; color: var(--text3); }
.sub-cols { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
@media (max-width: 760px) { .sub-cols { grid-template-columns: 1fr; } }
.sub-h { font-size: 0.76rem; font-weight: 600; color: var(--text2); margin-bottom: 4px; }
.mtable { width: 100%; border-collapse: collapse; font-size: 0.72rem; }
.mtable th, .mtable td { padding: 3px 6px; text-align: left; border-bottom: 1px solid var(--border); white-space: nowrap; }
.mtable th { color: var(--text3); font-weight: 600; }
.mtable td.bad { color: var(--danger); }
.mtable td.none { text-align: center; color: var(--text3); }

.sec-h { font-size: 0.85rem; font-weight: 600; color: var(--text2); margin: 14px 0 8px; }
.chart-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 12px; }
</style>
