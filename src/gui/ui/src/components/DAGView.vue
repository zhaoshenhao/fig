<template>
  <div ref="wrap" class="dag-wrap" :style="{ height: h + 'px' }">
    <svg
      ref="svgEl"
      :width="graphW"
      :height="graphH"
      :style="{ transform: `translate(${-vx}px, ${-vy}px)`, transition: panning ? 'none' : 'transform .2s' }"
    >
      <defs>
        <marker id="dag-arrow" markerWidth="7" markerHeight="6" refX="7" refY="3" orient="auto">
          <polygon points="0 0, 7 3, 0 6" fill="#94a3b8" />
        </marker>
      </defs>
      <path v-for="(e,i) in edges" :key="'e'+i" :d="e.d" stroke="#94a3b8" stroke-width="2" fill="none" marker-end="url(#dag-arrow)" />
      <g v-for="(n,i) in layoutNodes" :key="'n'+i" @click.stop="select(n)" style="cursor:pointer">
        <rect :x="n.x" :y="n.y" :width="n.w" :height="n.h" rx="8" :fill="n.bg" :stroke="n.color" stroke-width="2.5" />
        <rect :x="n.x" :y="n.y" :width="n.w" :height="44" rx="8" :fill="n.color" />
        <rect :x="n.x" :y="n.y+26" :width="n.w" :height="18" :fill="n.color" />
        <text :x="n.x+n.w/2" :y="n.y+30" text-anchor="middle" fill="#fff" font-size="28" font-weight="600" style="pointer-events:none">{{ n.head }}</text>
        <text :x="n.x+n.w/2" :y="n.y+56" text-anchor="middle" :fill="n.subColor" font-size="24" style="pointer-events:none">{{ n.sub }}</text>
      </g>
    </svg>
    <div v-if="sel" class="dag-card">
      <div class="dag-card-hd">
        <b>◉ {{ sel.name }}</b>
        <button class="dag-close" @click="sel=null">✕</button>
      </div>
      <div class="dag-row"><span>工具</span> {{ sel.tool || "-" }}</div>
      <div class="dag-row" v-if="sel.dur !== undefined"><span>耗时</span> {{ sel.dur }}ms</div>
      <div class="dag-row"><span>状态</span> {{ sel.status || "-" }}</div>
      <div class="dag-row" v-if="sel.next.length"><span>后继</span> {{ sel.next.join(", ") }}</div>
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
const emit = defineEmits(["selectNode"]);

const TOOL_COLORS = {
  llm: "#10b981", rag_search: "#3b82f6", router: "#8b5cf6", merge: "#f59e0b",
  db_query: "#06b6d4", api_call: "#ef4444", web_search: "#ec4899",
  extract_llm: "#6366f1", extract_regex: "#14b8a6", code: "#6b7280",
};
const STATUS_COLORS = {
  executed: "#4caf50", ok: "#4caf50", failed: "#f44336", error: "#f44336",
  skipped: "#9e9e9e", pending: "#64b5f6",
};

const NW = 320, NH = 70;
const BASE_HEAD = "28", BASE_SUB = "24";

const wrap = ref(null);
const svgEl = ref(null);
const h = ref(props.height);
const vx = ref(0), vy = ref(0);
const graphW = ref(800), graphH = ref(400);
const layoutNodes = ref([]);
const edges = ref([]);
const sel = ref(null);
const panning = ref(false);

let dagre = null;

function doLayout() {
  if (!dagre || !props.nodes.length) return;
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: "LR", nodesep: 80, ranksep: 140, edgesep: 30, marginx: 50, marginy: 50 });
  g.setDefaultEdgeLabel(() => ({}));

  const ndData = props.nodeData || {};
  const hasData = ndData && Object.keys(ndData).length > 0;
  const nameSet = new Set(props.nodes.map(n => n.name));

  for (const n of props.nodes) g.setNode(n.name, { width: NW, height: NH });

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
      color = STATUS_COLORS[st] || "#64b5f6";
      head = n.name.length > 14 ? n.name.slice(0, 13) + "…" : n.name;
      sub = st === "skipped" ? "-" : (tool || "-");
      subColor = st === "skipped" ? "var(--text3)" : "var(--text2)";
      bg = st === "skipped" ? "var(--bg3)" : "var(--bg)";
    } else {
      color = TOOL_COLORS[tool] || "#6b7280";
      head = tool ? tool.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase()) : n.name;
      head = head.length > 14 ? head.slice(0, 13) + "…" : head;
      sub = n.name.length > 18 ? n.name.slice(0, 17) + "…" : n.name;
      subColor = "var(--text2)";
      bg = "var(--bg)";
    }

    const x = d.x - NW / 2;
    const y = d.y - NH / 2;
    ns.push({ name: n.name, x, y, w: NW, h: NH, color, head, sub, subColor, bg, tool, dur, status: st, next: Array.isArray(n.next) ? n.next : (n.next ? [n.next] : []) });
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
  graphW.value = g.graph().width;
  graphH.value = g.graph().height;

  nextTick(() => {
    if (!wrap.value) return;
    const rect = wrap.value.getBoundingClientRect();
    const sx = rect.width / graphW.value;
    const sy = rect.height / graphH.value;
    const s = Math.min(sx, sy, 1);
    if (s < 1) {
      vx.value = 0;
      vy.value = 0;
      if (svgEl.value) {
        svgEl.value.style.transformOrigin = "0 0";
        svgEl.value.style.transform = `scale(${s})`;
      }
    }
  });
}

function select(n) {
  const data = { name: n.name, tool: n.tool, dur: n.dur, status: n.status, next: n.next || [], desc: n.desc || "" };
  sel.value = data;
  emit("selectNode", data);
}

let px = 0, py = 0;
function startPan(e) {
  if (e.target.closest(".dag-card")) return;
  panning.value = true;
  px = e.clientX;
  py = e.clientY;
}
function doPan(e) {
  if (!panning.value) return;
  vx.value += e.clientX - px;
  vy.value += e.clientY - py;
  px = e.clientX;
  py = e.clientY;
}
function endPan() { panning.value = false; }

watch(() => [props.nodes, props.nodeData], doLayout, { deep: true });
watch(() => props.height, v => { h.value = v; });

onMounted(async () => {
  await loadDagre();
  doLayout();
  if (wrap.value) {
    wrap.value.addEventListener("mousedown", startPan);
    window.addEventListener("mousemove", doPan);
    window.addEventListener("mouseup", endPan);
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
  width: 200px;
  max-height: calc(100% - 16px);
  overflow-y: auto;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px;
  box-shadow: var(--shadow-lg);
  font-size: 0.78rem;
}
.dag-card-hd {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}
.dag-row {
  font-size: 0.75rem;
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
