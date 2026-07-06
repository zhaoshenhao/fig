<template>
  <div ref="wrap" class="dag-wrap" :style="{ height: h + 'px' }">
    <svg ref="svgEl" :viewBox="`${vx} ${vy} ${vw} ${vh}`" style="width:100%;height:100%">
      <defs>
        <marker id="dag-arrow" markerWidth="6" markerHeight="5" refX="6" refY="2.5" orient="auto">
          <polygon points="0 0, 6 2.5, 0 5" fill="#94a3b8" />
        </marker>
      </defs>
      <path v-for="(e,i) in edges" :key="'e'+i" :d="e.d" stroke="#94a3b8" stroke-width="1.2" fill="none" marker-end="url(#dag-arrow)" />
      <g v-for="(n,i) in layoutNodes" :key="'n'+i" @click.stop="select(n)" style="cursor:pointer">
        <rect :x="n.x-n.w/2" :y="n.y-n.h/2" :width="n.w" :height="n.h" rx="8" :fill="n.bg" :stroke="n.color" stroke-width="1.5" />
        <rect :x="n.x-n.w/2" :y="n.y-n.h/2" :width="n.w" :height="40" rx="8" :fill="n.color" />
        <rect :x="n.x-n.w/2" :y="n.y-n.h/2+24" :width="n.w" :height="16" :fill="n.color" />
        <text :x="n.x" :y="n.y-n.h/2+28" text-anchor="middle" fill="#fff" font-size="20" font-weight="600" style="pointer-events:none">{{ n.head }}</text>
        <text :x="n.x" :y="n.y+8" text-anchor="middle" :fill="n.subColor" font-size="18" style="pointer-events:none">{{ n.sub }}</text>
      </g>
    </svg>
    <div v-if="sel" class="dag-card">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
        <b style="font-size:0.82rem">◉ {{ sel.name }}</b>
        <button class="dag-close" @click="sel=null">✕</button>
      </div>
      <div class="dag-row"><span>工具</span> {{ sel.tool || "-" }}</div>
      <div class="dag-row" v-if="sel.dur !== undefined"><span>耗时</span> {{ sel.dur }}ms</div>
      <div class="dag-row"><span>状态</span> {{ sel.status || "-" }}</div>
      <div class="dag-row" v-if="sel.next.length"><span>后继</span> {{ sel.next.join(", ") }}</div>
      <div class="dag-row" v-if="sel.desc"><span>描述</span> {{ sel.desc }}</div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, nextTick } from "vue";

const props = defineProps({
  nodes: { type: Array, required: true },
  nodeData: { type: Object, default: null },
  height: { type: Number, default: 400 },
});

const TOOL_COLORS = {
  llm: "#10b981", rag_search: "#3b82f6", router: "#8b5cf6", merge: "#f59e0b",
  db_query: "#06b6d4", api_call: "#ef4444", web_search: "#ec4899",
  extract_llm: "#6366f1", extract_regex: "#14b8a6", code: "#6b7280",
};
const STATUS_COLORS = {
  executed: "#4caf50", ok: "#4caf50", failed: "#f44336", error: "#f44336",
  skipped: "#9e9e9e", pending: "#64b5f6",
};

const wrap = ref(null);
const svgEl = ref(null);
const h = ref(props.height);
const vx = ref(0), vy = ref(0), vw = ref(800), vh = ref(props.height);
const layoutNodes = ref([]);
const edges = ref([]);
const sel = ref(null);

let dagre = null;

function toolColor(tool) { return TOOL_COLORS[tool] || "#6b7280"; }
function statusColor(st) { return STATUS_COLORS[st] || "#64b5f6"; }

