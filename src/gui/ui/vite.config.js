import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

// 开发模式下把 API 请求代理到本地 FastAPI（默认 9000），
// 避免 npm run dev (5173) 直连同源导致 404。可用 KF_API_TARGET 覆盖。
const apiTarget = process.env.KF_API_TARGET || "http://localhost:9000";

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      "/api/v1": apiTarget,
      "/workflows": apiTarget,
      "/sessions": apiTarget,
      "/collections": apiTarget,
      "/documents": apiTarget,
      "/export": apiTarget,
      "/reload": apiTarget,
      "/status": apiTarget,
      "/ready": apiTarget,
      "/health": apiTarget,
      "/metrics": apiTarget,
    },
  },
  build: { outDir: "dist", assetsDir: "assets" },
});
