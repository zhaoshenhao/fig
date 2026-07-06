<template>
  <div class="toast-container">
    <div v-for="(t, i) in toasts" :key="i" :class="['toast', t.type]">
      {{ t.msg }}
    </div>
  </div>
  <div :class="['sidebar-overlay', { open: sidebarOpen }]" @click="sidebarOpen = false"></div>
  <Sidebar :open="sidebarOpen" @close="sidebarOpen = false" />
  <div class="main">
    <header class="main-header">
      <div style="display:flex;align-items:center">
        <button class="hamburger-btn" @click="sidebarOpen = !sidebarOpen">☰</button>
        <span>KF · 智能客服 v2</span>
      </div>
      <span>{{ pageTitle }}</span>
    </header>
    <div class="main-content">
      <router-view />
    </div>
  </div>
</template>

<script>
import { computed, provide, ref } from "vue";
import { store } from "./store.js";
import Sidebar from "./components/Sidebar.vue";

export default {
  components: { Sidebar },
  setup() {
    const sidebarOpen = ref(false);
    const toasts = ref([]);
    const toast = (msg, type = "info") => {
      const id = Date.now();
      toasts.value.push({ msg, type, id });
      setTimeout(() => {
        toasts.value = toasts.value.filter((t) => t.id !== id);
      }, 3000);
    };
    provide("toast", toast);

    const pageTitle = computed(() => {
      const m = {
        chat: "多轮对话",
        kb: "知识库浏览",
        workflow: "工作流状态",
        docs: "文档管理",
        metrics: "运行指标",
      };
      return m[store.nav] || "";
    });

    return { sidebarOpen, toasts, pageTitle };
  },
};
</script>

<style>
@import "./css/base.css";
@import "./css/layout.css";
</style>
