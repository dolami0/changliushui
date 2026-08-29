## 项目概述
长流水 — 赛博仙门十倍股猎杀系统前端，一个投资分析与估值引擎的可视化平台。

## 技术栈
- **框架**: React 19 + TypeScript
- **构建**: Vite 7
- **样式**: Tailwind CSS 3 + Radix UI 组件库
- **路由**: React Router 7
- **图表**: Recharts
- **动画**: GSAP
- **包管理**: pnpm

## 目录结构
```
/workspace/projects/
├── src/
│   ├── components/       # UI 组件（含 ui/ 组件库子目录）
│   ├── pages/            # 页面组件
│   ├── sections/         # 页面区块
│   ├── hooks/            # 自定义 Hooks
│   ├── services/         # API 服务（cozeApi, memoryApi, valuationApi）
│   ├── lib/              # 工具函数
│   ├── config.ts         # 配置文件
│   └── main.tsx          # 入口
├── public/               # 静态资源
├── dist/                 # 生产构建输出
└── .coze                 # 项目配置
```

## 关键入口 / 核心模块
- `src/App.tsx` — 应用主入口，路由配置
- `src/pages/` — 主要页面（Dashboard, AgentAvatar, Cangjingyun, Tracking 等）
- `src/services/cozeApi.ts` — Coze 工作流 API 集成
- `src/services/valuationApi.ts` — 估值引擎 API 集成

## 运行与预览
- 开发模式: `pnpm dev`
- 生产构建: `pnpm build`
- 预览: `pnpm preview`

## 用户偏好与长期约束
- 项目使用 `pnpm` 管理依赖，禁止使用 npm 或 yarn
- 保持 TypeScript strict 模式，无未使用变量警告
- 优先使用 Radix UI 原语构建组件

## 预览链路配置
- **判断依据**: 这是一个 React + Vite 前端项目，核心价值在于可视化界面交互
- **预览入口**: `scripts/coze-preview-run.sh` → `pnpm exec vite preview`
- **暴露端口**: 5000
- **绑定地址**: 0.0.0.0 (IPv4 全接口)
- **验证状态**: HTTP 200 ✓，监听 0.0.0.0:5000 ✓

## 部署链路配置
- **deploy.build**: `bash scripts/build.sh` — 安装依赖 + Vite 构建
- **deploy.run**: `bash scripts/run.sh` — 使用 serve 提供静态文件 (端口 5000)
- **deploy.profile.kind**: service
- **deploy.profile.flavor**: web

## 追踪令状态管理
- Coze 追踪令表 (DB_TRACKING: `7645332166129287218`) 使用 `track_status` 字段：`active` | `paused`
- `updateTrackStatus(recordId, status)` 调用 Coze PUT API：`PUT /v1/databases/:id/records` + `{ update_fields, filter }`
- 桌面端 `/tracking`：侧边栏列表项和详情页头部均有暂停/恢复按钮
- 移动端 `/m/tracking`：列表页卡片底部有暂停按钮，详情页论点区有切换按钮
- 首页追踪令面板过滤掉 `paused` 记录；侧边栏暂停记录降透明度排底部
