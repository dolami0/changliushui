# 身外化身 Skill 体系 v2.3

## 核心分析哲学

**达摩达兰双驱动**：Numbers（财务数据）+ Narrative（变革叙事）双驱动。上游给的是事件驱动的投资线索，必有变革发生。你的任务是用 tushare 分产品数据拆解旧业务和新业务，验证叙事是否被数据支撑。

## 数据验证铁律

```
每次拉取数据 → 自动异常检测 → 异常触发交叉验证 → 三重确认后才纳入分析
```

**异常检测**：
- 分产品毛利率 > 90% → 自动标记，触发 investoday + WebSearch 交叉验证
- `bz_cost` = 0 或接近 0 → tushare 数据异常，切换数据源
- 利润贡献 > 50% 但收入占比 < 10% → 查年报附注确认业务实质

**交叉验证链**：tushare → investoday → WebSearch 年报附注 → 手动标注不确定性

**上游校准**：定数录和藏经阁也会犯错——关键数据（毛利率、质押率、分产品属性）必须独立验证，不能直接引用。

## 工作模式

```
用户输入：标的分析上下文 (藏经阁 + 定数录 + 灵光 + 案例)
    ↓
身外化身：tushare拉取 → 异常自动标记 → 交叉验证 → 纠错上游 → 双驱动判断
    ↓
输出：交易策略 + 追踪档案
```

## Skill 全景

| # | Skill | 步骤 | Anthropic 原始 | 使用状态 |
|---|-------|------|---------------|---------|
| 1 | `data-verify` | Step 1 | — | ✅ 活跃（tushare + investoday + WebSearch 三重交叉） |
| 2 | `industry` | Step 2 | competitive-analysis + sector-overview | ✅ 活跃（产业链定位/竞争格局/TAM/供需） |
| 3 | `financial` | Step 3 | earnings-analysis | ✅ 活跃（分产品拆解+四维诊断+达摩达兰双驱动） |
| 4 | `valuation` | Step 4 | comps-analysis + dcf-model | ✅ 活跃（绝对/相对/情景/预期差/BS检测器） |
| 5 | `case-match` | Step 5 | — | ✅ 活跃（42案例库6维比对+折扣率） |
| 6 | `catalyst` | Step 6 | catalyst-calendar | ✅ 活跃（催化剂日历+拐点识别） |
| 7 | `decision` | Step 7+8 | idea-generation | ✅ 活跃（灵光校准+风险扫描+交易策略输出） |
| 8 | `thesis` | Step 9+追踪 | thesis-tracker | ✅ 活跃（论点建立+评分卡+持续更新） |
| 9 | `evolve` | 定期 | — | ✅ 活跃（复盘偏差+灵光更新+案例追加） |

## Anthropic 框架使用详情

### 已深度集成（方法论直接嵌入决策步骤）

| Anthropic Skill | 集成位置 | 如何使用的 |
|----------------|---------|-----------|
| **competitive-analysis** | Step 2 industry | 五力模型→卡位评级，竞争矩阵→行业集中度分析。数据源从 SEC/Bloomberg 适配为 tushare/券商研报/WebSearch |
| **sector-overview** | Step 2 industry | TAM估算框架、行业结构（分散/集中）、趋势分析、价值链分配。A 股 TAM 引用券商研报 |
| **earnings-analysis** | Step 3 financial | 四维诊断框架（成长/盈利/现金流/健康）。10-K→年报，GAAP→中国会计准则。最关键适配：加入分产品拆解，区分新旧业务 |
| **comps-analysis** | Step 4 valuation | 同业可比公司表（PE/PB/ROE/毛利率/营收增速/市值）。美股可比→A股同业，估值倍数调整为A股惯例 |
| **dcf-model** | Step 4 valuation | DCF 方法论→BS检测器的反向DCF（隐含g计算）。保留 WACC 框架，参数适配 A 股 |
| **catalyst-calendar** | Step 6 catalyst | 事件分类（财报/公司/行业/政策/市场），Bull/Bear 触发器。FDA→NMPA/发改委/工信部 |
| **thesis-tracker** | Step 9 thesis | 论点→支柱→评分卡→催化剂日历→价格日志。增加 A 股特有项：质押率、解禁日期、两融监控 |
| **initiating-coverage** | 参考 | 5 步首次覆盖流程的方法论参考，格式标准（Times New Roman→中文报告标准） |

### 未使用（美股/欧美市场专属）

| Anthropic Skill | 不适用原因 |
|----------------|-----------|
| lbo-model | LBO 在美国 PE 收购中常用，A 股几乎不存在 |
| morning-note | 美股晨会简报格式，A 股交易时段不同 |
| earnings-preview | 依赖美股 consensus estimate 生态，A 股分析师预测覆盖不充分 |
| model-update | 依赖 SEC EDGAR 实时 filing，A 股无等效系统 |
| screen | 美股筛选标准，A 股需适配涨跌停/ST/流动性规则 |
| ib-check-deck / deck-refresh / ppt-template-creator | 投行 PPT 制作工具，非分析框架 |

### 方法论存档

完整的 Anthropic 原始 SKILL.md 保存在 `~/.claude/plugins/` 下：
- `financial-analysis/skills/` — 13 个 Skill 原文
- `equity-research/skills/` — 9 个 Skill 原文

需要时可以直接查阅原文的方法论细节。

## 数据拉取清单

每次决策前必须拉取：

```bash
# 基础——每次必拉
python data_helper.py valuation <code>    # 估值快照
python data_helper.py segment <code>      # 分产品拆解（事件驱动标的必查）
python data_helper.py pledge <code>       # 质押（风控铁律）

# 深度——按需
python data_helper.py income <code> 8     # 利润趋势
python data_helper.py fina <code> 8      # 财务指标趋势
python data_helper.py top10 <code>       # 十大股东
```

## 决策执行规则

1. **Step 1-5 不可跳过**，Step 6（catalyst）在催化剂不密集时可跳过
2. **Step 2-5 可并行**（独立分析维度）
3. **Step 7 在 Step 1-6 之后**，Step 8 在 Step 7 决定非否决后执行
4. 跳过某步时必须在报告中说明原因
5. **分产品数据拉取是事件驱动标的的强制步骤**——如果标的有新业务/新产品叙事，不拉 segment = 方法论不完整
