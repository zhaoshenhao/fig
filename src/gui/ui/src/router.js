import { createRouter, createWebHashHistory } from "vue-router";
import ChatPage from "./pages/ChatPage.vue";
import KBBrowserPage from "./pages/KBBrowserPage.vue";
import WorkflowStatusPage from "./pages/WorkflowStatusPage.vue";
import DocManagementPage from "./pages/DocManagementPage.vue";
import MetricsPage from "./pages/MetricsPage.vue";
import DashboardPage from "./pages/DashboardPage.vue";
import StatusPage from "./pages/StatusPage.vue";

const routes = [
  { path: "/", redirect: "/chat" },
  { path: "/chat", component: ChatPage },
  { path: "/kb", component: KBBrowserPage },
  { path: "/workflow", component: WorkflowStatusPage },
  { path: "/docs", component: DocManagementPage },
  { path: "/metrics", component: MetricsPage },
  { path: "/dashboard", component: DashboardPage },
  { path: "/status", component: StatusPage },
];

export const router = createRouter({ history: createWebHashHistory(), routes });
