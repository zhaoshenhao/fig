<template>
  <div>
    <div class="row">
      <select v-model="collection" class="field" style="flex:1">
        <option v-for="c in collections" :key="c" :value="c">{{ c }}</option>
      </select>
      <select v-model="perPage" class="field">
        <option :value="10">10</option>
        <option :value="20">20</option>
        <option :value="50">50</option>
        <option :value="100">100</option>
      </select>
      <button class="btn btn-danger" @click="confirmDelete" :disabled="!collection" title="删除当前知识库">删除</button>
    </div>

    <div v-if="showConfirm" class="modal-overlay" @click.self="showConfirm=false">
      <div class="modal-panel">
        <div class="modal-hd">确认删除</div>
        <div class="modal-body">
          <p>确定要删除知识库 <b>{{ collection }}</b> 吗？</p>
          <p class="warn">此操作不可恢复，将删除该知识库中所有数据。</p>
        </div>
        <div class="modal-ft">
          <button class="btn" @click="showConfirm=false">取消</button>
          <button class="btn btn-danger" @click="doDelete" :disabled="deleting">{{ deleting ? "删除中..." : "确认删除" }}</button>
        </div>
      </div>
    </div>

    <div style="margin:10px 0">
      <input v-model="query" class="field" style="width:100%" placeholder="搜索关键词..." @keydown.enter="doSearch" />
    </div>

    <div v-if="!query" style="margin-bottom:8px">
      <div class="row" style="justify-content:center">
        <button class="btn" @click="prevPage" :disabled="page<=1">上一页</button>
        <span style="font-size:0.82rem;color:var(--text2);padding:4px 12px">
          第 {{ page }}/{{ maxPage }} 页（共 {{ total }}）
        </span>
        <button class="btn" @click="nextPage" :disabled="page>=maxPage">下一页</button>
      </div>
    </div>

    <div v-if="!collections.length && !loading" class="empty">暂无知识库</div>
    <div v-else-if="loading" class="empty">加载中...</div>
    <div v-else-if="!results.length && !query" class="empty">暂无数据</div>
    <div v-else-if="!results.length" class="empty">未找到结果</div>

    <div v-for="r in results" :key="r.id" class="kb-item">
      <details>
        <summary>ID: {{ r.id }} <span v-if="r.score!==undefined" style="color:var(--text3);font-size:0.75rem">| {{ r.score.toFixed(4) }}</span></summary>
        <div v-if="query">
          <div class="kb-text" v-html="highlight(r.text || '', query)"></div>
        </div>
        <div v-else>
          <pre class="kb-payload">{{ formatJSON(r.payload) }}</pre>
        </div>
      </details>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, inject, computed } from "vue";
import { api } from "../api.js";

const toast = inject("toast");
const collections = ref([]);
const collection = ref("");
const perPage = ref(20);
const query = ref("");
const results = ref([]);
const total = ref(0);
const page = ref(1);
const loading = ref(false);
const deleting = ref(false);
const showConfirm = ref(false);

const maxPage = computed(() => Math.max(1, Math.ceil(total.value / perPage.value)));

async function loadCollections() {
  try {
    const d = await api.get("/collections");
    collections.value = d.collections || [];
    if (collections.value.length && !collection.value) collection.value = collections.value[0];
  } catch (e) {
    toast("加载集合列表失败: " + e.message, "error");
  }
}

async function loadBrowse() {
  if (!collection.value) return;
  loading.value = true;
  try {
    const ct = await api.get(`/collections/${collection.value}/count`);
    total.value = ct.count || 0;
    const d = await api.get(`/collections/${collection.value}/browse`, {
      limit: perPage.value,
      offset: (page.value - 1) * perPage.value,
    });
    results.value = (d.points || []).map(p => ({
      id: p.id,
      payload: p.payload || {},
      text: (p.payload && p.payload.text) || JSON.stringify(p.payload || {}),
      score: p.score,
    }));
  } catch { results.value = []; total.value = 0; }
  loading.value = false;
}

function confirmDelete() {
  if (!collection.value) return;
  showConfirm.value = true;
}

async function doDelete() {
  deleting.value = true;
  try {
    await api.del(`/collections/${collection.value}`);
    toast(`知识库 "${collection.value}" 已删除`, "info");
    showConfirm.value = false;
    await loadCollections();
    if (collections.value.length) {
      collection.value = collections.value[0];
      page.value = 1;
      await loadBrowse();
    } else {
      collection.value = "";
      results.value = [];
      total.value = 0;
    }
  } catch (e) {
    toast("删除失败: " + e.message, "error");
  }
  deleting.value = false;
}

async function doSearch() {
  if (!query.value.trim() || !collection.value) return;
  loading.value = true;
  try {
    const d = await api.get(`/collections/${collection.value}/search`, {
      q: query.value.trim(),
      limit: perPage.value,
    });
    results.value = (d.points || []).map(p => ({
      id: p.id,
      payload: { text: p.text, source: p.source },
      text: p.text || "",
      score: p.score,
    }));
    if (!results.value.length) toast("未找到相关结果", "info");
  } catch (e) { toast("搜索失败: " + e.message, "error"); results.value = []; }
  loading.value = false;
}

function highlight(text, term) {
  if (!term || !text) return text;
  const escaped = term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return text.replace(new RegExp(`(${escaped})`, "gi"), "<mark>$1</mark>");
}
function formatJSON(obj) {
  try { return JSON.stringify(obj, null, 2); } catch { return String(obj); }
}
function nextPage() { if (page.value < maxPage.value) page.value++; }
function prevPage() { if (page.value > 1) page.value--; }

watch([collection, perPage, page], () => { if (!query.value) loadBrowse(); });
onMounted(() => { loadCollections().then(() => { if (collection.value) loadBrowse(); }); });
</script>

<style scoped>
.row { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; }
.field { padding: 5px 8px; border: 1px solid var(--border); border-radius: 6px; background: var(--bg); font-size: 0.82rem; color: var(--text); }
.btn { padding: 5px 14px; border: 1px solid var(--border); border-radius: 6px; background: var(--bg); font-size: 0.82rem; color: var(--text); cursor: pointer; }
.btn:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-danger { border-color: var(--danger); color: var(--danger); }
.empty { text-align: center; color: var(--text3); padding: 40px 0; font-size: 0.9rem; }
.kb-item { margin-bottom: 4px; font-size: 0.82rem; }
.kb-item summary { cursor: pointer; padding: 6px 8px; border-radius: 4px; background: var(--bg2); }
.kb-item summary:hover { background: var(--bg3); }
.kb-text { font-size: 0.8rem; white-space: pre-wrap; margin: 8px 0; }
.kb-text :deep(mark) { background: #fef08a; color: #000; padding: 0 2px; border-radius: 2px; }
.kb-payload { font-size: 0.72rem; color: var(--text2); white-space: pre-wrap; background: var(--bg2); padding: 8px; border-radius: 4px; overflow-x: auto; max-height: 200px; }
.modal-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 100; }
.modal-panel { background: var(--bg); border-radius: 10px; padding: 24px; max-width: 400px; width: 90%; box-shadow: 0 4px 20px rgba(0,0,0,0.3); }
.modal-hd { font-size: 1.1rem; font-weight: 700; margin-bottom: 12px; }
.modal-body { margin-bottom: 20px; font-size: 0.9rem; }
.modal-body .warn { color: var(--danger); font-size: 0.82rem; margin-top: 8px; }
.modal-ft { display: flex; justify-content: flex-end; gap: 10px; }
</style>
