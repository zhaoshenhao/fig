<template>
  <div>
    <div class="chat-controls">
      <div class="row">
        <select v-model="wfName" class="field">
          <option v-for="w in workflows" :key="w.name" :value="w.name">{{ w.name }}</option>
        </select>
        <label class="check"><input type="checkbox" v-model="useStream" /> 流式</label>
        <button class="btn" @click="clearChat">清空</button>
        <label class="check"><input type="checkbox" v-model="autoScroll" /> 自动滚动</label>
      </div>
    </div>

    <div ref="msgBox" class="chat-messages" @scroll="onScroll">
      <div v-if="!messages.length" class="empty">输入消息开始对话</div>
      <div v-for="(m, i) in messages" :key="i" :class="['msg', m.role]">
        <div class="msg-role">{{ m.role === "user" ? "👤" : "🤖" }}</div>
        <div class="msg-body">
          <div class="msg-text">{{ m.content }}</div>
          <div class="msg-ts" v-if="m.ts">{{ m.ts }}</div>
          <div v-if="m.content && m.role==='assistant' && messages.indexOf(m)===messages.length-1 && !streaming" class="msg-actions">
            <button class="btn-sm" @click="copyText(m.content)">📋 复制</button>
          </div>
        </div>
      </div>
      <div v-if="streaming" class="msg assistant">
        <div class="msg-role">🤖</div>
        <div class="msg-body"><div class="msg-text">{{ streamText }}<span class="cursor">▌</span></div></div>
      </div>
      <div ref="msgEnd"></div>
    </div>

    <div class="chat-input-area">
      <textarea
        v-model="input"
        class="chat-textarea"
        rows="2"
        placeholder="输入消息..."
        @keydown.enter.exact.prevent="send"
      ></textarea>
      <button class="btn primary" @click="send" :disabled="!input.trim() || streaming">发送</button>
    </div>

    <details v-if="messages.length" style="margin-top:12px">
      <summary style="cursor:pointer;font-size:0.8rem;color:var(--text3)">导出对话</summary>
      <div style="display:flex;gap:8px;margin-top:8px">
        <button class="btn-sm" @click="exportJSON">JSON</button>
        <button class="btn-sm" @click="exportCSV">CSV</button>
      </div>
    </details>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted, nextTick, watch, inject } from "vue";
import { store } from "../store.js";
import { api } from "../api.js";

const toast = inject("toast");
const workflows = ref([]);
const wfName = ref("");
const input = ref("");
const messages = ref([]);
const useStream = ref(store.streamDefault);
const autoScroll = ref(true);
const streaming = ref(false);
const streamText = ref("");
const msgBox = ref(null);
const msgEnd = ref(null);
let abortCtrl = null;

async function loadWorkflows() {
  try {
    const d = await api.get("/workflows");
    workflows.value = d.workflows || [];
    if (workflows.value.length && !wfName.value) wfName.value = workflows.value[0].name;
  } catch (e) {
    toast("无法加载工作流列表", "error");
  }
}

function scrollBottom() {
  if (autoScroll.value) {
    nextTick(() => msgEnd.value?.scrollIntoView({ behavior: "smooth" }));
  }
}

function onScroll() {
  if (!msgBox.value) return;
  const el = msgBox.value;
  autoScroll.value = el.scrollHeight - el.scrollTop - el.clientHeight < 60;
}

