# 长流水 (Changliushui) 开发文档

> 基于估值重构引擎 V8 的完整架构文档，用于重构参考。
> 生成日期: 2026-06-26

---

## 文档导航

### 总体架构

| 文件 | 内容 |
|------|------|
| [00_总体架构.md](00_总体架构.md) | 系统定位、Coze事件板块(天机卷)→调度器→三条管线(A产业链/B预研/C估值)→追踪令、LOOP工程、三阶段演进路线 |

### 配置与集成

| 文件 | 内容 |
|------|------|
| [01_环境配置.md](01_环境配置.md) | 密钥管理、config.json、endpoint_mapping.yaml、Python 依赖、部署 Checklist |
| [02_外部API与搜索模组.md](02_外部API与搜索模组.md) | DeepSeek / investoday / Tushare / 火山引擎 / Bocha / Coze / 新浪 / Playwright 全部 API 规范 |

### 工作流管线

| 文件 | 内容 |
|------|------|
| [03_工作流管线详解.md](03_工作流管线详解.md) | 两条管线的每一步详解（输入/输出/数据变换/错误处理）、评测模式、性能基准 |

### LLM 配置与提示词存档

| 文件 | Agent | LLM | 核心内容 |
|------|-------|-----|---------|
| [llm_configs/01_Agent0_预路由.md](llm_configs/01_Agent0_预路由.md) | Agent-0 | 无 (规则引擎) | 行业→数据包映射、事件标签→优先级提升 |
| [llm_configs/02_Agent_Baseline_投资地图.md](llm_configs/02_Agent_Baseline_投资地图.md) | Baseline | deepseek-v4-pro | 六维投资地图 System Prompt |
| [llm_configs/03_Agent1_数据锻造.md](llm_configs/03_Agent1_数据锻造.md) | Agent-1 | 无 (数据抓取) | 30+ 端点并行抓取、8 项交叉验证 |
| [llm_configs/04_Agent2_统一路由判官.md](llm_configs/04_Agent2_统一路由判官.md) | Agent-2 | deepseek-v4-pro | 6 步推理链、10 模型目录、完整 System Prompt |
| [llm_configs/05_Agent3_情景估值_LLM1.md](llm_configs/05_Agent3_情景估值_LLM1.md) | Agent-3 LLM-1 | deepseek-v4-pro | 三情景推演、CAGR 拆解、参数锚定法则、完整 System Prompt |
| [llm_configs/06_Agent3_情景估值_LLM2.md](llm_configs/06_Agent3_情景估值_LLM2.md) | Agent-3 LLM-2 | deepseek-v4-pro | 审阅+多轮搜索、事件锚校验、前瞻信号验证、公司声明解读框架、完整 System Prompt |
| [llm_configs/07_PreScreen_预筛关卡.md](llm_configs/07_PreScreen_预筛关卡.md) | PreScreen | deepseek-v4-flash | 4 维评分、Fail-open 设计、拦截规则 |
| [llm_configs/08_Coze工作流_万业谱预研.md](llm_configs/08_Coze工作流_万业谱预研.md) | Coze 工作流 | deepseek-v4-flash ×18 | 8 节点 DAG、5 字段探针设计、总装+去重+交叉验证 |
| [llm_configs/09_产业链分析工作流.md](llm_configs/09_产业链分析工作流.md) | 产业链分析 | deepseek-v4-pro + flash | 8 步管线、5 维利润截留评估、42 例 V3 案例库、四维赔率评分 |
| [llm_configs/10_SOTP_rNPV_分支管线.md](llm_configs/10_SOTP_rNPV_分支管线.md) | SOTP / rNPV | deepseek-v4-pro | 分部估值参数体系、rNPV 公式、创新药管线评估 |

---

## 阅读顺序建议

**首次了解系统**:
1. `00_总体架构.md` → 建立全局认知
2. `03_工作流管线详解.md` → 理解每一步的数据变换
3. `01_环境配置.md` + `02_外部API与搜索模组.md` → 了解基础设施

**重构 LLM 提示词**:
1. 先读 `04_Agent2_统一路由判官.md` (路由是管线的决策中枢)
2. 再读 `05_Agent3_情景估值_LLM1.md` + `06_Agent3_情景估值_LLM2.md` (估值核心)
3. 其他按需阅读

**重构数据层**:
1. `03_Agent1_数据锻造.md` (investoday + Tushare 双源)
2. `02_外部API与搜索模组.md` (所有 API 规范)

**重构事件→语料的预研管线**:
1. `08_Coze工作流_万业谱预研.md` (Coze DAG)
2. `09_产业链分析工作流.md` (产业链利润流)

---

## 关键源文件映射

| 文档 | 对应源文件 |
|------|-----------|
| 00_总体架构 | `src/orchestrator.py` (编排器) |
| Agent-0 | `src/agent0_pre_router.py` (280 行) |
| Agent-1 | `src/agent1_data_forge.py` (789 行) |
| Agent-2 | `src/agent2_unified.py` (995 行) |
| Agent-3 | `src/agent3_scenario_asymmetry.py` (4161 行) |
| Baseline | `src/agent_baseline.py` (508 行) |
| PreScreen | `src/pre_screen_gate.py` (455 行) |
| 数据获取 | `src/data_fetcher.py` (1315 行) |
| Tushare | `src/tushare_fetcher.py` (350 行) |
| LLM 工具 | `src/valuation_utils.py` (254 行) |
| 定价工具 | `src/pricing_tools.py` (257 行) |
| 前瞻信号 | `src/forward_indicator_computer.py` (974 行) |
| 环境配置 | `src/env_config.py` (38 行) |
| 产业链分析 | `src/industry_chain_workflow.py` (1594 行) |
| Coze 工作流 | `src/coze_workflow/` (8 个文件) |
| SOTP | `src/agent3s_sotp.py` (2475 行) |
| rNPV | `src/rnpv/` (2 个文件) |
| 审计 | `src/review/` (4 个文件) |
| API 映射 | `config/endpoint_mapping.yaml` (389 行) |
