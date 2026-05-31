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
      // ── 只读数据: api-server (Coze) → :3001 ──
      '/api/tracking': { target: 'http://localhost:3001', changeOrigin: true },
      '/api/report': { target: 'http://localhost:3001', changeOrigin: true },
      '/api/reports': { target: 'http://localhost:3001', changeOrigin: true },
      '/api/ranking': { target: 'http://localhost:3001', changeOrigin: true },
      '/api/industry-chain': { target: 'http://localhost:3001', changeOrigin: true },
      '/api/status': { target: 'http://localhost:3001', changeOrigin: true },
      // ── 写入 + 管线控制: Python → :8080 ──
      '/api': { target: 'http://localhost:8080', changeOrigin: true },
      '/review': { target: 'http://localhost:8080', changeOrigin: true },
      '/investoday-market': {
        target: 'https://data-api.investoday.net',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/investoday-market/, '/data/market'),
        headers: { 'User-Agent': 'changliushui/1.0' },
      },
    },
  },
});
