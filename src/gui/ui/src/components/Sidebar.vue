<template>
  <aside :class="['sidebar', { open }]">
    <div class="sidebar-header">KF · 智能客服</div>
    <div class="sidebar-section">
      <div class="sidebar-label">导航</div>
      <button
        v-for="item in NAV_ITEMS"
        :key="item.id"
        :class="['nav-item', { active: nav === item.id }]"
        @click="navigate(item.id)"
      >
        <span class="nav-icon">{{ item.icon }}</span>
        {{ item.label }}
      </button>
    </div>
    <div class="sidebar-section">
      <div class="sidebar-label">会话</div>
      <div style="padding:0 16px">
        <span v-if="chatId" style="font-size:0.78rem;color:var(--text3)">
          {{ chatId.slice(0, 16) }}... · Turn {{ turnId }}
        </span>
        <span v-else style="font-size:0.78rem;color:var(--text3)">暂无</span>
      </div>
    </div>
    <div class="sidebar-section">
      <div class="sidebar-label">API 连接</div>
      <div style="padding:0 12px">
        <label>
          <span :style="{color: connected ? 'var(--success)' : 'var(--danger)'}">
            {{ connected ? "● 已连接" : "● 已断开" }}
          </span>
        </label>
        <input
          v-model="apiKeyInput"
          type="password"
          placeholder="API Key..."
          style="width:100%;padding:4px 6px;border:1px solid var(--border);border-radius:4px;font-size:0.78rem;background:var(--bg);margin:4px 0"
          @input="apiKey = apiKeyInput; persist()"
        />
      </div>
    </div>
    <div class="sidebar-footer">
      <button class="theme-toggle" @click="toggleTheme">
        {{ themeLabel }}
      </button>
    </div>
  </aside>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, inject } from "vue";
import { useRouter, useRoute } from "vue-router";
import { useAppStore } from "../store.js";
import { api } from "../api.js";

defineProps({ open: Boolean });
const emit = defineEmits(["close"]);

const router = useRouter();
const route = useRoute();
const { nav, apiKey, chatId, turnId, theme, connected } = useAppStore();
const toast = inject("toast");
const apiKeyInput = ref("");

const NAV_ITEMS = [
  { id: "chat", label: "聊天", icon: "💬" },
  { id: "kb", label: "知识库浏览", icon: "📚" },
  { id: "workflow", label: "工作流", icon: "🔀" },
  { id: "docs", label: "文档管理", icon: "📄" },
  { id: "metrics", label: "聊天记录", icon: "📊" },
  { id: "dashboard", label: "仪表盘", icon: "📈" },
  { id: "status", label: "系统状态", icon: "🩺" },
];

const themeLabel = computed(() => theme.value === "dark" ? "☀️ 浅色模式" : "🌙 深色模式");

function navigate(id) {
  nav.value = id;
  persist();
  router.push("/" + id);
  emit("close");
}

function toggleTheme() {
  const next = theme.value === "dark" ? "light" : "dark";
  theme.value = next;
  document.documentElement.setAttribute("data-theme", next);
  persist();
}

function persist() {
  localStorage.setItem("kf_prefs", JSON.stringify({
    nav: nav.value, theme: theme.value, apiKey: apiKey.value,
  }));
}

let _timer = 0;
async function checkHealth() {
  connected.value = await api.health();
}

watch(() => route.path, (p) => {
  const id = p.replace("/", "") || "chat";
  if (nav.value !== id) nav.value = id;
}, { immediate: true });

onMounted(() => {
  document.documentElement.setAttribute("data-theme", theme.value);
  apiKeyInput.value = apiKey.value;
  checkHealth();
  _timer = setInterval(checkHealth, 15000);
});
onUnmounted(() => clearInterval(_timer));
</script>
