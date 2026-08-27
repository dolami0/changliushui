import path from "path"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

export default defineConfig({
  base: '/',
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: {
    port: 5174,
    allowedHosts: ['.ngrok-free.dev'],
    proxy: {
      '/api': { target: 'http://localhost:8080', changeOrigin: true },
      '/admin/api': { target: 'http://localhost:8080', changeOrigin: true, rewrite: (p: string) => p.replace(/^\/admin/, '') },
      '/review': { target: 'http://localhost:8080', changeOrigin: true },
    },
  },
});
