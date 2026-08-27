import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './index.css'
import App from './App.tsx'

// 绕过 ngrok 免费版浏览器拦截页（仅同源请求，避免跨域 CORS 预检失败）
const _fetch = window.fetch
window.fetch = (input: RequestInfo | URL, init?: RequestInit) => {
  if (typeof window !== 'undefined' && window.location.hostname.includes('ngrok-free.dev')) {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    const isSameOrigin = url.startsWith('/') || url.includes(window.location.hostname)
    if (isSameOrigin) {
      const headers = new Headers(init?.headers)
      if (!headers.has('ngrok-skip-browser-warning')) headers.set('ngrok-skip-browser-warning', '1')
      return _fetch(input, { ...init, headers })
    }
  }
  return _fetch(input, init)
}

createRoot(document.getElementById('root')!).render(
  <BrowserRouter>
    <App />
  </BrowserRouter>
)
