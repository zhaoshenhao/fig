<template>
  <aside :class="['sidebar', { open }]">
    <div class="sidebar-header">KF · 智能客服</div>
    <div class="sidebar-section">
      <div class="sidebar-label">导航</div>
      <button
        v-for="item in navItems"
        :key="item.id"
        :class="['nav-item', { active: store.nav === item.id }]"
        @click="navigate(item.id)"
      >
        <span class="nav-icon">{{ item.icon }}</span>
        {{ item.label }}
      </button>
    </div>
    <div class="sidebar-section">
      <div class="sidebar-label">会话</div>
      <div style="padding:0 16px">
        <span v-if="store.chatId" style="font-size:0.78rem;color:var(--text3)">
          {{ store.chatId.slice(0, 16) }}... · Turn {{ store.turnId }}
        </span>
        <span v-else style="font-size:0.78rem;color:var(--text3)">暂无</span>
      </div>
    </div>
    <div class="sidebar-section">
      <div class="sidebar-label">API 连接</div>
      <div style="padding:0 12px">
        <label>
          <span :style="{color: store.connected ? 'var(--success)' : 'var(--danger)'}">
            {{ store.connected ? "● 已连接" : "● 已断开" }}
          </span>
        </label>
        <input
          v-model="apiKeyInput"
          type="password"
          placeholder="API Key..."
          style="width:100%;padding:4px 6px;border:1px solid var(--border);border-radius:4px;font-size:0.78rem;background:var(--bg);margin:4px 0"
          @input="onApiKeyChange"
        />
      </div>
    </div>
    <div class="sidebar-footer">
      <label>
        <input type="checkbox" v-model="store.streamDefault" @change="store._persist()" />
        默认流式输出
      </label>
      <button class="theme-toggle" @click="toggleTheme">
        {{ store.theme === "dark" ? "☀️ 浅色模式" : "🌙 深色模式" }}
      </button>
    </div>
  </aside>
</template>

<script>
import { inject, onMounted, ref, watch } from "vue";
import { useRouter, useRoute } from "vue-router";
import { store } from "../store.js";
import { api } from "../api.js";

export default {
  props: { open: Boolean },
  emits: ["close"],
  setup(props, { emit }) {
    const toast = inject("toast");
    const router = useRouter();
    const route = useRoute();
    const apiKeyInput = ref("");

    const navItems = [
      { id: "chat", label: "聊天", icon: "💬" },
      { id: "kb", label: "知识库浏览", icon: "📚" },
      { id: "workflow", label: "工作流状态", icon: "🔀" },
      { id: "docs", label: "文档管理", icon: "📄" },
      { id: "metrics", label: "运行指标", icon: "📊" },
    ];

    const navigate = (id) => {
      store.nav = id;
      store._persist();
      router.push("/" + id);
      emit("close");
    };

    const toggleTheme = () => {
      store.theme = store.theme === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", store.theme);
      store._persist();
    };

    const onApiKeyChange = () => {
      store.apiKey = apiKeyInput.value;
    };

    const checkHealth = async () => {
      store.connected = await api.health();
    };

    watch(
      () => route.path,
      (p) => {
        const id = p.replace("/", "") || "chat";
        if (store.nav !== id) store.nav = id;
      },
      { immediate: true },
    );

    onMounted(() => {
      document.documentElement.setAttribute("data-theme", store.theme);
      checkHealth();
      setInterval(checkHealth, 15000);
    });

    return { store, navItems, navigate, toggleTheme, apiKeyInput, onApiKeyChange };
  },
};
</script>
