import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

// /api 代理目标:
//   默认连本机后端(快、无网络抖动;需先启动 backend: uvicorn app.main:app)
//   想连线上服务器调试时: npm run dev:remote (或设 TS_API_TARGET=http://47.94.235.93)
const API_TARGET = process.env.TS_API_TARGET || "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [vue()],
  build: {
    // 输出覆盖 maxx/frontend/(后端 FRONTEND_DIR / nginx root 均指向它)
    outDir: "../frontend",
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: API_TARGET,
        changeOrigin: true,
      },
    },
  },
});
