# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

长流水 — 赛博仙门主题的十倍股猎杀系统前端。暗黑单色调 + 霓虹绿 (#ADFF00) 点缀，所有交互文案融入修仙隐喻（天眼司、估值殿、追踪司等十司宗门机构）。

## 常用命令

```bash
npm run dev          # 启动 Vite dev server（端口 5173）
npm run build        # TypeScript 类型检查 + Vite 生产构建
npm run lint         # ESLint 9 flat config 检查
npm run preview      # 预览生产构建
```

无测试命令（项目当前无测试框架）。

## 技术栈

- **React 19** + **TypeScript 5.9**（strict 模式）
- **Vite 7**（路径别名 `@/` → `./src/`，base `'./'` 相对路径）
- **Tailwind CSS 3**（class 暗色模式，`tailwindcss-animate`，shadcn/ui HSL CSS 变量主题）
- **React Router 7**（客户端路由，SPA 需 fallback 到 index.html）
- **GSAP** + ScrollTrigger（页面过渡、滚动动画）
- **Radix UI**（无样式原语）+ **shadcn/ui** 组件（位于 `src/components/ui/`，~40+ 组件）
- **Recharts**（图表）
- **react-hook-form** + **zod** + **@hookform/resolvers**（表单验证，AgentConfig 重度使用）
- **sonner**（Toast 通知）、**lucide-react**（图标）、**cmdk**（命令面板）
- **next-themes**（暗色模式切换）、**embla-carousel-react**（轮播）、**date-fns**（日期处理）
- **Geist** 字体包（Geist Pixel 用于标题）

### TypeScript 配置要点

- 三层 tsconfig：`tsconfig.json`（引用文件）→ `tsconfig.app.json`（应用代码）+ `tsconfig.node.json`（Vite/构建工具）
- `verbatimModuleSyntax: true` — 类型导入必须使用 `import type`，值导入和类型导入不可混用
- `erasableSyntaxOnly: true` — 只允许可擦除的类型语法（禁用 enum、带值的 namespace 等）
- `noUnusedLocals` / `noUnusedParameters` 开启，未使用变量会导致编译失败

### ESLint

ESLint 9 flat config（`eslint.config.js`），非旧版 `.eslintrc` 格式。包含 `reactHooks` 和 `reactRefresh` 插件。

## 项目架构

```
src/
├── main.tsx              # 入口：BrowserRouter + App
├── App.tsx               # 路由定义，GSAP 页面过渡，全局光标
├── config.ts             # 【核心】所有可编辑内容集中于此，类型安全的接口定义
├── index.css             # 全局样式，CSS 变量（shadcn/ui HSL 主题），自定义动画，点阵底纹
├── sections/             # 首页各区块（仅用于 / 路由）
│   ├── Hero.tsx          #   ASCII 月球 + 标题，40/60 分栏
│   ├── Facilities.tsx    #   宗门机构四列网格
│   ├── Archives.tsx      #   3D 轮播（藏经阁/藏经云）
│   ├── Manifesto.tsx     #   视频 + 文本宣言
│   ├── Observation.tsx   #   实时观测信号面板
│   └── Footer.tsx        #   全站页脚
├── pages/                # 独立路由页面
│   ├── Dashboard.tsx     #   总控台：SSE 进度流，调度器开关，审阅
│   ├── ValuationReport.tsx # 估值重构报告 V5 渲染器
│   ├── FacilityDetail.tsx  # 机构详情页
│   ├── AgentConfig.tsx   #   Agent 配置（最重，~54KB）
│   ├── AgentAvatar.tsx   #   身外化身交互
│   ├── AvatarCC.tsx      #   身外化身 CC 版
│   ├── TianjiPeak.tsx    #   天机峰：产业链分析
│   ├── IndustryChain.tsx #   产业链利润流
│   └── Tracking.tsx      #   追踪令：个股追踪面板（读取 tracking/ 目录）
├── components/           # 可复用组件
│   ├── ui/               #   shadcn/ui 组件库
│   ├── AsciiCanvas.tsx   #   ASCII 字符画布
│   ├── GlitchText.tsx    #   故障效果文字
│   ├── FloatingAvatar.tsx #  浮动头像
│   └── CustomCursor.tsx  #   自定义十字光标（移动端自动隐藏）
├── services/             # API 服务层
│   ├── valuationApi.ts   #   估值引擎：/api/*，SSE 流，天机/望气
│   ├── cozeApi.ts        #   Coze 云数据库：五大古籍库 CRUD
│   ├── memoryApi.ts      #   记忆 API
│   └── agentMemory.ts    #   Agent 记忆持久化
├── hooks/                # 自定义 Hooks
│   ├── useMobile.ts      #   响应式断点（768px）
│   └── useBackendHealth.ts # 后端存活 30s 心跳检测
└── lib/
    └── utils.ts          # cn() 工具函数（clsx + tailwind-merge）+ renderMarkdown()
```

## 路由表

| 路由 | 页面 | 说明 |
|------|------|------|
| `/` | Home | 首页：Hero + Facilities + Footer |
| `/facility/:slug` | FacilityDetail | 机构详情 |
| `/report/:code` | ValuationReport | V4/V5 估值报告 |
| `/report/v4/:code` | ValuationReport | V4 估值报告 |
| `/dashboard` | Dashboard | 总控台（调度器 + SSE） |
| `/cangjingyun` | Archives | 藏经云 |
| `/agent-config` | AgentConfig | Agent 配置 |
| `/avatar` | AgentAvatar | 身外化身 |
| `/avatar-cc` | AvatarCC | 身外化身 CC |
| `/tianjifeng` | TianjiPeak | 天机峰 |
| `/tracking` | Tracking | 追踪令：个股追踪面板 |

## 核心设计约定

### 配置驱动
所有可编辑内容在 `src/config.ts` 中通过类型安全的接口定义。`FacilityItem` 包含修仙主题特有字段：`status: 'cultivating' | 'meditating' | 'alchemy'`、`name`、`role`、`task`、`statusTextCN`。当前宗门页展示十大机构：天机峰四司（天眼司 TY-01/望气台 WQ-02/寻龙殿 XL-03/妙音阁 MY-04）+ 估值殿 VH-05 + 追踪司 TB-06 + 总控台 OP-07 + 身外化身 AV-08 + 藏经阁 CJ-09 + 炼器房 LQ-10。改文案、导航、配置时只改此文件，不要深入组件内部。

### 视觉系统
- **色板**：底色 `#050401`（近黑）、主文字 `#F2F4F3`（白）、主强调 `#ADFF00`（霓虹绿）、辅助强调 `#FF5C00`（橙）、金色 `#C88D3A`
- **主题系统**：采用 shadcn/ui 的 HSL CSS 变量模式。`index.css` 的 `:root` 定义亮色主题变量，`.dark` 类覆写为暗色。Tailwind 的 `color` 配置全部映射到 CSS 变量（如 `primary: "hsl(var(--primary))"`），因此修改主题色只需改 CSS 变量，无需改 Tailwind 配置
- **字体**：Geist Pixel → 标题/数字；IBM Plex Mono + Noto Sans SC → UI/正文；Space Mono → 表格/代码；Fragment Mono → ASCII
- **动画**：GSAP 处理复杂过渡，CSS `@keyframes` 处理呼吸/流光/符文循环动画
- **光标**：全局自定义十字光标（`CustomCursor`），移动端（<768px）自动回退系统光标
- **底纹**：`body::before` 全局点阵叠加层

### API 设计

开发环境有两套 API 机制，互不重叠：

| 路径前缀 | 机制 | 目标 |
|---------|------|------|
| `/api/*`（除 `/api/tracking`） | Vite proxy | `localhost:8080`（Python FastAPI 估值引擎） |
| `/review/*` | Vite proxy | `localhost:8080` |
| `/api/tracking` | Vite 内置插件 `trackingApiPlugin` | 本地文件系统 `.agents/agents/shenwaihuashen/memory/tracking/*.json` |
| Coze API | 直连 | `api.coze.cn`（Bearer token，不走 Vite proxy） |

SSE 端点 `/api/progress/stream` 用于实时进度推送。生产环境需反向代理或同源部署。

### 状态管理
无全局状态库。页面间通过 URL params 和 `useParams` 传递数据，页面内用 `useState` + `useEffect` 管理本地状态。

### 移动端适配
`useMobile()` hook 检测 768px 断点。网格布局通过 CSS 媒体查询切换为单列。自定义光标在移动端自动禁用。

## 注意事项

- `README.md` 是原始模板 "6 Ascii Moon" 的遗留文档，已过时，以本文件为准
- `src_backup_20260521/` 和 `src_v1.0/` 是历史备份，不要修改
- 估值重构引擎后端代码位于同级目录 `估值重构引擎_V5/`
- Coze token 通过环境变量 `VITE_COZE_TOKEN` 注入，详见 `.env.example`
- SPA 部署需配置 fallback 到 `index.html` 以支持客户端路由
- `.claude/launch.json` 已配置 `dev-server`（端口 5173），可使用 `preview_start("dev-server")` 启动
