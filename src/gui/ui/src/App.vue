<template>
  <div class="toast-container">
    <div v-for="t in toasts" :key="t.id" :class="['toast', t.type]">{{ t.msg }}</div>
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

<script setup>
import { computed, provide, ref } from "vue";
import { useAppStore } from "./store.js";
import Sidebar from "./components/Sidebar.vue";

const { nav } = useAppStore();
const sidebarOpen = ref(false);

/** @type {import('vue').Ref<Array<{id:number, msg:string, type:string}>>} */
const toasts = ref([]);

/**
 * @param {string} msg
 * @param {string} [type="info"]
 */
function toast(msg, type = "info") {
  const id = Date.now();
  toasts.value.push({ msg, type, id });
  setTimeout(() => {
    toasts.value = toasts.value.filter((t) => t.id !== id);
  }, 3000);
}

provide("toast", toast);

const TITLES = { chat: "多轮对话", kb: "知识库浏览", workflow: "工作流状态", docs: "文档管理", metrics: "运行指标" };
const pageTitle = computed(() => TITLES[nav.value] || "");
</script>

<style>
@import "./css/base.css";
@import "./css/layout.css";
</style>