async function send() {
  const text = input.value.trim();
  if (!text || streaming.value) return;
  input.value = "";
  const ts = new Date().toLocaleTimeString("zh-CN", { hour12: false });
  messages.value.push({ role: "user", content: text, ts });

  const payload = { query: text };
  if (store.chatId) payload.chat_id = store.chatId;

  scrollBottom();
  streaming.value = true;
  streamText.value = "";

  if (useStream.value) {
    let reply = "";
    abortCtrl = await api.stream(
      `/workflows/${wfName.value}/run?stream=true`, payload,
      (token) => { streamText.value += token; scrollBottom(); },
      (done) => {
        reply = done.reply || streamText.value;
        store.chatId = done.chat_id || store.chatId;
        store.turnId = done.turn_id || 0;
        finish(reply, ts);
      },
      (err) => { finish("错误: " + err, ts); },
    );
  } else {
    try {
      const d = await api.post(`/workflows/${wfName.value}/run`, payload);
      store.chatId = d.chat_id || store.chatId;
      store.turnId = d.turn_id || 0;
      finish(d.reply || "", ts);
    } catch (e) {
      finish("连接失败: " + e.message, ts);
    }
  }
}

function finish(reply, ts) {
  if (reply) messages.value.push({ role: "assistant", content: reply, ts });
  streaming.value = false;
  streamText.value = "";
  abortCtrl = null;
  scrollBottom();
}

async function clearChat() {
  if (store.chatId) {
    try { await api.del(`/sessions/${store.chatId}`); } catch (_) {}
  }
  store.chatId = "";
  store.turnId = 0;
  messages.value = [];
}

function exportJSON() {
  download(JSON.stringify(messages.value, null, 2), "chat_history.json", "application/json");
}
function exportCSV() {
  let csv = "role,content,timestamp\n";
  for (const m of messages.value) {
    csv += `"${m.role}","${(m.content || "").replace(/"/g,'""')}","${m.ts || ""}"\n`;
  }
  download(csv, "chat_history.csv", "text/csv");
}
function download(content, filename, mime) {
  const blob = new Blob([content], { type: mime });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}
async function copyText(text) {
  try { await navigator.clipboard.writeText(text); toast("已复制", "success"); }
  catch { toast("复制失败", "error"); }
}

onMounted(loadWorkflows);
onUnmounted(() => { if (abortCtrl) abortCtrl.abort(); });
</script>

<style scoped>
.chat-controls { margin-bottom: 10px; }
.row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.field { padding: 5px 8px; border: 1px solid var(--border); border-radius: 6px; background: var(--bg); font-size: 0.82rem; }
.check { font-size: 0.8rem; display: flex; align-items: center; gap: 4px; cursor: pointer; }
.btn { padding: 5px 14px; border: 1px solid var(--border); border-radius: 6px; background: var(--bg); font-size: 0.82rem; color: var(--text); }
.btn.primary { background: var(--accent); color: #fff; border-color: var(--accent); }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-sm { padding: 2px 10px; font-size: 0.75rem; border: 1px solid var(--border); border-radius: 4px; background: var(--bg); color: var(--text); }

.chat-messages { height: calc(100vh - 200px); min-height: 300px; overflow-y: auto; padding: 8px 0; }
.empty { text-align: center; color: var(--text3); padding: 40px 0; font-size: 0.9rem; }

.msg { display: flex; gap: 10px; padding: 8px 0; }
.msg.user { flex-direction: row-reverse; }
.msg-role { font-size: 1.2rem; flex-shrink: 0; margin-top: 2px; }
.msg-body { max-width: 75%; }
.msg.user .msg-body { text-align: right; }
.msg-text { white-space: pre-wrap; word-break: break-word; font-size: 0.85rem; line-height: 1.55; }
.user .msg-text { background: var(--bg3); padding: 8px 12px; border-radius: 10px 10px 0 10px; display: inline-block; text-align: left; }
.msg-ts { font-size: 0.68rem; color: var(--text3); margin-top: 2px; }
.msg-actions { margin-top: 4px; }

.chat-input-area { display: flex; gap: 8px; margin-top: 10px; }
.chat-textarea { flex: 1; padding: 8px; border: 1px solid var(--border); border-radius: 8px; resize: none; background: var(--bg); font-size: 0.85rem; }
.chat-textarea:focus { outline: 2px solid var(--accent); border-color: var(--accent); }

.cursor { animation: blink 1s step-end infinite; }
@keyframes blink { 50% { opacity: 0; } }
</style>
