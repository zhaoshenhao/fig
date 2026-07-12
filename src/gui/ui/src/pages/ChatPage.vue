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
      <details v-if="storeChatId" class="sess-meta">
        <summary>会话信息 · {{ sessTitle || '未命名' }}</summary>
        <div class="row" style="margin-top:6px">
          <input v-model="sessTitle" class="field" placeholder="会话标题" style="flex:1" />
          <input v-model="sessTags" class="field" placeholder="标签（逗号分隔）" style="flex:1" />
          <button class="btn-sm" @click="saveMeta">保存</button>
        </div>
      </details>
    </div>

    <div ref="msgBox" class="chat-messages" @scroll="onScroll">
      <div v-if="!messages.length" class="empty">输入消息开始对话</div>
      <div v-for="(m, i) in messages" :key="i" :class="['msg', m.role]">
        <div class="msg-role">{{ m.role === "user" ? "👤" : "🤖" }}</div>
        <div class="msg-body">
          <div v-if="m.role === 'assistant'" class="msg-text md" v-html="renderMarkdown(m.content)"></div>
          <div v-else class="msg-text">{{ m.content }}</div>
          <div class="msg-ts" v-if="m.ts">{{ m.ts }}</div>
          <div v-if="m.content && m.role==='assistant'" class="msg-actions">
            <button class="btn-xs" @click="copyText(m.content)" title="复制">📋</button>
            <template v-if="m.turnId !== null && m.turnId !== undefined">
              <button class="btn-xs" :class="{on: m.feedback==='up'}" @click="toggleFeedback(m,'up')" title="有帮助">👍</button>
              <button class="btn-xs" :class="{on: m.feedback==='down'}" @click="toggleFeedback(m,'down')" title="没帮助/纠错">👎</button>
            </template>
            <button v-if="i===messages.length-1 && !streaming && storeChatId" class="btn-xs" @click="regenerate" title="重新生成">🔄 重新生成</button>
          </div>
          <div v-if="m.fbOpen" class="fb-box">
            <div class="fb-hint">{{ m.fbRating==='up' ? '👍 好评' : '👎 差评' }} · 补充反馈（可选）</div>
            <input v-model="m.fbComment" class="fb-input" placeholder="评论，如：回答很清楚 / 答非所问" />
            <textarea v-if="m.fbRating==='down'" v-model="m.fbCorrection" class="fb-input" rows="2" placeholder="纠错：正确答案应该是……"></textarea>
            <div class="fb-actions">
              <button class="btn-xs primary" @click="submitFeedback(m)">提交</button>
              <button class="btn-xs" @click="m.fbOpen=false">取消</button>
            </div>
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
        ref="inputBox"
        v-model="input"
        class="chat-textarea"
        rows="2"
        placeholder="输入消息...（Enter 或 Ctrl+Enter 发送，Shift+Enter 换行）"
        @keydown.enter.exact.prevent="send"
        @keydown.enter.ctrl.prevent="send"
      ></textarea>
      <button class="btn primary" @click="send" :disabled="!input.trim() || streaming">发送</button>
    </div>

    <details v-if="messages.length" style="margin-top:12px">
      <summary style="cursor:pointer;font-size:0.8rem;color:var(--text3)">导出对话</summary>
      <div style="display:flex;gap:8px;margin-top:8px">
        <button class="btn-sm" @click="exportJSON">JSON</button>
        <button class="btn-sm" @click="exportCSV">CSV</button>
        <button class="btn-sm" @click="exportExcel">Excel</button>
      </div>
    </details>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, nextTick, inject } from "vue";
import { useAppStore } from "../store.js";
import { api } from "../api.js";
import { renderMarkdown } from "../md.js";

const toast = inject("toast");
const { chatId: storeChatId, turnId: storeTurnId } = useAppStore();
const workflows = ref([]);
const wfName = ref("");
const input = ref("");
const messages = ref([]);
const useStream = ref(false);
const autoScroll = ref(true);
const streaming = ref(false);
const streamText = ref("");
const msgBox = ref(null);
const msgEnd = ref(null);
const inputBox = ref(null);
const sessTitle = ref("");
const sessTags = ref("");
/** @type {AbortController|null} */
let abortCtrl = null;

