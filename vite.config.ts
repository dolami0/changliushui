import path from "path"
import fs from "fs"
import react from "@vitejs/plugin-react"
import { defineConfig, type Plugin } from "vite"

const TRACKING_DIR = path.resolve(__dirname, ".agents/agents/shenwaihuashen/memory/tracking")

function trackingApiPlugin(): Plugin {
  return {
    name: "tracking-api",
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        if (!req.url?.startsWith("/api/tracking")) return next()

        res.setHeader("Access-Control-Allow-Origin", "*")
        res.setHeader("Content-Type", "application/json; charset=utf-8")

        const subpath = decodeURIComponent(req.url.replace("/api/tracking", "")) || "/"

        if (subpath === "/" || subpath === "") {
          try {
            if (!fs.existsSync(TRACKING_DIR)) {
              res.statusCode = 200
              res.end(JSON.stringify([]))
              return
            }
            const files = fs.readdirSync(TRACKING_DIR).filter(f => f.endsWith(".json") && f !== "_template.json")
            const stocks = files.map(f => {
              const raw = fs.readFileSync(path.join(TRACKING_DIR, f), "utf-8")
              return JSON.parse(raw)
            })
            res.statusCode = 200
            res.end(JSON.stringify(stocks))
          } catch {
            res.statusCode = 500
            res.end(JSON.stringify({ error: "Failed to read tracking data" }))
          }
        } else {
          const filename = subpath.replace(/^\//, "")
          try {
            const filePath = path.join(TRACKING_DIR, filename)
            if (!fs.existsSync(filePath)) {
              res.statusCode = 404
              res.end(JSON.stringify({ error: "File not found" }))
              return
            }
            const raw = fs.readFileSync(filePath, "utf-8")
            res.statusCode = 200
            res.end(raw)
          } catch {
            res.statusCode = 500
            res.end(JSON.stringify({ error: "Failed to read tracking file" }))
          }
        }
      })
    },
  }
}

// https://vite.dev/config/
export default defineConfig({
  base: './',
  plugins: [react(), trackingApiPlugin()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    allowedHosts: ['.ngrok-free.dev'],
    proxy: {
      '/api': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/review': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
    },
  },
});
