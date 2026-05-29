import path from "path"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

// https://vite.dev/config/
export default defineConfig({
  base: './',
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    allowedHosts: ['.ngrok-free.dev'],
    proxy: {
      // 只读 API → api-server (port 3001)
      '/api': {
        target: 'http://localhost:3001',
        changeOrigin: true,
      },
      // 控制后台 → admin-server (port 3002)
      // 前端/管理页面通过 /admin/api/* 调用
      '/admin': {
        target: 'http://localhost:3002',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/admin/, ''),
      },
      // 审阅 HTML 页面 → admin-server
      '/review': {
        target: 'http://localhost:3002',
        changeOrigin: true,
      },
    },
  },
});