async function loadWorkflows() {
  try {
    const d = await api.get("/api/v1/workflows");
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
  if (storeChatId.value) payload.chat_id = storeChatId.value;

  scrollBottom();
  streaming.value = true;
  streamText.value = "";

  if (useStream.value) {
    let reply = "";
    abortCtrl = await api.stream(
      `/api/v1/workflows/${wfName.value}/run?stream=true`, payload,
      (token) => { streamText.value += token; scrollBottom(); },
      (done) => {
        reply = done.reply || streamText.value;
        storeChatId.value = done.chat_id || storeChatId.value;
        storeTurnId.value = done.turn_id || 0;
        finish(reply, ts, (done.turn_id || 1) - 1);
      },
      (err) => { finish("错误: " + err, ts, null); },
    );
  } else {
    try {
      const d = await api.post(`/api/v1/workflows/${wfName.value}/run`, payload);
      storeChatId.value = d.chat_id || storeChatId.value;
      storeTurnId.value = d.turn_id || 0;
      finish(d.reply || "", ts, (d.turn_id || 1) - 1);
    } catch (e) {
      finish("连接失败: " + e.message, ts, null);
    }
  }
}

function finish(reply, ts, turnId = null) {
  if (reply) messages.value.push({
    role: "assistant", content: reply, ts, turnId, feedback: null,
    fbOpen: false, fbRating: "", fbComment: "", fbCorrection: "",
  });
  streaming.value = false;
  streamText.value = "";
  abortCtrl = null;
  scrollBottom();
}

function toggleFeedback(m, rating) {
  // 点击 👍/👎 展开反馈输入框（可填评论/纠错），再点提交才写入
  if (m.fbOpen && m.fbRating === rating) { m.fbOpen = false; return; }
  m.fbRating = rating;
  m.fbComment = m.fbComment || "";
  m.fbCorrection = m.fbCorrection || "";
  m.fbOpen = true;
  scrollBottom();
}

async function submitFeedback(m) {
  if (!storeChatId.value || m.turnId === null || m.turnId === undefined) return;
  try {
    await api.post(
      `/api/v1/sessions/${storeChatId.value}/turns/${m.turnId}/feedback`,
      {
        rating: m.fbRating,
        comment: (m.fbComment || "").trim() || null,
        correction: m.fbRating === "down" ? ((m.fbCorrection || "").trim() || null) : null,
      },
    );
    m.feedback = m.fbRating;
    m.fbOpen = false;
    toast(m.fbRating === "up" ? "感谢反馈 👍" : "已记录 👎", "success");
  } catch (e) {
    toast("反馈失败: " + e.message, "error");
  }
}

async function regenerate() {
  if (!storeChatId.value || streaming.value) return;
  const ts = new Date().toLocaleTimeString("zh-CN", { hour12: false });
  streaming.value = true;
  streamText.value = "";
  scrollBottom();
  try {
    const d = await api.post(`/api/v1/workflows/${wfName.value}/regenerate`,
      { chat_id: storeChatId.value });
    storeTurnId.value = d.turn_id || storeTurnId.value;
    finish(d.reply || "", ts, (d.turn_id || 1) - 1);
  } catch (e) {
    finish("重新生成失败: " + e.message, ts, null);
  }
}

async function saveMeta() {
  if (!storeChatId.value) return;
  const tags = sessTags.value.split(",").map(s => s.trim()).filter(Boolean);
  try {
    await api.patch(`/api/v1/sessions/${storeChatId.value}/meta`,
      { title: sessTitle.value, tags });
    toast("会话信息已保存", "success");
  } catch (e) {
    toast("保存失败: " + e.message, "error");
  }
}

async function clearChat() {
  if (!messages.value.length && !storeChatId.value) return;
  if (!window.confirm("确定清空当前对话？此操作不可恢复。")) return;
  if (storeChatId.value) {
    try { await api.del(`/api/v1/sessions/${storeChatId.value}`); }
    catch (e) { toast("删除会话失败: " + e.message, "error"); }
  }
  storeChatId.value = "";
  storeTurnId.value = 0;
  messages.value = [];
  sessTitle.value = "";
  sessTags.value = "";
}

function exportRows() {
  // 组装含反馈的导出行
  return messages.value.map(m => ({
    role: m.role,
    content: m.content,
    ts: m.ts || "",
    feedback: m.feedback || "",
    comment: m.fbComment || "",
    correction: m.fbCorrection || "",
  }));
}
function exportJSON() {
  download(JSON.stringify(exportRows(), null, 2), "chat_history.json", "application/json");
}
function exportCSV() {
  let csv = "role,content,timestamp,feedback,comment,correction\n";
  for (const m of exportRows()) {
    const esc = (v) => `"${String(v || "").replace(/"/g, '""')}"`;
    csv += [m.role, m.content, m.ts, m.feedback, m.comment, m.correction].map(esc).join(",") + "\n";
  }
  download("\ufeff" + csv, "chat_history.csv", "text/csv");
}
async function exportExcel() {
  try {
    const blob = await api.postBlob("/export/chat.xlsx", { messages: exportRows() });
    downloadBlob(blob, "chat_history.xlsx");
  } catch (e) {
    toast("Excel 导出失败: " + e.message, "error");
  }
}
function download(content, filename, mime) {
  downloadBlob(new Blob([content], { type: mime }), filename);
}
function downloadBlob(blob, filename) {
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

function onGlobalKey(e) {
  // "/" 聚焦输入框（当前焦点不在输入类元素时）
  if (e.key === "/" && !streaming.value) {
    const tag = (document.activeElement?.tagName || "").toLowerCase();
    if (tag !== "input" && tag !== "textarea") {
      e.preventDefault();
      inputBox.value?.focus();
    }
  }
}

onMounted(() => {
  loadWorkflows();
  window.addEventListener("keydown", onGlobalKey);
});
onUnmounted(() => {
  abortCtrl?.abort();
  window.removeEventListener("keydown", onGlobalKey);
});
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
.btn-xs { padding: 1px 7px; font-size: 0.72rem; border: 1px solid var(--border); border-radius: 4px; background: var(--bg); color: var(--text2); cursor: pointer; }
.btn-xs:hover { background: var(--bg3); }
.btn-xs.on { background: var(--accent); color: #fff; border-color: var(--accent); }

.sess-meta { margin-top: 6px; font-size: 0.8rem; }
.sess-meta summary { cursor: pointer; color: var(--text3); }

.btn-xs.primary { background: var(--accent); color: #fff; border-color: var(--accent); }
.fb-box { margin-top: 6px; padding: 8px; border: 1px solid var(--border); border-radius: 6px; background: var(--bg2); max-width: 420px; }
.fb-hint { font-size: 0.72rem; color: var(--text3); margin-bottom: 4px; }
.fb-input { width: 100%; padding: 4px 6px; border: 1px solid var(--border); border-radius: 4px; background: var(--bg); font-size: 0.78rem; margin-bottom: 4px; resize: vertical; box-sizing: border-box; }
.fb-actions { display: flex; gap: 6px; }

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
.msg-actions { margin-top: 4px; display: flex; gap: 6px; align-items: center; }

.chat-input-area { display: flex; gap: 8px; margin-top: 10px; }
.chat-textarea { flex: 1; padding: 8px; border: 1px solid var(--border); border-radius: 8px; resize: none; background: var(--bg); font-size: 0.85rem; }
.chat-textarea:focus { outline: 2px solid var(--accent); border-color: var(--accent); }

.cursor { animation: blink 1s step-end infinite; }
@keyframes blink { 50% { opacity: 0; } }

.msg-text.md :deep(p) { margin: 0 0 4px; }
.msg-text.md :deep(h3), .msg-text.md :deep(h4), .msg-text.md :deep(h5), .msg-text.md :deep(h6) { margin: 6px 0 4px; font-size: 0.92rem; }
.msg-text.md :deep(ul) { margin: 4px 0; padding-left: 20px; }
.msg-text.md :deep(li) { margin: 2px 0; }
.msg-text.md :deep(a) { color: var(--accent); }
.msg-text.md :deep(.md-code) { background: var(--bg3); padding: 1px 5px; border-radius: 4px; font-family: "Cascadia Code", "Consolas", monospace; font-size: 0.8rem; }
.msg-text.md :deep(.md-pre) { background: var(--bg2); border: 1px solid var(--border); border-radius: 6px; padding: 8px 10px; overflow-x: auto; margin: 6px 0; }
.msg-text.md :deep(.md-pre code) { font-family: "Cascadia Code", "Consolas", monospace; font-size: 0.78rem; white-space: pre; }
.msg-text.md :deep(br) { line-height: 0.5; }
</style>
