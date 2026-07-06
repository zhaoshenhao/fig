<template>
  <div>
    <h3 style="font-size:0.9rem;font-weight:600;margin-bottom:8px">上传文档</h3>
    <div class="row" style="margin-bottom:8px">
      <input type="file" ref="fileInput" multiple
        accept=".txt,.md,.pdf,.docx,.csv,.xlsx"
        @change="onFileChange" style="flex:1;font-size:0.82rem" />
    </div>
    <div class="row" style="margin-bottom:12px">
      <input v-model="upCollection" class="field" placeholder="目标集合" style="flex:1" />
      <input v-model.number="upChunkSize" class="field" type="number" placeholder="分块大小" style="width:100px" min="64" max="4096" />
      <button class="btn primary" @click="doUpload" :disabled="!files.length || uploading">
        {{ uploading ? "上传中..." : "上传" }}
      </button>
    </div>
    <div v-if="uploadResult" class="result-msg success">{{ uploadResult }}</div>
    <div v-if="uploadError" class="result-msg error">{{ uploadError }}</div>

    <hr style="border:1px solid var(--border);margin:20px 0" />

    <h3 style="font-size:0.9rem;font-weight:600;margin-bottom:8px">扫描目录</h3>
    <div class="row" style="margin-bottom:8px">
      <input v-model="scanDir" class="field" placeholder="目录路径" style="flex:1" />
      <input v-model="scanCollection" class="field" placeholder="目标集合" style="flex:1" />
      <button class="btn primary" @click="doScan" :disabled="!scanDir || scanning">
        {{ scanning ? "扫描中..." : "扫描" }}
      </button>
    </div>
    <div v-if="scanResult" class="result-msg success">{{ scanResult }}</div>
    <div v-if="scanError" class="result-msg error">{{ scanError }}</div>
  </div>
</template>

<script setup>
import { ref, inject } from "vue";
import { api } from "../api.js";

const toast = inject("toast");
const fileInput = ref(null);
const files = ref([]);
const upCollection = ref("default");
const upChunkSize = ref(800);
const uploading = ref(false);
const uploadResult = ref("");
const uploadError = ref("");

const scanDir = ref("data/documents");
const scanCollection = ref("default");
const scanning = ref(false);
const scanResult = ref("");
const scanError = ref("");

function onFileChange(e) {
  files.value = Array.from(e.target.files || []);
}

async function doUpload() {
  if (!files.value.length) return;
  uploading.value = true;
  uploadResult.value = "";
  uploadError.value = "";
  try {
    for (const f of files.value) {
      const fd = new FormData();
      fd.append("file", f);
      fd.append("collection", upCollection.value || "default");
      fd.append("chunk_size", String(upChunkSize.value));
      const r = await api.post("/documents/upload", fd, true);
      uploadResult.value = `✅ ${f.name}: ${r.chunks} 分块 → ${r.collection}`;
    }
    toast("上传完成", "success");
    files.value = [];
    if (fileInput.value) fileInput.value.value = "";
  } catch (e) {
    uploadError.value = "上传失败: " + e.message;
    toast(uploadError.value, "error");
  }
  uploading.value = false;
}

async function doScan() {
  scanning.value = true;
  scanResult.value = "";
  scanError.value = "";
  try {
    const fd = new FormData();
    fd.append("directory", scanDir.value);
    fd.append("collection", scanCollection.value || "default");
    const r = await api.post("/documents/scan", fd, true);
    scanResult.value = `✅ ${r.directory}: ${r.chunks} 分块 → ${r.collection}`;
    toast("扫描完成", "success");
  } catch (e) {
    scanError.value = "扫描失败: " + e.message;
    toast(scanError.value, "error");
  }
  scanning.value = false;
}
</script>

<style scoped>
.row { display: flex; gap: 8px; align-items: center; }
.field { padding: 5px 8px; border: 1px solid var(--border); border-radius: 6px; background: var(--bg); font-size: 0.82rem; }
.btn { padding: 5px 14px; border: 1px solid var(--border); border-radius: 6px; background: var(--bg); font-size: 0.82rem; cursor: pointer; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn.primary { background: var(--accent); color: #fff; border-color: var(--accent); }
.result-msg { padding: 6px 10px; border-radius: 6px; font-size: 0.8rem; margin-top: 4px; }
.result-msg.success { background: #d1fae5; color: #065f46; }
.result-msg.error { background: #fee2e2; color: #991b1b; }
</style>
