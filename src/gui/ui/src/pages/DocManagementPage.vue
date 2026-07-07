<template>
  <div>
    <!-- Upload -->
    <h3 style="font-size:0.9rem;font-weight:600;margin-bottom:8px">上传文档</h3>
    <div class="row" style="margin-bottom:6px">
      <label class="mode-label">
        <input type="radio" value="new" v-model="upMode" /> 新建
      </label>
      <label class="mode-label">
        <input type="radio" value="rebuild" v-model="upMode" /> 重建
      </label>
    </div>
    <div class="row" style="margin-bottom:8px">
      <input type="file" ref="fileInput" multiple
        accept=".txt,.md,.pdf,.docx,.csv,.xlsx"
        @change="onFileChange" style="flex:1;font-size:0.82rem" />
    </div>
    <div class="row" style="margin-bottom:12px;flex-wrap:wrap">
      <select v-if="upMode === 'rebuild'" v-model="upCollection" class="field" style="flex:1">
        <option value="">选择集合...</option>
        <option v-for="c in collections" :key="c" :value="c">{{ c }}</option>
      </select>
      <input v-else v-model="upCollection" class="field" placeholder="集合名称" style="flex:1" />
      <label class="fg"><span>chunk_size</span><input v-model.number="upChunkSize" class="field" type="number" min="64" max="4096" /></label>
      <label class="fg"><span>chunk_overlap</span><input v-model.number="upChunkOverlap" class="field" type="number" min="0" max="4096" /></label>
      <button class="btn primary" @click="doUpload" :disabled="!files.length || !upCollection || uploading">
        {{ uploading ? "上传中..." : "上传" }}
      </button>
    </div>
    <div v-if="uploadResult" class="result-msg success">{{ uploadResult }}</div>
    <div v-if="uploadError" class="result-msg error">{{ uploadError }}</div>

    <hr style="border:1px solid var(--border);margin:20px 0" />

    <!-- Scan -->
    <h3 style="font-size:0.9rem;font-weight:600;margin-bottom:8px">扫描目录</h3>
    <div class="row" style="margin-bottom:6px">
      <label class="mode-label">
        <input type="radio" value="new" v-model="scanMode" /> 新建
      </label>
      <label class="mode-label">
        <input type="radio" value="rebuild" v-model="scanMode" /> 重建
      </label>
    </div>
    <div class="row" style="margin-bottom:8px">
      <input v-model="scanDir" class="field" placeholder="目录路径" style="flex:1" />
    </div>
    <div class="row" style="margin-bottom:12px;flex-wrap:wrap">
      <select v-if="scanMode === 'rebuild'" v-model="scanCollection" class="field" style="flex:1">
        <option value="">选择集合...</option>
        <option v-for="c in collections" :key="c" :value="c">{{ c }}</option>
      </select>
      <input v-else v-model="scanCollection" class="field" placeholder="集合名称" style="flex:1" />
      <label class="fg"><span>chunk_size</span><input v-model.number="scanChunkSize" class="field" type="number" min="64" max="4096" /></label>
      <label class="fg"><span>chunk_overlap</span><input v-model.number="scanChunkOverlap" class="field" type="number" min="0" max="4096" /></label>
      <button class="btn primary" @click="doScan" :disabled="!scanDir || !scanCollection || scanning">
        {{ scanning ? "扫描中..." : "扫描" }}
      </button>
    </div>
    <div v-if="scanResult" class="result-msg success">{{ scanResult }}</div>
    <div v-if="scanError" class="result-msg error">{{ scanError }}</div>
  </div>
</template>

<script setup>
import { ref, inject, onMounted } from "vue";
import { api } from "../api.js";

const toast = inject("toast");
const collections = ref([]);

const fileInput = ref(null);
const files = ref([]);
const upMode = ref("new");
const upCollection = ref("");
const upChunkSize = ref(800);
const upChunkOverlap = ref(64);
const uploading = ref(false);
const uploadResult = ref("");
const uploadError = ref("");

const scanMode = ref("new");
const scanDir = ref("data/documents");
const scanCollection = ref("");
const scanChunkSize = ref(800);
const scanChunkOverlap = ref(64);
const scanning = ref(false);
const scanResult = ref("");
const scanError = ref("");

async function loadCollections() {
  try {
    const d = await api.get("/collections");
    collections.value = d.collections || [];
  } catch (_) {}
}

function onFileChange(e) {
  files.value = Array.from(e.target.files || []);
}

async function doUpload() {
  if (!files.value.length || !upCollection.value) return;
  uploading.value = true;
  uploadResult.value = "";
  uploadError.value = "";
  try {
    for (const f of files.value) {
      const fd = new FormData();
      fd.append("file", f);
      fd.append("collection", upCollection.value);
      fd.append("chunk_size", String(upChunkSize.value));
      fd.append("chunk_overlap", String(upChunkOverlap.value));
      const r = await api.post("/documents/upload", fd, true);
      uploadResult.value = `✅ ${f.name}: ${r.chunks} 分块 → ${r.collection}`;
    }
    toast("上传完成", "success");
    files.value = [];
    if (fileInput.value) fileInput.value.value = "";
    loadCollections();
  } catch (e) {
    uploadError.value = "上传失败: " + e.message;
    toast(uploadError.value, "error");
  }
  uploading.value = false;
}

async function doScan() {
  if (!scanDir.value || !scanCollection.value) return;
  scanning.value = true;
  scanResult.value = "";
  scanError.value = "";
  try {
    const fd = new FormData();
    fd.append("directory", scanDir.value);
    fd.append("collection", scanCollection.value);
    fd.append("chunk_size", String(scanChunkSize.value));
    fd.append("chunk_overlap", String(scanChunkOverlap.value));
    const r = await api.post("/documents/scan", fd, true);
    scanResult.value = `✅ ${r.directory}: ${r.chunks} 分块 → ${r.collection}`;
    toast("扫描完成", "success");
    loadCollections();
  } catch (e) {
    scanError.value = "扫描失败: " + e.message;
    toast(scanError.value, "error");
  }
  scanning.value = false;
}

onMounted(loadCollections);
</script>

<style scoped>
.row { display: flex; gap: 8px; align-items: center; }
.field { padding: 5px 8px; border: 1px solid var(--border); border-radius: 6px; background: var(--bg); font-size: 0.82rem; }
.btn { padding: 5px 14px; border: 1px solid var(--border); border-radius: 6px; background: var(--bg); font-size: 0.82rem; cursor: pointer; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn.primary { background: var(--accent); color: #fff; border-color: var(--accent); }
.mode-label { font-size: 0.82rem; display: flex; align-items: center; gap: 4px; cursor: pointer; }
.result-msg { padding: 6px 10px; border-radius: 6px; font-size: 0.8rem; margin-top: 4px; }
.result-msg.success { background: #d1fae5; color: #065f46; }
.result-msg.error { background: #fee2e2; color: #991b1b; }
.fg { display: flex; flex-direction: column; gap: 1px; }
.fg span { font-size: 0.65rem; color: var(--text3); }
</style>
