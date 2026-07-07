<template>
  <div ref="wrap" class="dag-wrap" :style="wrapStyle" @pointerdown.stop="onDown" @pointermove.stop="onMove" @pointerup.stop="onUp" @pointerleave="onUp">
    <svg :width="graphW" :height="graphH" :style="{ transform: `translate(${vx}px, ${vy}px)` }">
      <defs>
        <marker id="dag-arrow" markerWidth="7" markerHeight="6" refX="7" refY="3" orient="auto">
          <polygon points="0 0, 7 3, 0 6" fill="#94a3b8" />
        </marker>
      </defs>
      <path v-for="(e,i) in edges" :key="'e'+i" :d="e.d" stroke="#94a3b8" stroke-width="2" fill="none" marker-end="url(#dag-arrow)" />
      <g v-for="(n,i) in layoutNodes" :key="'n'+i" @click="select(n)" style="cursor:pointer">
        <template v-if="n.virtual">
          <title>虚拟节点&#10;{{ n.name }}</title>
          <circle :cx="n.x" :cy="n.y" :r="n.r" :fill="n.bg" :stroke="n.color" stroke-width="1" />
          <text :x="n.x" :y="n.y+5" text-anchor="middle" :fill="n.subColor" font-size="12" font-weight="600" style="pointer-events:none">{{ n.head }}</text>
        </template>
        <template v-else>
          <title>{{ n.fullHead }}&#10;{{ n.fullSub }}</title>
          <rect :x="n.x" :y="n.y" :width="n.w" :height="n.h" rx="6" :fill="n.bg" :stroke="n.color" stroke-width="1" />
          <rect :x="n.x" :y="n.y" :width="n.w" :height="19" rx="6" :fill="n.color" />
          <rect :x="n.x" :y="n.y+12" :width="n.w" :height="7" :fill="n.color" />
          <text :x="n.x+n.w/2" :y="n.y+13" text-anchor="middle" fill="#fff" font-size="13" font-weight="600" style="pointer-events:none">{{ n.head }}</text>
          <text :x="n.x+n.w/2" :y="n.y+29" text-anchor="middle" :fill="n.subColor" font-size="10" style="pointer-events:none">{{ n.sub }}</text>
        </template>
      </g>
    </svg>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, computed } from "vue";

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

const NW = 140, NH = 38;

const wrapStyle = computed(() => ({ height: props.height > 0 ? props.height + "px" : "100%" }));
const h = ref(props.height);
const wrap = ref(null);
const vx = ref(0), vy = ref(0);
const graphW = ref(800);
const graphH = ref(400);
const layoutNodes = ref([]);
const edges = ref([]);

let dagre = null;

async function loadDagre() {
  if (dagre) return;
  if (window.dagre) { dagre = window.dagre; return; }
  await new Promise((resolve) => {
    const s = document.createElement("script");
    s.src = "/dagre.min.js";
    s.onload = () => { dagre = window.dagre; resolve(); };
    document.head.appendChild(s);
  });
}

