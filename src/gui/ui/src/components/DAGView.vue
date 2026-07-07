<template>
  <div ref="wrap" class="dag-wrap" :style="{ height: h + 'px' }">
    <div class="dag-scroll">
      <svg :width="graphW" :height="graphH">
        <defs>
          <marker id="dag-arrow" markerWidth="7" markerHeight="6" refX="7" refY="3" orient="auto">
            <polygon points="0 0, 7 3, 0 6" fill="#94a3b8" />
          </marker>
        </defs>
        <g v-for="(e,i) in edges" :key="'e'+i">
          <path :d="e.d" stroke="#94a3b8" stroke-width="2" fill="none" marker-end="url(#dag-arrow)" />
        </g>
        <g v-for="(n,i) in layoutNodes" :key="'n'+i" @click.stop="select(n)" style="cursor:pointer">
          <rect :x="n.x" :y="n.y" :width="n.w" :height="n.h" rx="8" :fill="n.bg" :stroke="n.color" stroke-width="2" />
          <rect :x="n.x" :y="n.y" :width="n.w" :height="24" rx="8" :fill="n.color" />
          <rect :x="n.x" :y="n.y+15" :width="n.w" :height="9" :fill="n.color" />
          <text :x="n.x+n.w/2" :y="n.y+16" text-anchor="middle" fill="#fff" font-size="16" font-weight="600" style="pointer-events:none">{{ n.head }}</text>
          <text :x="n.x+n.w/2" :y="n.y+36" text-anchor="middle" :fill="n.subColor" font-size="13" style="pointer-events:none">{{ n.sub }}</text>
        </g>
      </svg>
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

const NW = 190, NH = 48;

const h = ref(props.height);
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
  g.setGraph({ rankdir: "LR", nodesep: 70, ranksep: 120, edgesep: 20, marginx: 50, marginy: 50 });
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
      for (const t of (Array.isArray(nxt) ? nxt : [nxt])) {
        if (nameSet.has(t)) g.setEdge(n.name, t);
      }
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
    const x = d.x - NW / 2;
    const y = d.y - NH / 2;

    let color, head, sub, subColor, bg;
    if (hasData) {
      color = STATUS_COLORS[st] || "#64b5f6";
      head = n.name.length > 12 ? n.name.slice(0, 11) + "…" : n.name;
      sub = st === "skipped" ? "-" : (tool || "-");
      subColor = st === "skipped" ? "var(--text3)" : "var(--text2)";
      bg = st === "skipped" ? "var(--bg3)" : "var(--bg)";
    } else {
      color = TOOL_COLORS[tool] || "#6b7280";
      head = tool ? tool.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase()) : n.name;
      head = head.length > 12 ? head.slice(0, 11) + "…" : head;
      sub = n.name.length > 16 ? n.name.slice(0, 15) + "…" : n.name;
      subColor = "var(--text2)";
      bg = "var(--bg)";
    }

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
}

function select(n) {
  emit("selectNode", { name: n.name, tool: n.tool, dur: n.dur, status: n.status, next: n.next || [], desc: n.desc || "" });
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
  background: var(--bg2);
  border-radius: 8px;
  border: 1px solid var(--border);
  user-select: none;
}
.dag-scroll {
  width: 100%;
  height: 100%;
  overflow: auto;
}
</style>
