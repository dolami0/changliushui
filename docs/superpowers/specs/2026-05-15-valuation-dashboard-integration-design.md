# 长流水 × 估值重构引擎整合 — 设计文档

## 目标

将 Python 估值重构引擎 V4 的仪表盘和 HTML 报告以 React 页面形式整合进长流水前端，统一设计语言。

## 原则

- 不修改任何已有页面、组件、特效、配置数据
- 新增路由和页面，沿用长流水设计语言
- Python 后端退为纯 API + 管线引擎，新增必要 API 端点

## 架构

```
React 前端 (Vite :5173)
├── /                   首页 (已有)
├── /facility/:slug     机构详情 (已有)
├── /report/:id         预研报告 (已有，Coze源)
├── /report/v4/:code    估值报告 (新增 — Python管线产出)
├── /dashboard          实时仪表盘 (新增)
├── /agent-config       身外化身配置 (已有)
└── /avatar             身外化身推演 (已有)
         │  HTTP/SSE
         ▼
Python 后端 (FastAPI :8081)
├── /api/status                 调度器状态
├── /api/progress/stream        SSE 实时进度
├── /api/trigger                手动触发轮询
├── /api/scheduler/start|stop   调度器启停
├── /api/scheduler/interval     设置轮询间隔
├── /api/scheduler/status       调度器详细状态
└── /api/report/:code/data      报告结构化数据 (新增)
```

## 新增文件

- `src/pages/Dashboard.tsx` — 实时监控仪表盘
- `src/pages/ValuationReport.tsx` — 估值报告查看页
- `src/services/valuationApi.ts` — Python 后端 HTTP/SSE 封装

## 修改文件

- `src/App.tsx` — 新增两条路由
- `估值重构引擎_V4/valuation_app/server.py` — 新增报告数据 API + CORS 配置

---

## Dashboard 页面设计

### 布局

- 粘性导航栏 (同 AgentConfig 风格)
- 标题区：Geist Pixel "估值重构炉 · 实时监控" + 副标题
- 状态卡片行 (4列)：SSE连接 / 调度状态 / 上次轮询 / 下次轮询
- 控制面板：启动/停止/触发按钮 + 轮询间隔预设按钮组
- 活跃任务区：进度条 + 任务卡片
- 已完成列表：历史记录卡片

### 设计规范

| 元素 | 规格 |
|------|------|
| 背景 | #050401 |
| 标题字体 | Geist Pixel, #ADFF00, textShadow 发光 |
| UI 字体 | Space Mono, 11-13px |
| 正文 | IBM Plex Mono + Noto Sans SC |
| 卡片底色 | rgba(255,255,255,0.03) |
| 卡片边框 | 1px solid rgba(255,255,255,0.06) |
| 卡片 hover | 边框变 rgba(173,255,0,0.2)，底色微提 |
| 主要强调 | #ADFF00 (荧光绿) |
| 警告/错误 | #FF5C00 (警示橙) |
| 状态圆点 | 8px, #ADFF00 pulse 动画 (活跃) / #666 (闲置) |
| 进度条 | 深色底轨 rgba(255,255,255,0.06) + #ADFF00 填充 |
| 分隔线 | #2A2A2A |
| 按钮主色 | #ADFF00 文字, 背景透明, 边框 rgba(173,255,0,0.25) |
| 按钮危险 | #FF5C00 文字 |
| 入场动画 | GSAP fadeUp + stagger |

### 数据交互

- SSE EventSource → `/api/progress/stream`
- 状态轮询 GET `/api/status` (10s间隔)
- 控制 POST `/api/trigger`, `/api/scheduler/start|stop`, `/api/scheduler/interval`

---

## 估值报告页面设计

### 布局

- 粘性导航栏
- 报告头部：股票名 + 代码 + 元数据
- TOC 导航条
- 区块滚动：
  1. 执行摘要 (大数字 + 情景概率条 + 市值箭头)
  2. BS检测器 (反向DCF 数据表)
  3. 三情景推演 (表格)
  4. 案例比对校准 (6维矩阵)
  5. 置信度评分 (维度条)
  6. 交易标注 (S1-S4 评分)
  7. KPI追踪 / 事件时间线
  8. 叙事

### 设计规范

同仪表盘，额外规范：

| 元素 | 规格 |
|------|------|
| 大数字涨幅 | Geist Pixel, #ADFF00 (正) / #FF5C00 (负) |
| 情景概率条 | 三色：Bear #FF5C0055 / Base #666 / Bull #ADFF0055 |
| TOC 标签 | Space Mono, 11px, hover #ADFF00 |
| 评分维度条 | 细横条 5px, 深底轨 + #ADFF00/#FF5C00 填充 |

### 数据获取

- GET `/api/report/{stock_code}/data` → JSON → React 渲染

---

## Python 后端改动

### 新增 API

```python
@app.get("/api/report/{stock_code}/data")
async def get_report_data(stock_code: str):
    # 从 Coze 输出表查询该股票的管线处理结果
    # 返回结构化 JSON（包含 Agent1/2/3 全部字段）
    # 如果未找到返回 404
```

返回数据结构：Agent0 投资分析、Agent1 财务全景/BS检测/估值路由/WACC、Agent2 事件传导/参数推演/案例比对/校验、Agent3 预期差/置信度/交易标注/KPI/时间线/叙事。

### CORS

添加 CORS 中间件，允许 Vite 开发服务器跨域请求。

### 原则

- 不影响已有管线逻辑
- 不影响调度器行为
- 不影响原有路由 (`/dashboard`, `/report/:code` HTML 版保持可用)

---

## 技术约束

- 开发环境：Vite dev server + FastAPI 同时运行，CORS 处理跨域
- 生产环境：`vite build` 产出放到 FastAPI StaticFiles 挂载，或独立部署
- SSE 连接：只在新页面挂载时建立，离开时关闭
- 不引入新依赖（使用已有的 React 19 / GSAP / Tailwind / react-router-dom）
