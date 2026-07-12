<template>
  <div class="lc">
    <div class="lc-hd">
      <span class="lc-title">{{ title }}</span>
      <span class="lc-unit" v-if="unit">{{ unit }}</span>
    </div>
    <svg v-if="hasData" :viewBox="`0 0 ${W} ${H}`" class="lc-svg" preserveAspectRatio="none">
      <!-- y grid + labels -->
      <g v-for="(g, i) in yTicks" :key="'g'+i">
        <line :x1="padL" :y1="g.y" :x2="W - padR" :y2="g.y" class="lc-grid" />
        <text :x="padL - 4" :y="g.y + 3" text-anchor="end" class="lc-axis">{{ g.label }}</text>
      </g>
      <!-- x labels (first / mid / last) -->
      <text v-for="(x, i) in xTicks" :key="'x'+i" :x="x.x" :y="H - 2" text-anchor="middle" class="lc-axis">{{ x.label }}</text>
      <!-- lines -->
      <polyline v-for="s in paths" :key="s.name" :points="s.points" :stroke="s.color" fill="none" stroke-width="1.5" />
    </svg>
    <div v-else class="lc-empty">无数据</div>
    <div class="lc-legend" v-if="series.length > 1">
      <span v-for="(s, i) in series" :key="s.name" class="lc-lg">
        <span class="lc-dot" :style="{background: color(i)}"></span>{{ s.name }}
      </span>
    </div>
  </div>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  title: { type: String, default: "" },
  unit: { type: String, default: "" },
  labels: { type: Array, default: () => [] },
  // series: [{ name, points: [number|null,...] }]
  series: { type: Array, default: () => [] },
});

const PALETTE = ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6",
  "#06b6d4", "#ec4899", "#14b8a6", "#6366f1", "#84cc16"];
function color(i) { return PALETTE[i % PALETTE.length]; }

const W = 520, H = 160, padL = 44, padR = 10, padT = 10, padB = 18;

const allVals = computed(() =>
  props.series.flatMap(s => s.points).filter(v => v !== null && v !== undefined && !isNaN(v)));
const hasData = computed(() => allVals.value.length > 0 && props.labels.length > 0);
const maxY = computed(() => Math.max(1, ...allVals.value));

const n = computed(() => props.labels.length);
function xAt(i) {
  if (n.value <= 1) return padL;
  return padL + (i / (n.value - 1)) * (W - padL - padR);
}
function yAt(v) {
  return padT + (1 - v / maxY.value) * (H - padT - padB);
}

const paths = computed(() =>
  props.series.map((s, si) => {
    const pts = [];
    s.points.forEach((v, i) => {
      if (v === null || v === undefined || isNaN(v)) return;
      pts.push(`${xAt(i).toFixed(1)},${yAt(v).toFixed(1)}`);
    });
    return { name: s.name, color: color(si), points: pts.join(" ") };
  })
);

const yTicks = computed(() => {
  const ticks = [];
  for (let k = 0; k <= 4; k++) {
    const val = (maxY.value * k) / 4;
    ticks.push({ y: yAt(val), label: fmt(val) });
  }
  return ticks;
});

const xTicks = computed(() => {
  if (!n.value) return [];
  const idxs = n.value === 1 ? [0] : [0, Math.floor((n.value - 1) / 2), n.value - 1];
  return idxs.map(i => ({ x: xAt(i), label: shortT(props.labels[i]) }));
});

function fmt(v) {
  if (v >= 1000) return (v / 1000).toFixed(1) + "k";
  return Math.round(v).toString();
}
function shortT(t) {
  // "YYYY-MM-DD HH:MM" -> "MM-DD HH:MM"
  return (t || "").slice(5);
}
</script>

<style scoped>
.lc { border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px; background: var(--bg); }
.lc-hd { display: flex; align-items: baseline; gap: 6px; margin-bottom: 4px; }
.lc-title { font-size: 0.78rem; font-weight: 600; color: var(--text2); }
.lc-unit { font-size: 0.68rem; color: var(--text3); }
.lc-svg { width: 100%; height: 160px; display: block; }
.lc-grid { stroke: var(--border); stroke-width: 0.5; opacity: 0.5; }
.lc-axis { fill: var(--text3); font-size: 8px; }
.lc-empty { text-align: center; color: var(--text3); font-size: 0.78rem; padding: 40px 0; }
.lc-legend { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 6px; }
.lc-lg { display: inline-flex; align-items: center; gap: 3px; font-size: 0.68rem; color: var(--text3); }
.lc-dot { width: 8px; height: 8px; border-radius: 2px; display: inline-block; }
</style>
