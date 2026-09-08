import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

// /api 代理目标:
//   默认连线上服务器(建的用户等数据都落在服务器库,与 http://47.94.235.93 同源)
//   想连本机后端调试时: npm run dev:local (或设 TS_API_TARGET=http://127.0.0.1:8000)
const API_TARGET = process.env.TS_API_TARGET || "http://47.94.235.93";

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
