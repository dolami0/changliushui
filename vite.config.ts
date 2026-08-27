import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// API 代理：前端 /api/* → 后端 Express（文档 §21，uvicorn:8080 的 TS 重建对应物）
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8080',
    },
  },
});