function doLayout() {
  if (!dagre || !props.nodes.length) return;
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: "LR", nodesep: 50, ranksep: 90, edgesep: 15, marginx: 40, marginy: 40 });
  g.setDefaultEdgeLabel(() => ({}));

  const ndData = props.nodeData || {};
  const hasData = ndData && Object.keys(ndData).length > 0;
  const nameSet = new Set(props.nodes.map(n => n.name));

  const hasVirtual = !hasData;
  const VR = 16;
  const VIRT_W = VR * 2, VIRT_H = VR * 2;

  if (hasVirtual) {
    g.setNode("INPUT", { width: VIRT_W, height: VIRT_H });
    g.setNode("OUTPUT", { width: VIRT_W, height: VIRT_H });
    const roots = props.nodes.filter(n => !props.nodes.some(m => {
      const nx = m.next || [];
      const targets = Array.isArray(nx) ? nx : (typeof nx === "string" ? [nx] : []);
      return targets.includes(n.name);
    }));
    const leaves = props.nodes.filter(n => {
      const nx = n.next || [];
      return !nx || (Array.isArray(nx) && nx.length === 0) || (typeof nx === "string" && !nameSet.has(nx));
    });
    for (const r of roots) g.setEdge("INPUT", r.name);
    for (const l of leaves) g.setEdge(l.name, "OUTPUT");
  }

  for (const n of props.nodes) g.setNode(n.name, { width: NW, height: NH });
  for (const n of props.nodes) {
    const nt = n.next_type || "one";
    const nxt = n.next || [];
    if (nt === "one" && nxt && typeof nxt === "string" && nameSet.has(nxt)) {
      g.setEdge(n.name, nxt);
    } else if (nt === "if-then" || nt === "switch") {
      for (const t of (Array.isArray(nxt) ? nxt : [nxt])) {
        if (nameSet.has(t)) g.setEdge(n.name, t);
      }
    }
  }

  dagre.layout(g);

  const ns = [];
  const MAX_H = 10, MAX_S = 14;

  if (hasVirtual) {
    const id = g.node("INPUT") || { x: 0, y: 0 };
    ns.push({ name: "INPUT", x: id.x, y: id.y, r: VR, virtual: true, color: "#94a3b8", head: "IN", subColor: "var(--text3)", bg: "var(--bg2)", tool: "", dur: undefined, status: "virtual", next: [] });
    const od = g.node("OUTPUT") || { x: 0, y: 0 };
    ns.push({ name: "OUTPUT", x: od.x, y: od.y, r: VR, virtual: true, color: "#94a3b8", head: "OUT", subColor: "var(--text3)", bg: "var(--bg2)", tool: "", dur: undefined, status: "virtual", next: [] });
  }

  for (const n of props.nodes) {
    const nd = ndData[n.name] || {};
    const st = nd.status || "pending";
    const tool = nd.tool || n.tool || "";
    const dur = nd.duration_ms !== undefined ? Math.round(Number(nd.duration_ms)) : undefined;
    const d = g.node(n.name) || { x: 0, y: 0 };

    let color, headFull, subFull, subColor, bg;
    if (hasData) {
      color = STATUS_COLORS[st] || "#64b5f6";
      headFull = n.name;
      subFull = st === "skipped" ? "-" : (tool || "-");
      subColor = st === "skipped" ? "var(--text3)" : "var(--text2)";
      bg = st === "skipped" ? "var(--bg3)" : "var(--bg)";
    } else {
      color = TOOL_COLORS[tool] || "#6b7280";
      headFull = tool ? tool.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase()) : n.name;
      subFull = n.name;
      subColor = "var(--text2)";
      bg = "var(--bg)";
    }

    const x = d.x - NW / 2;
    const y = d.y - NH / 2;
    ns.push({
      name: n.name, x, y, w: NW, h: NH, color, virtual: false,
      head: headFull.length > MAX_H ? headFull.slice(0, MAX_H - 1) + "…" : headFull,
      sub: subFull.length > MAX_S ? subFull.slice(0, MAX_S - 1) + "…" : subFull,
      fullHead: headFull, fullSub: subFull,
      subColor, bg, tool, dur, status: st,
      next: Array.isArray(n.next) ? n.next : (n.next ? [n.next] : []),
    });
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
}

function select(n) {
  if (moved) return;
  emit("selectNode", { name: n.name, tool: n.tool, dur: n.dur, status: n.status, next: n.next || [], desc: n.desc || "" });
}

let down = false, moved = false, sx = 0, sy = 0, ox = 0, oy = 0;

function onDown(e) {
  const onNode = e.target.closest("g");
  if (onNode) return; // let click bubble
  down = true;
  moved = false;
  sx = e.clientX;
  sy = e.clientY;
  ox = vx.value;
  oy = vy.value;
  e.target.setPointerCapture?.(e.pointerId);
}

function onMove(e) {
  if (!down) return;
  const dx = e.clientX - sx;
  const dy = e.clientY - sy;
  if (!moved && Math.abs(dx) < 2 && Math.abs(dy) < 2) return;
  moved = true;
  vx.value = ox + dx;
  vy.value = oy + dy;
}

function onUp() {
  down = false;
  setTimeout(() => { moved = false; }, 0);
}

watch([() => props.nodes, () => props.nodeData], () => doLayout());
watch(() => props.height, v => { h.value = v; });

onMounted(async () => {
  await loadDagre();
  doLayout();
});
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
  touch-action: none;
}
.dag-wrap:active { cursor: grabbing; }
</style>
