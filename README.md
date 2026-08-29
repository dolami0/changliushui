# 长流水

赛博仙门主题的事件驱动与个股估值选股平台。从产业资讯筛选定价合理、上涨空间较大的标的，输出情景估值报告（定数录），再用追踪令持续监控。

核心理念：不是预测股价，而是判断市场定价中隐含的预期是否合理。LLM 做分类、推理、搜索编排；算术由代码执行。投研辅助，不构成投资建议。

生产前端来自 dolami0/valuation-engine-frontend（master）：React 19 + Vite 7 + Tailwind + react-router。仓库 dolami0/changliushui-3.0 是独立实验版本，不是本仓库的前端。

## 系统怎么跑

1. 事件写入天机卷（Coze DB 7479116110479048754）。来源：bstudio 自动监控，或前端人工投喂。
2. Python 调度器 估值重构引擎_V5/valuation_app/scheduler.py 轮询天机卷（默认约 1800 秒，可手动触发）。
3. 产业模式走管线 A（industry_chain_workflow.py），结果进因果簿/望气，最优个股汇入管线 B。
4. 个股模式走管线 B 万业谱预研（wanyepu_pipeline.py 或 Coze DAG），写入万业谱 DB 7639784337973477386。
5. 管线 C orchestrator.py：Agent-0 预路由、Agent-1 数据锻造、Baseline、Agent-2 路由、Agent-3 情景估值（LLM 出参数，代码算估值，LLM 再审阅）。
6. 摘要写入定数录 DB 7640094415800860724；完整 JSON 写入报告 V6 DB 7644911309938589711。
7. 身外化身复核后进入追踪令 DB 7645332166129287218。

外部数据：DeepSeek、investoday、Tushare、火山引擎、Bocha、Coze、新浪。FastAPI 默认 8080。前端 Vite 开发代理见 vite.config.ts（/api 指向 localhost:3002）。

## 前端与 Coze 表

浏览器通过 src/services/cozeApi.ts 访问 api.coze.cn。Token 使用 VITE_COZE_TOKEN（见 .env.example，勿提交 .env）。

- 藏经阁 7611455655748304896 旧预研
- 天机卷 7479116110479048754 事件入口
- 万业谱 7639784337973477386 五维语料
- 定数录 7640094415800860724 估值摘要
- 因果簿 7640928034144698374 产业链/望气
- 报告V6 7644911309938589711 按 Agent 拆分报告
- 追踪令 7645332166129287218 持仓论点
- 灵光 7645332554400153646 投资笔记
- 案例 7645333715039830079 十倍股案例

调度器、审阅、产业链启停走 /api。桌面路由：首页、藏经云、看板、天机峰、追踪令、身外化身、报告；移动端 /m/*。

## 仓库布局

- src/ ：生产前端（valuation-engine-frontend）
- scripts/ ：Coze 预览与部署（pnpm）
- 估值重构引擎_V5/ ：Python 管线与 FastAPI
- docs/ ：架构与使用手册
- reports/ ：示例报告
- .env.example ：前端 VITE_COZE_TOKEN 模板；引擎模板在 估值重构引擎_V5/.env.example

根目录 batch_upload.py、fix_ts.py、pack_clean.py 是本地一次性脚本，未改入口。changliushui-frontend、valuation-engine-frontend、valuation-engine-ts 是没有 .gitmodules 的 gitlink，未删除。

## 怎么跑

前端：pnpm install 然后 cp .env.example .env 然后 pnpm dev

后端：进入 估值重构引擎_V5 ，cp .env.example .env ，pip install -r requirements.txt ，然后 python -m uvicorn valuation_app.server:app --host 0.0.0.0 --port 8080

密钥优先级：环境变量大于 .env 大于 valuation_app/config.json（后者已被 gitignore）。详见 docs/01_环境配置.md。不要把 .env 提交进仓库。

## 文档

- docs/00_总体架构.md
- docs/01_环境配置.md
- docs/03_工作流管线详解.md
- docs/用户使用手册.md

未启用 GitHub Pages。仓库首页就是本 README。index.html 是 Vite 入口，不是营销页。