function doLayout() {
  if (!dagre || !props.nodes.length) return;
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: "LR", nodesep: 60, ranksep: 100, edgesep: 20, marginx: 30, marginy: 30 });
  g.setDefaultEdgeLabel(() => ({}));

  const ndData = props.nodeData || {};
  const hasData = ndData && Object.keys(ndData).length > 0;
  const nameSet = new Set(props.nodes.map(n => n.name));

  for (const n of props.nodes) g.setNode(n.name, { width: 300, height: 100 });

  for (const n of props.nodes) {
    const nt = n.next_type || "one";
    const nxt = n.next || [];
    if (nt === "one" && nxt && typeof nxt === "string" && nameSet.has(nxt)) {
      g.setEdge(n.name, nxt);
    } else if (nt === "if-then" || nt === "switch") {
      const ts = Array.isArray(nxt) ? nxt : [nxt];
      for (const t of ts) { if (nameSet.has(t)) g.setEdge(n.name, t); }
    }
  }

  dagre.layout(g);

  const ns = [];
  for (const n of props.nodes) {
    const nd = ndData[n.name] || {};
    const st = nd.status || "pending";
    const tool = nd.tool || n.tool || "";
    const dur = nd.duration_ms !== undefined ? Math.round(Number(nd.duration_ms)) : undefined;
    const d = g.node(n.name) || { x: 0, y: 0 };

    let color, head, sub, subColor, bg;
    if (hasData) {
      color = statusColor(st);
      head = n.name.length > 14 ? n.name.slice(0, 13) + "…" : n.name;
      sub = st === "skipped" ? "-" : (tool || "-");
      subColor = st === "skipped" ? "var(--text3)" : "var(--text2)";
      bg = st === "skipped" ? "var(--bg3)" : "var(--bg)";
    } else {
      color = toolColor(tool);
      head = tool ? tool.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase()) : n.name;
      head = head.length > 14 ? head.slice(0, 13) + "…" : head;
      sub = n.name.length > 18 ? n.name.slice(0, 17) + "…" : n.name;
      subColor = "var(--text2)";
      bg = "var(--bg)";
    }

    ns.push({ name: n.name, x: d.x, y: d.y, w: 300, h: 100, color, head, sub, subColor, bg, tool, dur, status: st, next: Array.isArray(n.next) ? n.next : (n.next ? [n.next] : []) });
  }

  const es = [];
  for (const e of g.edges()) {
    const pts = g.edge(e).points || [];
    if (pts.length < 2) continue;
    let path = `M${pts[0].x},${pts[0].y}`;
    if (pts.length === 2) {
      const cx1 = pts[0].x + (pts[1].x - pts[0].x) * 0.4;
      const cx2 = pts[0].x + (pts[1].x - pts[0].x) * 0.6;
      path += ` C${cx1},${pts[0].y} ${cx2},${pts[1].y} ${pts[1].x},${pts[1].y}`;
    } else {
      for (let i = 1; i < pts.length; i++) path += ` L${pts[i].x},${pts[i].y}`;
    }
    es.push({ d: path });
  }

  layoutNodes.value = ns;
  edges.value = es;
  const gw = g.graph().width + 80;
  const gh = g.graph().height + 80;
  vw.value = Math.max(gw, 800);
  vh.value = Math.max(gh, props.height);
}

function select(n) {
  sel.value = { name: n.name, tool: n.tool, dur: n.dur, status: n.status, next: n.next || [], desc: n.desc || "" };
}

let panning = false, px = 0, py = 0;
function startPan(e) { panning = true; px = e.clientX; py = e.clientY; }
function doPan(e) {
  if (!panning) return;
  const rect = wrap.value?.getBoundingClientRect();
  if (!rect) return;
  const dx = ((e.clientX - px) / rect.width) * vw.value;
  const dy = ((e.clientY - py) / rect.height) * vh.value;
  vx.value -= dx; vy.value -= dy;
  px = e.clientX; py = e.clientY;
}
function endPan() { panning = false; }

watch(() => [props.nodes, props.nodeData], doLayout, { deep: true });
watch(() => props.height, v => { h.value = v; });

onMounted(async () => {
  await loadDagre();
  doLayout();
  if (wrap.value) {
    wrap.value.addEventListener("mousedown", startPan);
    wrap.value.addEventListener("mousemove", doPan);
    wrap.value.addEventListener("mouseup", endPan);
    wrap.value.addEventListener("mouseleave", endPan);
  }
});

async function loadDagre() {
  if (dagre) return;
  if (window.dagre) { dagre = window.dagre; return; }
  return new Promise((resolve) => {
    const s = document.createElement("script");
    s.src = "/dagre.min.js";
    s.onload = () => { dagre = window.dagre; resolve(); };
    document.head.appendChild(s);
  });
}
</script>

<style scoped>
.dag-wrap {
  position: relative;
  overflow: hidden;
  background: var(--bg2);
  border-radius: 8px;
  border: 1px solid var(--border);
  cursor: grab;
  user-select: none;
}
.dag-wrap:active { cursor: grabbing; }
.dag-card {
  position: absolute;
  right: 8px;
  top: 8px;
  width: 190px;
  max-height: calc(100% - 16px);
  overflow-y: auto;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px;
  box-shadow: var(--shadow-lg);
  font-size: 0.75rem;
}
.dag-row {
  font-size: 0.72rem;
  margin-bottom: 3px;
  color: var(--text2);
}
.dag-row span { color: var(--text3); margin-right: 6px; }
.dag-close {
  border: none;
  background: var(--bg3);
  border-radius: 4px;
  padding: 2px 8px;
  cursor: pointer;
  font-size: 0.85rem;
}
</style>
