"""
产业链利润流分析器 — 双Pass LLM架构

Step 1: DeepSeek LLM #1 (flash+bocha) — 产业链推理 → 前2节点
Step 2: Volc联网搜索 — 每节点1个query (并行)
Pass 1:
  Step 3: LLM #2 (flash) — 提名节点1候选股(仅名称,无代码)
  Step 3.5: tushare 按名称校验真实代码
  Step 4: tushare市值/PE/财务指标 + Volc个股投资地图 (并行)
  Step 5: LLM #2 (v4-pro) — 四维评分(黑洞/弹射+连续光谱+裁量权)
  ├─ best >= 6.5 → 输出
  └─ best < 6.5 → Pass 2:
      Step 7: 提名节点2候选股
      Step 7.5: tushare 代码校验
      Step 8: 数据富化
      Step 9: 混合评分 → 输出
"""

import json, re, time, requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

from data_fetcher import DataFetcher
from env_config import VOLC_AGENT_KEY
from agents.tools import bocha_search, TOOL_DEFINITIONS, TOOL_MAP

# ═══════════════════════════════════════
# API 配置
# ═══════════════════════════════════════
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-v4-pro"
DEEPSEEK_MODEL_FAST = "deepseek-v4-flash"  # 统一用 Flash 开思考
BOCHA_TOOLS = [t for t in TOOL_DEFINITIONS if t["function"]["name"] in ("bocha_search", "fetch_url")]
VOLC_URL = "https://open.feedcoopapi.com/agent_api/agent/chat/completion"
VOLC_BOT_ID = "7640524154441156122"

# ═══════════════════════════════════════
# LLM #1 — 产业链节点利润截留分析
# ═══════════════════════════════════════
LLM1_PROMPT = """你是产业链利润流分析师。你的任务是通过自主搜索，判断产业链上哪些节点截取最多利润，输出前2个节点。

# 工作流程

使用 bocha_search 搜索。搜索结果中标题看起来关键、但摘要太短（<300字）或缺少具体数字的，必须用 fetch_url 点进去读全文。每次操作后暂停，判断信息是否足够：

维度覆盖清单：
1. 产业链结构 — 上游/中游/下游各环节及核心公司
2. 利润分配 — 哪个环节毛利率最高、截留利润最多
3. 竞争格局 — 各环节的集中度、头部公司市场份额
4. 进入壁垒 — 认证周期、客户绑定、技术门槛
5. 需求弹性 — 事件对哪个环节拉动最大
6. 市场容量(TAM) — 每个节点的国内/全球市场规模，必须搜索到具体数字或合理估算

搜索策略：
- 先搜最关键的1-2个维度，读结果后判断是否还需补充
- 信息充分就停止搜索，不必用完所有轮次
- 最多5轮，第5轮后必须输出最终JSON
- 所有维度覆盖完毕后，交叉验证，输出完整报告

# 分析框架：5维度利润截留评估

1. 议价能力 — 该节点对上游能否压价？对下游能否提价？
2. 集中度 — 寡头还是散兵？集中才能留住利润
3. 转换成本 — 客户换供应商有多难？（认证周期/产线绑定/监管壁垒）
4. 增值比例 — 该节点贡献最终产品价值的百分之几？
5. 需求弹性 — 事件直接拉动该节点需求，还是间接蹭到？

# 隐性上游优先原则

产业链利润往往向"隐性上游"集中——即体积小、价值密度高、认证壁垒极强的上游环节（芯片、特种材料、核心元器件），而非显眼的中游总装。分析时重点关注：
- 若某上游环节占下游成品成本<5%但断供即瘫痪 → 利润截留极高（如宇航芯片、高速光芯片）
- 中游总装即使产值大，若竞争分散、切换成本低，利润截留反而不如隐性上游
- 不要无限向上游追溯：只考虑一阶直接供应商

# 节点命名规则
节点名必须包含「产业链具体环节+行业定语」。

# 证据纪律
对每个维度的评分，必须标注证据来源。搜索过程中找到的引用为"搜索发现"，需附带具体数据+来源；基于搜索发现的逻辑推理为"推断"，需标注"推断"及推理链条。绝对禁止没有任何证据基础的评分——实在搜不到的维度标注"未找到直接证据"。

# 最终输出JSON（搜索完成后输出，不要用markdown包裹）
{
  "chain_overview": {"industry":"","event_summary":"","nodes":[{"name":"","position":"upstream/midstream/downstream","key_products":[]}]},
  "profit_flow_analysis": [{"node_name":"","position":"","bargaining_power":"high/medium/low","concentration":"high/medium/low","switching_cost":"high/medium/low","value_add_ratio_pct":0,"demand_elasticity":"high/medium/low","profit_retention_score":0,"rationale":"","tam_estimate":"节点国内/全球市场规模(亿元)+数据年份+来源","evidence":{"concentration":"搜索发现或推断: 具体数据/推理链+来源","bargaining_power":"","switching_cost":"","value_add_ratio_pct":"","demand_elasticity":"","tam":"搜索发现或推断: 市场容量数据+来源"}}],
  "top_two_nodes": [{"node_name":"","position":"","profit_retention_score":0,"tam_estimate":"","justification":"","what_to_look_for":"此节点内什么特征的公司会胜出（必须结合此具体行业写，不要泛泛而谈）","key_risk":""}]
}"""

# ═══════════════════════════════════════
# LLM #2 — 个股赔率评分
# ═══════════════════════════════════════
LLM2_NOMINATE_PROMPT = """你的任务：为指定产业链节点找出最相关的A股上市公司，按关联度排序输出前5只。

# 工作方式（严格按顺序执行）
1. 从Volc搜索结果中提取所有主营业务直接属于目标节点的A股公司
2. 从原始资讯、Agent0分析、背景知识中找出所有被提及的该节点公司
3. 合并去重后，按与节点的关联度排序（主营越纯正越靠前）
4. 上述来源合计不足5只时，用你的A股知识补充到5只（该行业知名公司）
5. 确保最终输出恰好5只

# 关联度判断标准
- 第一梯队：公司主营产品就是该节点的核心产品，资料中明确描述
- 第二梯队：公司业务部分覆盖该节点，资料中有提及
- 第三梯队：公司是该节点知名A股标的（用你的知识补充）
- 排除：纯概念炒作、跨行业蹭热点、主营完全不沾边

# 注意
- 不需要判断市值大小、赔率高低 — 那是后续评分环节的工作
- 不需要填股票代码，只需输出公司简称（如"云南锗业"）
- 必须恰好输出5只，不足时必须用你的A股知识补足

# 输出JSON
{
  "nominations": [
    {"stock_name":"公司简称","node_name":"所属节点名","reason":"关联度：主营与节点的匹配说明"}
  ]
}"""

LLM2_SCORE_PROMPT = """你是十倍股赔率评估师。基于实时财务数据和V3案例库经验，对候选个股评分排序。输出前2名推荐。

阅读已提供的个股数据后，对照评分标准，判断还缺少哪些关键信息。如有缺失，使用 bocha_search 搜索或 fetch_url 读取原文补充，最多搜索1次。

⚠️ 个股卡片中的财务数据（市值/PE/毛利率/净利率/负债率/营收/营业利润）来自 tushare 实时行情，是评分唯一依据。请勿搜索这些字段——搜索结果中的市值/PE 可能是过时数据，会导致评分错乱。搜索仅用于补充财务数据之外的定性信息（如催化剂进展、竞争格局、客户合作等）。

# V3 十倍股案例库速查表 (42例)
| # | 股票 | 产业链节点 | 截留 | x倍 | 核心逻辑 | 壁垒 | 驱动类型 |
|---|------|-----------|------|-----|-----------------|------|---------|
| 1 | 寒武纪(688256) | 上游资源 | 高 | 29x | AI芯片是整个AI产业链中价值密度最高、壁垒最高的环节。上游EDA/IP工具（Cadence/... | 技术迭代速度/资本密集度 | 综合驱动 |
| 2 | 胜宏科技(300476) | 中游制造 | 中 | 19x | PCB是AI服务器的必需材料层，单台AI服务器PCB价值量是普通服务器的5-8x，技术壁垒来自... | 客户认证周期/规模效应 | 技术突破 |
| 3 | 惠城环保(300779) | 基础设施 | 高 | 18x | 全球首创废塑料化学回收CPDCC技术，从环保→化工新材料的技术革命，万亿级废塑料处理市场 | 技术迭代速度/专利墙 | 技术突破 |
| 4 | 中际旭创(300308) | 中游制造 | 高 | 18x | 全球光模块/光器件产能80%在中国，AI算力驱动的800G→1.6T技术代际切换形成2年窗口期... | 技术迭代速度/客户认证周期 | 技术突破 |
| 5 | 天普股份(605255) | 平台层(转型后) | 高(预期) | 14x | 汽车管路主业无十倍潜力(与特斯拉/机器人无关,公司已澄清)。涨幅100%来自中昊芯英(国内唯一... | TPU AI芯片技术壁垒(国内唯一量产)/前谷歌TPU团队 | 商业模式升级 |
| 6 | 中坚科技(002779) | 平台层(转型后) | 高(预期) | 14x | 园林机械主业无十倍潜力。涨幅100%来自赛道切换：从传统园林机械→具身智能机器人。通过投资1X... | 1X全球顶级人形机器人供应链准入/华为/英伟达生态合作壁垒 | 商业模式升级 |
| 7 | 九安医疗(002432) | 下游应用 | 高 | 14x | 抗原检测是疫情中需求最刚性、供给最短缺的环节。FDA EUA认证形成了天然的寡头格局（仅7家获... | 牌照/客户认证周期 | 技术突破 |
| 8 | 淳中科技(603516) | 中游制造 | 中 | 12x | 淳中是题材驱动型（液冷无实际收入），涨幅来自自研ASIC芯片概念的市场情绪放大 | 技术迭代速度 | 技术突破 |
| 9 | 亚翔集成(603929) | 基础设施 | 中 | 11x | 半导体洁净室是晶圆厂必需的基础设施(占晶圆厂投资5-8%)，技术壁垒来自洁净度等级(Class... | 客户认证周期/技术迭代速度 | 技术突破 |
| 10 | 同洲电子(002052) | 中游制造 | 中 | 10x | 车载镜头是智能驾驶必需传感器，认证壁垒极高 | 客户认证周期/技术迭代速度 | 技术突破 |
| 11 | 剑桥科技(603083) | 中游制造 | 高 | 10x | 全球光模块/光器件产能80%在中国，AI算力驱动的800G→1.6T技术代际切换形成2年窗口期... | 技术迭代速度/客户认证周期 | 技术突破 |
| 12 | 双林股份(300100) | 中游制造 | 中 | 10x | 特斯拉供应链身份带来强客户锁定+品牌溢价 | 客户认证周期 | 业绩拐点 |
| 13 | 上纬新材(688585) | 平台层(转型后) | 高(预期) | 10x | 碳纤维主业无十倍潜力。涨幅100%来自智元机器人通过收购控股上市公司带来的壳价值重估+资产注入... | 牌照(上市公司壳)/技术迭代速度(人形机器人) | 商业模式升级 |
| 14 | 生益电子(688183) | 中游制造 | 中 | 11x | PCB是AI服务器的必需材料层，单台AI服务器PCB价值量是普通服务器的5-8x，技术壁垒来自... | 客户认证周期/规模效应 | 技术突破 |
| 15 | 新易盛(300502) | 中游制造 | 高 | 10x | 全球光模块产能80%在中国，800G→1.6T技术代际切换形成2年窗口期。光模块是AI算力网络... | 技术迭代速度/客户认证周期 | 技术突破 |
| 16 | 科泰电源(300153) | 中游制造 | 中 | 10x | 储能+充电桩是能源转型基础设施，政策驱动+需求确定性高 | 客户认证周期 | 业绩拐点 |
| 17 | 北特科技(603009) | 中游制造 | 中 | 9x | 双供应链认证形成强客户锁定 | 客户认证周期 | 业绩拐点 |
| 18 | 太辰光(300570) | 中游制造 | 高 | 9x | 全球光模块/光器件产能80%在中国，AI算力驱动的800G→1.6T技术代际切换形成2年窗口期... | 技术迭代速度/客户认证周期 | 技术突破 |
| 19 | 藏格矿业(000408) | 上游资源 | 高 | 9x | 钾肥是中国稀缺资源(进口依赖>50%)+锂是新能源必需要素，藏格的双资源布局极度稀缺 | 资源独占/牌照 | 景气上行 |
| 20 | 仕佳光子(688313) | 中游制造 | 高 | 9x | 光芯片是光模块成本占比最高（30-40%）且国产化率最低的环节，国产替代空间最大 | 技术迭代速度/客户认证周期 | 技术突破 |
| 21 | 浩欧博(688656) | 下游应用 | 高 | 8x | 过敏诊疗闭环（检测+药物）是稀缺商业模式，中国生物制药控股打开资产注入想象空间 | 牌照/专利墙 | 业绩拐点 |
| 22 | 新莱应材(300260) | 中游制造 | 中 | 4x | 精密制造是半导体设备上游必需环节，国产替代从设备→零部件的下沉带来增量 | 客户认证周期/技术迭代速度 | 业绩拐点 |
| 23 | 长盛轴承(300718) | 中游制造 | 中 | 8x | 机器人轴承是人形机器人关节的必需零部件 | 技术迭代速度/客户认证周期 | 业绩拐点 |
| 24 | 协创数据(300857) | 中游制造 | 低 | 8x | 存储芯片分销是低壁垒环节，利润截留能力弱，涨幅主要来自周期反转β而非α | 客户认证周期 | 业绩拐点 |
| 25 | 腾景科技(688195) | 中游制造 | 中 | 6x | PCB是AI服务器的必需材料层，单台AI服务器PCB价值量是普通服务器的5-8x，技术壁垒来自... | 客户认证周期/规模效应 | 技术突破 |
| 26 | 广生堂(300436) | 下游应用 | 中 | 7x | 肝素制剂是成熟市场但海外注册壁垒高，创新药管线打开第二增长曲线 | 牌照/客户认证周期 | 综合驱动 |
| 27 | 永鼎股份(600105) | 上游资源 | 中 | 6x | 光纤光缆是AI数据中心互联的基础设施层，需求确定性高但技术壁垒低于光模块，涨幅通常低于光模块环节 | 资本密集度/规模效应 | 业绩拐点 |
| 28 | 福瑞医科(300049) | 下游应用 | 高 | 5x | FibroScan是全球肝病无创检测的绝对金标准(200+指南推荐)，按次付费模式（类似Saa... | 专利墙/牌照 | 业绩拐点 |
| 29 | 华锡有色(600301) | 上游资源 | 高 | 10x | 锑是半导体掺杂/阻燃剂必需材料，中国锑储量全球第一，供给刚性+需求增长→价格弹性极大 | 资源独占/牌照 | 景气上行 |
| 30 | 品茗科技(688109) | 平台层(转型后) | 高(预期) | 6x | 建筑信息化主业无十倍潜力。涨幅100%来自通研院(北京通用人工智能研究院/朱松纯)战略入股后的... | 通研院AI国家队壁垒/朱松纯全球顶级AI学术资源 | 商业模式升级 |
| 31 | 正丹股份(300641) | 上游资源 | 高 | 6x | TMA是高端增塑剂/粉末涂料必需原料，英力士关停后全球仅2-3家供应商形成寡头垄断 | 资源独占/规模效应 | 景气上行 |
| 32 | 东山精密(002384) | 中游制造 | 中 | 6x | PCB是AI服务器的必需材料层，单台AI服务器PCB价值量是普通服务器的5-8x，技术壁垒来自... | 客户认证周期/规模效应 | 业绩拐点 |
| 33 | 长芯博创(300548) | 中游制造 | 高 | 6x | 全球光模块/光器件产能80%在中国，AI算力驱动的800G→1.6T技术代际切换形成2年窗口期... | 技术迭代速度/客户认证周期 | 技术突破 |
| 34 | 欧陆通(300870) | 中游制造 | 中 | 6x | AI服务器电源是GPU功耗暴增后的刚需升级环节，Google独家合作形成强客户锁定 | 客户认证周期/技术迭代速度 | 业绩拐点 |
| 35 | 华明装备(002270) | 中游制造 | 高 | 5x | 特高压分接开关是电网核心设备（技术壁垒极高），华明国内市占率>80%绝对垄断 | 技术迭代速度/客户认证周期 | 业绩拐点 |
| 36 | 宏和科技(603256) | 上游资源 | 中 | 5x | 碳纤维是航空航天/风电必需材料，航空级壁垒最高 | 技术迭代速度/客户认证周期 | 技术突破 |
| 37 | 常山药业(300255) | 下游应用 | 高 | 5x | GLP-1减重药是医药领域最大的增量市场之一（全球千亿美元级），先发优势+临床数据壁垒形成护城河 | 牌照/技术迭代速度 | 商业模式升级 |
| 38 | 罗博特科(300757) | 中游制造 | 高 | 5x | 硅光耦合设备是CPO/硅光的核心卡脖子环节，ficonTEC是全球唯一量产的供应商，'卖铲人的... | 技术迭代速度/客户认证周期 | 商业模式升级 |
| 39 | 兴业银锡(000426) | 上游资源 | 高 | 5x | 银锡是新能源（光伏/电动车）必需金属，需求增长确定+供给刚性→价格弹性极大 | 资源独占/资本密集度 | 景气上行 |
| 40 | 工业富联(601138) | 中游制造 | 中 | 5x | AI服务器代工是规模致胜的环节，工业富联的产能规模全球第一形成绝对壁垒 | 规模效应/资本密集度 | 业绩拐点 |
| 41 | 国盾量子(688027) | 基础设施 | 中 | 5x | 量子通信是前沿概念，市场按远期期权定价而非当期盈利 | 技术迭代速度/牌照 | 商业模式升级 |
| 42 | 热景生物(688068) | 下游应用 | 高 | 4x | FIC创新药是医药领域价值最高的环节，一旦成功回报极高(>10x)，但失败风险也极高 | 牌照/专利墙 | 商业模式升级 |

# 如何使用V3案例库（加分项，非及格线）
V3速查表是历史经验的参考，不是必须匹配的模板：
- 若当前案例的节点/壁垒/驱动类型在V3中有相似模式 → 加分（说明此模式历史上验证过）
- 若没有找到相似案例 → 不扣分（V3只覆盖了42个已发生的成功案例，不代表所有可能的成功模式）
- V3案例涨幅是事后验证的，仅作为赔率参考，非涨幅保证
- 核心评分依据是当前公司的数据，不是V3历史对照

# 评分维度(1-10分) — 评"事件冲击"而非"公司好坏"

十倍股起涨时往往体质极端：寒武纪ROIC=-23.8%、九安医疗只是小检测厂。
评分不是评这家公司"现在好不好"，而是评"事件兑现后冲击有多大"。

# 硬过滤（评分前执行）
市值 > 300亿 → 直接剔除，不进入评分环节。十倍股从不在大市值中诞生。

# 评分维度(1-10分)

1. 事件冲击比(45%)：暴露度 × 赔率杠杆。分两种类型评估。

   # ═══ 关键前置判断：低市值是"弹射"还是"黑洞"？ ═══

   市值<100亿的公司，低市值可能是因为被错杀的潜力股（弹射），也可能是因为业务在持续毁灭价值（黑洞）。评分前必须先判定——财务数据已在个股卡片中提供。

   【黑洞信号 — 出现任一信号则 impact_score ≤ 5 分】
   - 毛利率 < 15% → 主业本身不创造价值，低市值是合理定价
   - 资产负债率 > 70% 且净利率 < -30% → 债务悬崖+持续失血，退市风险是真实生存问题
   - 营业利润亏损额 > 营收的 50% → 经营失控，新业务利润被旧业务黑洞吞噬
   - 营收同比持续下滑(连续两期) → 业务在萎缩，不是"即将反转"
   ※ 黑洞型：事件利好被旧业务亏损黑洞吞噬。低市值≠低估，而是价值毁灭的合理定价。

   【弹射信号 — 可正常评分】
   - 毛利率 > 25%，亏损来自研发/扩张投入而非主营业务衰退
   - 资产负债率 < 60%，有时间窗口等待反转
   - 营收同比转正或环比改善
   - 扣非亏损在收窄（非扩大）
   ※ 弹射型：低市值=临时困境，新业务有价值且资源在向新业务倾斜。

   【灰色地带】不满足黑洞也不满足弹射 → impact 最高 7 分。

   完成上述判定后，进入评分前还需做 TAM 校验：

   # ═══ TAM 校验：10x 终点能在多大市场里装下？ ═══

   节点市场规模(TAM)已由上游分析提供（见评分节点头部的 TAM 数据），直接使用，无需重新搜索。

   评分前必须评估：当前市值×10 是否能在该 TAM 内实现？
   不设硬性公式——由你判断，但必须在 rationale 中记录。

   评估框架：
   - 若 TAM 明确小于 10x 目标市值（即使 100% 市占也不够）→ 在 rationale 中解释，自行适当限制 impact
   - 若 TAM 处于灰色地带 → 标注「TAM 不确定」，正常评分但提示风险
   - 若 TAM 明确足够 → 标注「TAM 通过」
   - 若上游未提供 TAM → 标注「TAM 无数据」

   例：某公司市值 29 亿，10x = 290 亿。若节点 TAM 标注为 ~100 亿，则即使 100% 市占也无法实现 10x —— impact 不应给到 9 分。

   TAM 校验完成后，按连续光谱给分：

   成熟型（当前已有规模化收入）：
   impact 在 1-10 之间连续取值，综合两个因子：

   ① 暴露度得分（核心）— 事件相关收入占总营收的实际比例，连续评估：
      暴露度 > 70% → 基础区间 8-10 分
      暴露度 50-70% → 基础区间 6-8 分
      暴露度 30-50% → 基础区间 4-6 分
      暴露度 < 30% → 基础区间 2-4 分
      在区间内按实际比例连续取值。例：暴露度 65% 可取 7.5，暴露度 55% 可取 6.5。不要机械锁死在某个整数。

   ② 市值弹性系数 — 市值越小赔率越大，连续衰减：
      50 亿以下 → 不折价（在基础区间上半段取值）
      50-100 亿 → 轻折价（倾向区间中段）
      100-200 亿 → 中等折价（倾向区间下半段）
      200-300 亿 → 显著折价（倾向区间底部）
      105 亿和 195 亿应有可感知的差异——不要同档处理。210 亿和 290 亿也不应同分。

   impact = 暴露度在区间内连续定位 × 市值弹性微调

   验证突破型（产品已通过认证/产能即将放量, 但收入尚未起量）：
   同成熟型逻辑但上限 8 分（10 分只给已有规模化收入的公司）。
   同样按连续光谱——市值 105 亿的最高分应高于市值 195 亿。
   三条条件全部满足 → 不再受验证突破型 8 分上限约束，但评分仍须严格按成熟型的暴露度区间和市值折价标准执行。暴露度 < 30% 就是 2-4 分基础区间，市值 200-300 亿就是显著折价。高分需要高暴露度支撑，认证/订单/产能不能替代暴露度。
   满足 1-2 条 → 上限按市值连续衰减：50 亿→最高 8, 100 亿→最高 7, 200 亿→最高 5（中间值线性插值）。

   # ±1 裁量调整（在 rationale 中显式声明理由）
   允许在上述评分基础上 ±1 调整：
   +1 条件：标的在节点中的纯正度/壁垒/确定性远超同市值段其他公司
   -1 条件：标的在节点中的暴露度/确定性弱于同市值段
   必须在 rationale 中显式声明，格式为「裁量+1：<理由>」或「裁量-1：<理由>」。
   未声明理由的调整视为评分错误。

	2. V3模式匹配(25%)：不猜具体利润倍数，匹配V3中4种十倍股原型
   10=亏损反转型 (寒武纪型): 当前亏损/微利,事件将赋予技术壁垒+市场垄断,利润从负→正大幅反转
   7 =隐形冠军型 (九安型): 公司不起眼,事件突然赋予垄断地位(FDA/牌照/独家认证),利润非线性暴增
   4 =加速成长型 (中际型): 公司已盈利,事件带来技术代际切换(800G→1.6T),量价齐升加速成长
   1 =周期β型 (协创型): 低壁垒蹭热度,涨幅来自市场情绪而非基本面质变
   未匹配到V3模式 → 给4分(中性),不扣分也不加分

	3. 叙事亮点(20%)：该股票的投资故事有多大的想象空间和传播力？

	   评估时综合判断以下四个维度，不要机械对照分数：
	   a) 独特性和稀缺性 — 是不是"第一次""唯一""最大"？故事有没有破圈传播潜力？
	   b) 催化剂的具体性 — 有公告数字、时间节点、订单金额，还是模糊的"有望受益"？
	   c) 预期差 — 市场是否已经充分定价了这个故事？还有没有被忽视的增量信息？
	   d) 验证路径 — 未来3-6个月有没有可观测的验证节点（财报、产能数据、客户公告）？

	   10分 = 四维度全满足：稀缺强叙事+具体数字和时间+市场未充分定价+短期有验证事件
	   7分 = 满足2-3个维度：有明确拐点故事和具体数字支撑，但验证节点较远或预期差一般
	   4分 = 仅满足1个维度：宏观景气受益或模糊利好，缺乏个股层面独特性和具体催化剂
	   1分 = 四个维度均不满足：无清晰叙事，纯概念炒作

4. 唯一性溢价(10%)：按该股票实际可触及的细分市场竞争格局评估，而非整个行业。
   例：MLCC行业有几十家，但"AI服务器高端MLCC"国内能做的不超过5家→基于后者评分。
   10=该细分A股唯一纯正标的
   7 =该细分仅2-3家纯正标的
   4 =该细分有4-8家公司
   1 =竞争激烈>8家（按细分市场计）

# V3案例库关键经验
42个A股十倍股起涨状态：市值中位数39亿，ROIC中位数0.4%，PE中位数44。
起涨时财务数据往往平庸甚至差——关键是事件兑现后的弹性。
利润截留能力是十倍股最重要特征：42例中90%处于中高利润截留节点。
寒武纪案例最典型：起涨ROIC=-23.8%，AI芯片TAM巨大，亏损反转型，47个点的反转创造29倍涨幅。

# 数据校验规则
- 主营与节点明显无关-> impact_score不超过3分，rationale标注"主营不匹配"
- 主营为X却被市场炒作Y概念-> 可给中等分，标注矛盾，impact_score扣1-2分
- 数据缺失的股票 impact_score 和 narrative_score 不超过3分

# 亏损不作惩罚
亏损是弹射起点。*ST退市风险在rationale中标注即可。

# 输出JSON
{
  "scored_stocks": [
    {"stock_code":"","stock_name":"","node_name":"所属节点","impact_score":0,"v3match_score":0,"narrative_score":0,"scarcity_score":0,"total_score":0,"rationale":"","key_risk":""}
  ],
  "top_pick":{"stock_code":"","stock_name":"","node_name":"","investment_thesis":""},
  "runner_up":{"stock_code":"","stock_name":"","node_name":"","investment_thesis":""}
}
scored_stocks按total_score降序。top_pick = 总分最高者（优先第一节点），runner_up = 总分第二高者。
总分 = impact*0.45 + v3match*0.25 + narrative*0.20 + scarcity*0.10

# 阈值硬规则（不可违反）
- 所有候选股total_score均 < 6.5 -> 必须严格按以下格式输出, 不得填入其他字段:
  "top_pick": {"stock_code": "", "stock_name": "无高赔率标的", "node_name": "", "investment_thesis": "所有候选股均未达到6.5分阈值"}
  "runner_up": {"stock_code": "", "stock_name": "无高赔率标的", "node_name": "", "investment_thesis": ""}
- 禁止虚高打分凑数。宁缺毋滥。"""
# ═══════════════════════════════════════
# 核心类
# ═══════════════════════════════════════

class IndustryChainWorkflow:

    def __init__(self, deepseek_key: str, coze_client=None):
        self.dk = deepseek_key
        self.coze = coze_client
        self.fetcher = DataFetcher()

    # ── 主管线 ────────────────────────

    def run_on_record(self, record: dict, progress_cb: Callable | None = None,
                      eval_mode: bool = False) -> dict:
        """
        eval_mode=True: 仅用 news_content 原文推理，不做联网搜索。
        这是为了避免「未来信息泄露」——评测历史案例时，当前网络搜索结果
        已经包含了事后涨幅信息，会污染 LLM 的推理。
        """
        news = str(record.get("news_content", ""))
        step_one = str(record.get("step_one", ""))
        knowledge = str(record.get("knowledge", ""))
        rid = str(record.get("id", ""))

        if not news.strip():
            return {"status": "skipped", "error": "news_content 为空"}

        try:
            # Step 1: LLM #1 — 产业链推理（flash + bocha_search）
            self._p(progress_cb, 1, "LLM产业链推理(flash+bocha)")
            
            chain = self._llm_tool_use(LLM1_PROMPT,
                self._msg_llm1(news, step_one, knowledge),
                tools=BOCHA_TOOLS, tool_map=TOOL_MAP, model=DEEPSEEK_MODEL_FAST, max_turns=5)
            chain.pop("_search_log", [])  # bocha原始结果不再传入提名, LLM #1报告已精炼

            # 校验 LLM #1 输出
            industry = chain.get("chain_overview", {}).get("industry", "")
            nodes = chain.get("top_two_nodes", [])
            is_hard_error = chain.get("error", "").startswith("API ")
            if is_hard_error:
                return {"status": "skipped", "error": chain.get("error", ""), "record_id": rid}
            if (not industry or not nodes):
                print(f"[LLM1-EMPTY] industry='{industry}' nodes={len(nodes)}, retrying...", flush=True)
                chain = self._llm_tool_use(LLM1_PROMPT,
                    self._msg_llm1(news, step_one, knowledge)
                    + "\n\n上次输出industry或top_two_nodes为空。请确保chain_overview.industry不为空、top_two_nodes包含2个节点。",
                    tools=BOCHA_TOOLS, tool_map=TOOL_MAP, model=DEEPSEEK_MODEL_FAST, max_turns=5)
                chain.pop("_search_log", [])
                # 重试后再次检查
                industry = chain.get("chain_overview", {}).get("industry", "")
                nodes = chain.get("top_two_nodes", [])
                is_hard_error = chain.get("error", "").startswith("API ")
                if is_hard_error:
                    return {"status": "skipped", "error": chain.get("error", ""), "record_id": rid}
            if (not industry or not nodes):
                return {"status": "skipped", "error": "LLM #1 无法识别产业链/节点", "record_id": rid}

            # Step 2: Volc节点搜索 — 为提名LLM提供节点内公司列表
            if not eval_mode:
                self._p(progress_cb, 2, "Volc节点搜索")
                web2 = self._search_nodes(chain)
            else:
                web2 = ""

            # Step 3: 提名节点1候选股（flash, 资讯+LLM #1报告+Volc节点公司列表）
            self._p(progress_cb, 3, "Pass1-提名节点1候选股")
            node1 = chain.get("top_two_nodes", [{}])[0]
            noms1 = self._llm(LLM2_NOMINATE_PROMPT, self._msg_nominate_single(node1, chain, news, step_one, knowledge, web2), model=DEEPSEEK_MODEL_FAST)
            noms1["nominations"] = self._resolve_stock_codes(noms1.get("nominations", []))

            self._p(progress_cb, 3, "Pass1-批量查询实时数据")
            enriched1 = self._enrich(noms1, chain)

            self._p(progress_cb, 3, "Pass1-评分排序")
            msg1 = self._msg_score_single(node1, chain, enriched1)
            scores1 = self._llm_tool_use(LLM2_SCORE_PROMPT, msg1,
                tools=BOCHA_TOOLS, tool_map=TOOL_MAP, max_turns=2)
            scores1 = self._validate_and_retry_score(scores1, msg1)

            # 判断节点1最高分是否达标
            ss1 = scores1.get("scored_stocks", [])
            best1 = ss1[0].get("total_score", 0) if ss1 else 0
            node1_ok = best1 >= 6.5

            if node1_ok:
                print(f"[PASS1-OK] node1 best={best1}, using node1 only", flush=True)
                final_scores = scores1
                final_noms = noms1
                final_enriched = enriched1
            else:
                print(f"[PASS1-FAIL] node1 best={best1} < 6.5, adding node2...", flush=True)

                self._p(progress_cb, 5, "Pass2-提名节点2候选股")
                node2 = chain.get("top_two_nodes", [{}, {}])[1]
                noms2 = self._llm(LLM2_NOMINATE_PROMPT, self._msg_nominate_single(node2, chain, news, step_one, knowledge, web2), model=DEEPSEEK_MODEL_FAST)
                noms2["nominations"] = self._resolve_stock_codes(noms2.get("nominations", []))

                self._p(progress_cb, 5, "Pass2-批量查询实时数据")
                enriched2 = self._enrich(noms2, chain)

                all_enriched = {**enriched1, **enriched2}
                all_noms = {
                    "nominations": (noms1.get("nominations", []) + noms2.get("nominations", []))
                }

                self._p(progress_cb, 6, "Pass2-混合评分排序")
                msg_all = self._msg_score(chain, all_enriched)
                final_scores = self._llm_tool_use(LLM2_SCORE_PROMPT, msg_all,
                    tools=BOCHA_TOOLS, tool_map=TOOL_MAP, max_turns=2)
                final_scores = self._validate_and_retry_score(final_scores, msg_all)
                final_noms = all_noms
                final_enriched = all_enriched

            return self._assemble(record, chain, final_noms, final_scores, final_enriched, web2)

        except Exception as e:
            return {"status": "error", "error": str(e)[:1000], "record_id": rid}

    # ── Step 1: LLM #1 ─────────────────

    @staticmethod
    def _msg_llm1(news: str, step_one: str, knowledge: str = "", web: str = "") -> str:
        parts = [f"# 产业资讯\n{news}"]
        if step_one:
            parts.append(f"\n# Agent0初步分析\n{step_one}")
        if knowledge:
            parts.append(f"\n# 背景知识\n{knowledge}")
        if web:
            parts.append(f"\n# 联网搜索结果\n{web[:3000]}")
        return "\n".join(parts)

    # ── Step 3: 联网搜索2 (并行) ───────

    def _search_nodes(self, chain: dict, event_summary: str = "") -> str:
        nodes = chain.get("top_two_nodes", [])
        evt = chain.get("chain_overview", {}).get("event_summary", event_summary)
        queries = []
        for n in nodes:
            name = n.get("node_name", "")
            what = n.get("what_to_look_for", "")
            q = (
                f"搜索「{name}」产业链节点的A股核心公司。\n\n"
                f"背景事件：{evt}\n"
                f"筛选标准：{what}\n\n"
                f"输出要求（按此结构，每家公司一个条目）：\n"
                f"【公司名+代码】主营业务与该节点的匹配说明（1句话）\n"
                f"【竞争壁垒】核心壁垒+市场份额（引用公告/研报）\n"
                f"【业绩与催化】近期业绩趋势+具体催化事件（注明数字和时间）\n\n"
                f"严格排除规则：\n"
                f"- 排除：主营业务产品与该节点核心产品不是同一品类的公司\n"
                f"- 排除：仅因概念/题材被提及，无实质业务的公司\n"
                f"- 排除：跨行业蹭热度的公司（如军工股归入商业航天、AI概念归入医疗设备）\n"
                f"- 优先：券商研报和公司公告中明确点名属于该节点的公司\n"
                f"- 宁缺毋滥，至少列出2家，最多输出5家最核心的公司"
            )
            queries.append(q)

        # 并行调用
        results = []
        with ThreadPoolExecutor(max_workers=2) as ex:
            futures = {ex.submit(self._call_volc, q): i for i, q in enumerate(queries)}
            for f in as_completed(futures):
                i = futures[f]
                try:
                    r = f.result(timeout=90)
                    results.append((i, r))
                except Exception:
                    pass

        results.sort(key=lambda x: x[0])
        parts = []
        for i, (idx, text) in enumerate(results):
            n = nodes[idx] if idx < len(nodes) else {}
            parts.append(f"## 节点{idx+1}: {n.get('node_name','?')}\n{text}")
        return "\n\n".join(parts)

    # ── Step 4: LLM #2 提名 ────────────

    @staticmethod
    def _msg_nominate_single(node: dict, chain: dict, news: str = "",
                             step_one: str = "", knowledge: str = "", web2: str = "") -> str:
        """单节点提名：资讯 + LLM #1节点分析 + Volc节点公司列表 → 候选股"""
        node_name = node.get("node_name", "")
        what = node.get("what_to_look_for", "")
        pfa = json.dumps(chain.get("profit_flow_analysis", []), ensure_ascii=False, indent=2)

        parts = [
            f"# 目标节点: {node_name}",
            f"利润截留分: {node.get('profit_retention_score', 0)}",
            f"选股特征: {what}",
            f"入选理由: {node.get('justification', '')}",
        ]
        if news.strip():
            parts.append(f"\n# 原始产业资讯\n{news[:2000]}")
        if step_one.strip():
            parts.append(f"\n# Agent0产业分析\n{step_one[:1500]}")
        if knowledge.strip():
            parts.append(f"\n# 背景知识\n{knowledge[:1500]}")
        parts.append(f"\n# 全部节点利润流分析（LLM #1 产业链推理结论）\n{pfa}")
        if web2:
            parts.append(f"\n# 节点内A股公司列表（Volc实时搜索）\n{web2}")
        parts.append(f"\n请为「{node_name}」提名5只最相关的A股候选个股。优先从Volc搜索结果中提取公司，不足5只时用你的A股知识补足到5只。")
        return "\n".join(parts)

    # ── Step 4.5: 股票代码校验 ────────────

    def _resolve_stock_codes(self, nominations: list[dict]) -> list[dict]:
        """用 tushare 按名称查找真实股票代码，修正 LLM 可能编造的代码。含3次重试。"""
        if not nominations:
            return nominations

        df = None
        for attempt in range(3):
            try:
                import tushare as ts
                config_path = Path(__file__).parent.parent / 'valuation_app' / 'config.json'
                with open(config_path) as f:
                    cfg = json.load(f)
                pro = ts.pro_api(cfg.get('tushare_token', ''))

                # 全量 A 股名称索引
                df = pro.stock_basic(
                    fields='ts_code,name,list_status')
                df = df[df['list_status'] == 'L']  # 仅上市中
                df['clean_code'] = df['ts_code'].str[:6]
                break
            except Exception as e:
                if attempt < 2:
                    print(f'[CODE-RESOLVE] tushare stock_basic 失败(attempt {attempt+1}): {e}', flush=True)
                    time.sleep(3 * (attempt + 1))
                else:
                    print(f'[CODE-RESOLVE] tushare 3次重试均失败，返回空代码', flush=True)
                    return [{**nom, 'stock_code': '', '_code_source': 'tushare_down'} for nom in nominations]

        if df is None or df.empty:
            return [{**nom, 'stock_code': '', '_code_source': 'tushare_empty'} for nom in nominations]

        resolved = []
        for nom in nominations:
            name = str(nom.get('stock_name', '')).strip()
            if not name:
                resolved.append({**nom, 'stock_code': '', '_code_source': 'empty_name'})
                continue

            # 1) 精确名称匹配
            exact = df[df['name'] == name]
            if not exact.empty:
                code = exact.iloc[0]['clean_code']
                resolved.append({**nom, 'stock_code': code, '_code_source': 'exact_match'})
                continue

            # 2) 名称包含匹配（公司全称包含简称关键词）
            contains = df[df['name'].str.contains(name.replace('(', '\\(').replace(')', '\\)'), na=False)]
            if not contains.empty:
                contains = contains.copy()
                contains['name_len'] = contains['name'].str.len()
                contains = contains.sort_values('name_len')
                code = contains.iloc[0]['clean_code']
                matched_name = contains.iloc[0]['name']
                resolved.append({**nom, 'stock_code': code, 'stock_name': matched_name,
                                 '_code_source': 'fuzzy_match'})
                continue

            # 3) 全称去干扰词匹配（如"云南临沧鑫圆锗业股份有限公司"→"云南锗业"）
            import re as _re
            short = name
            for s in ['股份有限公司','有限责任公司','有限公司','科技股份','新材料','科技']:
                short = short.replace(s, '')
            for prefix in ['云南临沧','云南','北京','深圳','上海','广东','浙江','江苏','山东',
                          '湖北','湖南','四川','福建','安徽','河北','河南','陕西','重庆',
                          '天津','黑龙江','吉林','辽宁','江西','广西','贵州','甘肃','海南',
                          '新疆','西藏','内蒙古','宁夏','青海','山西']:
                if short.startswith(prefix) and len(short) - len(prefix) >= 2:
                    short = short[len(prefix):]
                    break
            core = _re.sub(r'[^一-鿿]', '', short)
            for window in [4, 3, 2]:
                if len(core) >= window:
                    kw = core[-window:]
                    fuzzy2 = df[df['name'].str.contains(kw, na=False)]
                    if not fuzzy2.empty:
                        fuzzy2 = fuzzy2.copy()
                        fuzzy2['name_len'] = fuzzy2['name'].str.len()
                        fuzzy2 = fuzzy2.sort_values('name_len')
                        code = fuzzy2.iloc[0]['clean_code']
                        matched_name = fuzzy2.iloc[0]['name']
                        resolved.append({**nom, 'stock_code': code, 'stock_name': matched_name,
                                         '_code_source': 'core_name'})
                        break
                else:
                    continue
            if resolved and resolved[-1].get('stock_code'):
                continue

            # 4) 关键词模糊匹配
            keywords = name.replace('*', '').replace('ST', '').strip()
            if len(keywords) >= 3:
                fuzzy = df[df['name'].str.contains(keywords, na=False)]
                if not fuzzy.empty:
                    fuzzy = fuzzy.copy()
                    fuzzy['name_len'] = fuzzy['name'].str.len()
                    fuzzy = fuzzy.sort_values('name_len')
                    code = fuzzy.iloc[0]['clean_code']
                    matched_name = fuzzy.iloc[0]['name']
                    resolved.append({**nom, 'stock_code': code, 'stock_name': matched_name,
                                     '_code_source': 'keyword_match'})
                    continue

            # 找不到
            print(f'[CODE-UNMATCHED] 无法匹配: \"{name}\"', flush=True)
            resolved.append({**nom, 'stock_code': '', '_code_source': 'unmatched'})

        # 日志
        matched = sum(1 for r in resolved if r.get('stock_code'))
        print(f'[CODE-RESOLVE] {matched}/{len(resolved)} 只代码校验通过', flush=True)
        for r in resolved:
            src = r.get('_code_source', '?')
            print(f'  {r.get("stock_name","?")} -> {r.get("stock_code","?")} [{src}]', flush=True)

        return resolved

    # ── Step 4.6: Volc 个股投资地图 ──────

    def _fetch_stock_intel(self, stock_code: str, stock_name: str,
                           node_name: str, industry: str = "") -> str:
        """单只个股的 Volc Agent 联网搜索 — 获取实时投资地图"""
        query = (
            f"搜索{stock_name}({stock_code})在「{industry}」产业链「{node_name}」节点的投资地图。按以下结构输出关键字段：\n"
            f"【主营匹配】主营产品线与{node_name}的对应关系、收入占比（引用最新财报）\n"
            f"【竞争壁垒】技术独特性、认证资质、客户绑定深度、产能规模（引用公告/研报）\n"
            f"【近期催化】近6个月的产能扩张/客户突破/大额订单/政策利好（注明具体数字和时间）\n"
            f"【差异化】相比同节点竞对的独特优势（引用可比公司数据）\n"
            f"【市值估值】最新市值、PE/PB、盈利趋势\n"
            f"区分硬事实（公告/财报/研报）与市场观点。不限制字数，信息密度优先。"
        )
        try:
            r = requests.post(VOLC_URL, json={
                "bot_id": VOLC_BOT_ID, "stream": False,
                "messages": [{"role": "user", "content": query}],
            }, headers={"Authorization": f"Bearer {VOLC_AGENT_KEY}",
                        "Content-Type": "application/json"}, timeout=60)
            if r.status_code == 200:
                choices = r.json().get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", "")
        except Exception:
            pass
        return ""

    # ── Step 5: tushare 富化 + Volc 个股搜索 ────

    def _enrich(self, noms: dict, chain: dict | None = None) -> dict:
        """A.tushare批量市值+PE(3次重试)  B.Volc Agent 每只个股并行搜索投资地图"""
        nominations = noms.get("nominations", [])
        codes = [n.get("stock_code", "") for n in nominations if n.get("stock_code")]
        if not codes:
            return {}

        enriched = {c: {} for c in codes}

        # 个股→节点映射 (用于 Volc 查询)
        code_to_node = {}
        code_to_name = {}
        for n in nominations:
            c = n.get("stock_code", "")
            if c:
                code_to_node[c] = n.get("node_name", "")
                code_to_name[c] = n.get("stock_name", "")

        industry = ""
        if chain:
            industry = chain.get("chain_overview", {}).get("industry", "")

        # ── A. tushare 批量市值+PE+流通盘+换手率（3次重试）───
        tushare_ok = False
        for attempt in range(3):
            try:
                import tushare as ts
                config_path = Path(__file__).parent.parent / 'valuation_app' / 'config.json'
                with open(config_path) as f:
                    cfg = json.load(f)
                pro = ts.pro_api(cfg.get('tushare_token', ''))

                fetched_count = 0
                for c in codes:
                    ts_code = f'{c}.SH' if c.startswith(('60','68')) else f'{c}.SZ'
                    try:
                        # 基础信息
                        df_basic = pro.stock_basic(ts_code=ts_code, fields='ts_code,name,industry')
                        if not df_basic.empty:
                            enriched[c]['stock_name'] = df_basic.iloc[0]['name']
                            enriched[c]['industry'] = df_basic.iloc[0]['industry']

                        # 日线指标: 市值/PE/PB/流通盘/换手率
                        df_daily = pro.daily_basic(ts_code=ts_code,
                            fields='ts_code,total_mv,pe_ttm,pb,total_share,float_share,turnover_rate')
                        if not df_daily.empty:
                            row = df_daily.iloc[0]
                            enriched[c]['market_cap'] = float(row['total_mv']) / 1e4  # 万元->亿
                            enriched[c]['pe_ttm'] = float(row['pe_ttm']) if row['pe_ttm'] else 0
                            enriched[c]['pb'] = float(row['pb']) if row['pb'] else 0
                            enriched[c]['total_share'] = float(row['total_share']) / 1e4
                            enriched[c]['float_share'] = float(row['float_share']) / 1e4 if row['float_share'] else 0
                            enriched[c]['turnover_rate'] = float(row['turnover_rate']) if row['turnover_rate'] else 0
                            fetched_count += 1

                        # 财务指标: 盈利质量 + 生存概率（用于黑洞/弹射区分）
                        try:
                            df_fina = pro.fina_indicator(ts_code=ts_code,
                                fields='ts_code,end_date,roe,roa,grossprofit_margin,netprofit_margin,debt_to_assets')
                            if not df_fina.empty:
                                row_f = df_fina.iloc[0]
                                enriched[c]['roe'] = float(row_f['roe']) if row_f['roe'] else 0
                                enriched[c]['roa'] = float(row_f['roa']) if row_f['roa'] else 0
                                enriched[c]['gross_margin'] = float(row_f['grossprofit_margin']) if row_f['grossprofit_margin'] else 0
                                enriched[c]['net_margin'] = float(row_f['netprofit_margin']) if row_f['netprofit_margin'] else 0
                                enriched[c]['debt_ratio'] = float(row_f['debt_to_assets']) if row_f['debt_to_assets'] else 0
                        except Exception:
                            pass

                        # 利润表: 营收+利润趋势（tushare income 单位为元，需 / 1e8 → 亿元）
                        try:
                            df_inc = pro.income(ts_code=ts_code,
                                fields='ts_code,end_date,total_revenue,operate_profit,n_deducted_netprofit')
                            if not df_inc.empty:
                                # 最新一期
                                row_i = df_inc.iloc[0]
                                enriched[c]['revenue'] = float(row_i['total_revenue']) / 1e8  # 元→亿元
                                enriched[c]['op_profit'] = float(row_i['operate_profit']) / 1e8 if row_i['operate_profit'] else 0
                                enriched[c]['deducted_np'] = float(row_i['n_deducted_netprofit']) / 1e8 if row_i['n_deducted_netprofit'] else 0
                                # 上一期（同比趋势）
                                if len(df_inc) >= 2:
                                    rp = df_inc.iloc[1]
                                    prev_rev = float(rp['total_revenue']) / 1e8
                                    if prev_rev and prev_rev > 0:
                                        enriched[c]['revenue_yoy'] = round((enriched[c]['revenue'] - prev_rev) / prev_rev * 100, 1)
                                    else:
                                        enriched[c]['revenue_yoy'] = None
                                else:
                                    enriched[c]['revenue_yoy'] = None
                        except Exception:
                            pass
                    except Exception:
                        pass

                if fetched_count > 0:
                    tushare_ok = True
                    break
                elif attempt < 2:
                    print(f'[tushare] 第{attempt+1}次全空, {3}s后重试...', flush=True)
                    time.sleep(3)
            except Exception as e:
                print(f'[tushare] 第{attempt+1}次异常: {e}', flush=True)
                if attempt < 2:
                    time.sleep(5 * (attempt + 1))

        if not tushare_ok:
            print(f'[tushare] 3次重试后仍无数据, 市值/PE将缺失', flush=True)

        # ── 标记数据质量 ──
        for c in codes:
            has_mcap = enriched[c].get('market_cap') is not None
            has_pe = enriched[c].get('pe_ttm', 0) != 0
            has_fina = enriched[c].get('gross_margin') is not None
            if has_mcap and has_pe and has_fina:
                enriched[c]['_data_quality'] = 'full'
            elif has_mcap and (has_pe or has_fina):
                enriched[c]['_data_quality'] = 'partial'
            else:
                enriched[c]['_data_quality'] = 'missing'

        # ── B. Volc Agent 每只个股并行搜索投资地图（仅搜索市值<=300亿的）───
        def fetch_intel(code: str) -> tuple:
            name = code_to_name.get(code, '')
            node = code_to_node.get(code, '')
            try:
                intel = self._fetch_stock_intel(code, name, node, industry)
                return code, intel
            except Exception:
                return code, ""

        small_codes = [c for c in codes
                       if (enriched[c].get('market_cap') or 0) <= 300]
        skipped = len(codes) - len(small_codes)
        if skipped > 0:
            print(f'[Volc] 跳过{skipped}只大盘股(市值>300亿), 仅搜索{len(small_codes)}只', flush=True)

        if small_codes:
            with ThreadPoolExecutor(max_workers=3) as ex:
                futures = [ex.submit(fetch_intel, c) for c in small_codes]
                for f in as_completed(futures):
                    try:
                        code, intel = f.result(timeout=75)
                        enriched[code]['_volc_intel'] = intel
                    except Exception:
                        pass

        # ── C. 兜底：名称用提名数据补 ──
        for n in nominations:
            code = n.get("stock_code", "")
            if code in enriched and not enriched[code].get('stock_name'):
                enriched[code]['stock_name'] = n.get('stock_name', '')

        return enriched

    # ── Step 6: LLM #2 评分 ────────────

    @staticmethod
    def _msg_score(chain: dict, enriched: dict) -> str:
        nodes = chain.get("top_two_nodes", [])
        nodes_text = json.dumps(nodes, ensure_ascii=False, indent=2)
        pfa = json.dumps(chain.get("profit_flow_analysis", []), ensure_ascii=False, indent=2)

        lines = [
            f"# 前2节点\n{nodes_text}",
            f"\n# 全部节点利润流分析\n{pfa}",
            f"\n# 候选个股实时数据",
        ]

        has_missing = False
        for code, data in enriched.items():
            mcap = data.get('market_cap', 0) or 0
            data_qual = data.get('_data_quality', 'full')
            if mcap > 300:
                continue  # 硬过滤：市值>300亿直接跳过，不送入LLM

            pe = data.get('pe_ttm', 0) or 0
            pb = data.get('pb', 0) or 0
            ind = data.get('industry', '') or ''
            ts_val = data.get('total_share', 0) or 0
            fs_val = data.get('float_share', 0) or 0
            tr = data.get('turnover_rate', 0) or 0
            volc_intel = data.get('_volc_intel', '') or ''

            # 财务健康数据（用于黑洞/弹射区分）
            gm = data.get('gross_margin')
            nm = data.get('net_margin')
            roe = data.get('roe')
            da = data.get('debt_ratio')
            rev = data.get('revenue')
            op_profit = data.get('op_profit')
            rev_yoy = data.get('revenue_yoy')
            deducted = data.get('deducted_np')

            name = data.get('stock_name', '') or f'({code})'

            if data_qual == 'missing':
                has_missing = True
                mcap_str = "[数据缺失-禁止臆测]"
            else:
                mcap_str = f"{mcap:.0f}亿"

            intel_block = f"\n[个股投资地图-Volc实时搜索]\n{volc_intel}" if volc_intel else "\n[个股投资地图: 未获取到]"

            # 构建财务健康行（有数据则展示，无则跳过）
            fin_parts = []
            if gm is not None:
                fin_parts.append(f"毛利率={gm:.1f}%")
            if nm is not None:
                fin_parts.append(f"净利率={nm:.1f}%")
            if roe is not None:
                fin_parts.append(f"ROE={roe:.1f}%")
            if da is not None:
                fin_parts.append(f"负债率={da:.1f}%")
            if rev is not None:
                rev_str = f"营收={rev:.1f}亿"
                if rev_yoy is not None:
                    rev_str += f"(同比{rev_yoy:+.1f}%)" if rev_yoy else ""
                fin_parts.append(rev_str)
            if op_profit is not None:
                fin_parts.append(f"营业利润={op_profit:+.1f}亿")
            if deducted is not None:
                fin_parts.append(f"扣非={deducted:+.1f}亿")
            fin_line = (" | ".join(fin_parts)) if fin_parts else "财务数据: 暂无"

            card = (
                f"\n### {name}({code})\n"
                f"市值{mcap_str} | PE={pe:.1f} | PB={pb:.1f} | 换手率{tr:.1f}%\n"
                f"行业: {ind} | 总股本{ts_val:.1f}亿 | 流通{fs_val:.1f}亿\n"
                f"{fin_line}"
                f"{intel_block}"
            )
            lines.append(card)

        if has_missing:
            lines.append(
                f"\n# [严重警告] 以上标记为'数据缺失'的股票,"
                f"说明 tushare 3次重试后仍无法获取实时市值/PE。"
                f"严禁使用训练数据臆测。"
                f"数据缺失的股票 impact_score 和 narrative_score 不得超过 3 分。"
            )

        lines.append("\n请基于以上数据对候选股评分排序。")
        return "\n".join(lines)

    @staticmethod
    def _msg_score_single(node: dict, chain: dict, enriched: dict) -> str:
        """单节点评分：只有一个节点的候选股，简单评分"""
        node_name = node.get("node_name", "")
        tam = node.get("tam_estimate", "")
        evt = chain.get("chain_overview", {}).get("event_summary", "")

        lines = [
            f"# 评分节点: {node_name}",
            f"节点市场规模(TAM): {tam}" if tam else f"节点市场规模(TAM): 未提供",
            f"事件: {evt}",
            f"\n# 候选个股实时数据",
        ]

        has_missing = False
        for code, data in enriched.items():
            mcap = data.get('market_cap', 0) or 0
            data_qual = data.get('_data_quality', 'full')
            if mcap > 300:
                continue  # 硬过滤
            pe = data.get('pe_ttm', 0) or 0
            name = data.get('stock_name', code) or code
            ind = data.get('industry', '') or ''
            volc_intel = data.get('_volc_intel', '') or ''

            # 财务健康数据
            gm = data.get('gross_margin')
            nm = data.get('net_margin')
            roe_val = data.get('roe')
            da = data.get('debt_ratio')
            rev = data.get('revenue')
            op_profit = data.get('op_profit')
            rev_yoy = data.get('revenue_yoy')

            if data_qual == 'missing':
                has_missing = True
                mcap_str = "[数据缺失-禁止臆测]"
            else:
                mcap_str = f"{mcap:.0f}亿"

            intel_block = f"\n[个股投资地图-Volc实时搜索]\n{volc_intel}" if volc_intel else "\n[个股投资地图: 未获取到]"

            fin_parts = []
            if gm is not None: fin_parts.append(f"毛利率={gm:.1f}%")
            if nm is not None: fin_parts.append(f"净利率={nm:.1f}%")
            if roe_val is not None: fin_parts.append(f"ROE={roe_val:.1f}%")
            if da is not None: fin_parts.append(f"负债率={da:.1f}%")
            if rev is not None:
                rev_str = f"营收={rev:.1f}亿"
                if rev_yoy is not None:
                    rev_str += f"(同比{rev_yoy:+.1f}%)"
                fin_parts.append(rev_str)
            if op_profit is not None: fin_parts.append(f"营业利润={op_profit:+.1f}亿")
            fin_line = (" | ".join(fin_parts)) if fin_parts else "财务数据: 暂无"

            card = (
                f"\n### {name}({code})\n"
                f"市值{mcap_str} | PE={pe:.1f} | 行业: {ind}\n"
                f"{fin_line}"
                f"{intel_block}"
            )
            lines.append(card)

        if has_missing:
            lines.append(
                f"\n# [严重警告] 以下股票市值标记为'数据缺失',"
                f"说明 tushare 3次重试后仍无法获取实时数据。"
                f"严禁使用训练数据臆测市值/PE。"
                f"数据缺失的股票 impact_score 和 narrative_score 不得超过 3 分。"
            )

        lines.append(f"\n请对以上「{node_name}」节点的候选股评分排序。每只打出impact/v3match/narrative/scarcity四个分，选出top_pick和runner_up。")
        return "\n".join(lines)

    def _validate_and_retry_score(self, scores: dict, msg: str) -> dict:
        """校验 LLM #2 输出：空则用同一份prompt重试一次"""
        ss = scores.get("scored_stocks", [])
        tp = scores.get("top_pick", {})

        # 评分日志 — 输出每只候选股的四维得分，方便监控管线健康度
        if ss:
            lines = ["[SCORES] 候选股评分:"]
            for s in ss:
                lines.append(
                    f"  {s.get('stock_name','?')}({s.get('stock_code','?')}) | "
                    f"impact={s.get('impact_score',0)} v3match={s.get('v3match_score',0)} "
                    f"narrative={s.get('narrative_score',0)} scarcity={s.get('scarcity_score',0)} "
                    f"→ 总分={s.get('total_score',0):.1f}"
                )
            lines.append(f"  top_pick={tp.get('stock_name','?')}({tp.get('stock_code','?')})")
            print("\n".join(lines), flush=True)
        else:
            print("[SCORES] scored_stocks为空，无可评分候选股", flush=True)

        if (not ss or (not tp.get("stock_code", "") and not _is_no_pick(tp))) and not scores.get("error", "").startswith("API "):
            print(f"[LLM2-EMPTY] scored_stocks={len(ss)} top_pick_code='{tp.get('stock_code','')}', retrying...", flush=True)
            scores = self._llm_tool_use(LLM2_SCORE_PROMPT,
                msg + "\n\n上次输出缺少有效的scored_stocks或top_pick。请确保输出完整，top_pick和runner_up必须有stock_code。",
                tools=BOCHA_TOOLS, tool_map=TOOL_MAP, max_turns=2)
        return scores

    # ── 组装结果 ────────────────────────

    def _assemble(self, record, chain, noms, scores, enriched, web2="") -> dict:
        tp = scores.get("top_pick", {})
        ru = scores.get("runner_up", {})
        ss = scores.get("scored_stocks", [])

        # ── 归一化 top_pick/runner_up ──
        tp = _normalize_pick(tp, "top_pick")
        ru = _normalize_pick(ru, "runner_up")

        # 处理"无高赔率标的" — 检查 name 和 code 两个字段
        is_no_pick = _is_no_pick(tp)
        is_no_runner = _is_no_pick(ru)

        # 注入 tushare 真实市值 (LLM 不输出市值, 由代码填入)
        for s in ss:
            code = s.get("stock_code", "")
            if code and code in enriched:
                real_mcap = enriched[code].get("market_cap")
                if real_mcap is not None:
                    s["market_cap_billion"] = round(real_mcap, 1)
            # 确保代码是纯6位数字
            s["stock_code"] = _clean_stock_code(s.get("stock_code", ""))

        return {
            "status": "done",
            "record_id": str(record.get("id", "")),
            "chain_analysis": chain,
            "nominations": noms,
            "stock_analysis": scores,
            "top_pick": tp, "runner_up": ru,
            "top5_reference": ss[:5],
            "news_content": str(record.get("news_content", "")),
            "step_one": str(record.get("step_one", "")),
            "web_research": f"=== Volc节点搜索 ===\n{web2}",
            "source_record_id": _safe_int(record.get("id", 0)),
            "industry_chain": chain.get("chain_overview", {}).get("industry", ""),
            "event_summary": chain.get("chain_overview", {}).get("event_summary", ""),
            "top_nodes_json": json.dumps(chain.get("top_two_nodes", []), ensure_ascii=False),
            "scored_stocks_json": json.dumps(ss, ensure_ascii=False),
            "chain_analysis_json": json.dumps(chain, ensure_ascii=False),
            "stock_analysis_json": json.dumps(scores, ensure_ascii=False),
            "top_pick_code": "" if is_no_pick else tp.get("stock_code", ""),
            "top_pick_name": "无高赔率标的" if is_no_pick else tp.get("stock_name", ""),
            "top_pick_node": "" if is_no_pick else tp.get("node_name", ""),
            "top_pick_score": "" if is_no_pick else (str(ss[0].get("total_score", "")) if ss else ""),
            "top_pick_thesis": "" if is_no_pick else tp.get("investment_thesis", ""),
            "runner_up_code": "" if is_no_runner else ru.get("stock_code", ""),
            "runner_up_name": "无高赔率标的" if is_no_runner else ru.get("stock_name", ""),
            "runner_up_node": "" if is_no_runner else ru.get("node_name", ""),
            "runner_up_score": "" if is_no_runner else (str(ss[1].get("total_score", "")) if len(ss) > 1 else ""),
            "runner_up_thesis": "" if is_no_runner else ru.get("investment_thesis", ""),
        }

    # ── LLM 调用 ────────────────────────

    def _llm(self, system: str, user: str, label: str = "", model: str = "") -> dict:
        model = model or DEEPSEEK_MODEL
        use_thinking = model == DEEPSEEK_MODEL  # 仅 v4-pro 评分开思考，提名不需要
        for attempt in range(3):
            try:
                payload = {
                    "model": model,
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                    "max_tokens": 30720 if use_thinking else 8192,
                    "stream": False, "temperature": 0,
                }
                if use_thinking:
                    payload["thinking"] = {"type": "enabled"}
                    payload["reasoning_effort"] = "high"
                r = requests.post(DEEPSEEK_URL, json=payload,
                    headers={"Authorization": f"Bearer {self.dk}", "Content-Type": "application/json"}, timeout=600)
                if r.status_code != 200:
                    if attempt < 2: time.sleep(3 * (attempt + 1)); continue
                    return {"error": f"API {r.status_code}", "raw": r.text[:500]}
                resp_json = r.json()
                content = resp_json["choices"][0]["message"]["content"]
                usage = resp_json.get("usage", {})
                reasoning = (usage.get("completion_tokens_details", {}) or {}).get("reasoning_tokens", 0)
                print(f"[LLM-TOKEN] _llm model={model} prompt={usage.get("prompt_tokens",0)} completion={usage.get("completion_tokens",0)} reasoning={reasoning} total={usage.get("total_tokens",0)}", flush=True)
                parsed = self._parse_json(content)
                if parsed: return parsed
                if attempt < 2:
                    user += "\n\n上次输出不是有效JSON。请严格输出纯JSON，不要用```json```包裹，不要加注释，不要有任何前缀或后缀文字。确保所有字符串用双引号。"
                    continue
                print(f'[LLM-PARSE-FAIL] {label} raw(500): {content[:500]}', flush=True); return {"error": "JSON解析失败", "raw": content[:2000]}
            except requests.Timeout:
                if attempt < 2: time.sleep(5); continue
                return {"error": "API超时"}
            except Exception as e:
                if attempt < 2: time.sleep(3); continue
        return {"error": "重试耗尽"}

    def _llm_tool_use(self, system: str, user: str, tools: list[dict],
                       tool_map: dict, max_turns: int = 4,
                       model: str = "") -> dict:
        """带 tool-use 的 LLM 调用。返回 dict 含 _search_log(搜索记录列表)"""
        model = model or DEEPSEEK_MODEL
        use_thinking = model in (DEEPSEEK_MODEL, DEEPSEEK_MODEL_FAST)  # v4-pro 和 Flash 都开思考
        search_log = []  # 收集所有搜索结果
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        for turn in range(max_turns):
            try:
                is_last_turn = (turn == max_turns - 1)

                payload = {
                    "model": model,
                    "messages": messages,
                    "max_tokens": 30720,
                    "stream": False, "temperature": 0,
                }
                # 最后一轮：Flash → v4-pro 输出可靠 JSON
                if is_last_turn and model == DEEPSEEK_MODEL_FAST:
                    payload["model"] = DEEPSEEK_MODEL
                    payload["thinking"] = {"type": "enabled"}
                elif is_last_turn:
                    pass  # v4-pro already set, thinking handled below
                # 前N-1轮: 传tools; 最后轮: 不传tools强制输出JSON
                if not is_last_turn:
                    payload["tools"] = tools
                    if use_thinking:
                        payload["thinking"] = {"type": "enabled"}
                        payload["reasoning_effort"] = "high"
                else:
                    messages.append({
                        "role": "user",
                        "content": "工具已关闭。请基于以上所有搜索结果，直接输出最终JSON报告。禁止使用工具、DSML、XML或任何非JSON格式。输出必须是纯JSON对象（以{开头，以}结尾）。"
                    })
                    # 思考模式输出更大(推理tokens+JSON)，统一给16384
                    payload["max_tokens"] = 16384

                r = requests.post(DEEPSEEK_URL, json=payload,
                    headers={"Authorization": f"Bearer {self.dk}",
                           "Content-Type": "application/json"}, timeout=300)
                if r.status_code != 200:
                    return {"error": f"API {r.status_code}", "raw": r.text[:500], "_search_log": search_log}
                resp_json = r.json()
                msg = resp_json["choices"][0]["message"]
                usage = resp_json.get("usage", {})
                reasoning = (usage.get("completion_tokens_details", {}) or {}).get("reasoning_tokens", 0)
                print(f'[LLM-TOKEN] turn={turn}/{max_turns} model={model} prompt={usage.get("prompt_tokens",0)} completion={usage.get("completion_tokens",0)} reasoning={reasoning} total={usage.get("total_tokens",0)}', flush=True)

                if msg.get("tool_calls"):
                    # V4 requires non-empty content for tool call messages
                    assistant_content = msg.get("content") or "正在搜索..."
                    messages.append({
                        "role": "assistant",
                        "content": assistant_content,
                        "tool_calls": msg["tool_calls"],
                    })
                    for tc in msg["tool_calls"]:
                        fn_name = tc["function"]["name"]
                        fn_args = json.loads(tc["function"]["arguments"])
                        fn = tool_map.get(fn_name)
                        if fn:
                            try:
                                result = fn(**fn_args)
                            except Exception as e:
                                result = f"工具调用异常: {e}"
                        else:
                            result = f"未知工具: {fn_name}"
                        print(f'[TOOL] {fn_name}({json.dumps(fn_args, ensure_ascii=False)[:100]}) -> {len(result)} chars', flush=True)
                        search_log.append({
                            "fn": fn_name,
                            "args": fn_args,
                            "result": str(result)[:3000],
                        })
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": str(result)[:8000],
                        })
                    continue

                content = msg.get("content", "")

                # 检测 DSML tool_call（DeepSeek Flash 偶发，含最后一轮）
                dsml_tool_calls = self._parse_dsml(content)
                if dsml_tool_calls:
                    if is_last_turn:
                        # 最后一轮仍输出DSML：追加强制JSON指令，立即重试一次
                        messages.append({"role": "user", "content": "不要再用工具。请直接输出最终JSON报告，不要用DSML或XML格式，输出纯JSON。不要输出任何其他格式。"})
                        payload["messages"] = messages
                        r2 = requests.post(DEEPSEEK_URL, json=payload,
                            headers={"Authorization": f"Bearer {self.dk}",
                                   "Content-Type": "application/json"}, timeout=300)
                        if r2.status_code == 200:
                            content2 = r2.json()["choices"][0]["message"].get("content", "")
                            parsed2 = self._parse_json(content2)
                            if parsed2:
                                parsed2["_search_log"] = search_log
                                return parsed2
                        # 重试也失败 — 回退：构造最小化结果
                        print(f'[LLM1-DSML-RETRY-FAIL] 最后一轮重试仍失败', flush=True)
                        return {"error": "DSML格式无法转换", "raw": content[:2000], "_search_log": search_log}
                    messages.append({"role": "assistant", "content": content[:500]})
                    for tc in dsml_tool_calls:
                        fn_name = tc["name"]
                        fn_args = tc["args"]
                        fn = tool_map.get(fn_name)
                        if fn:
                            try:
                                result = fn(**fn_args)
                            except Exception as e:
                                result = f"工具调用异常: {e}"
                        else:
                            result = f"未知工具: {fn_name}"
                        print(f'[TOOL-DSML] {fn_name}({json.dumps(fn_args, ensure_ascii=False)[:100]}) -> {len(result)} chars', flush=True)
                        search_log.append({
                            "fn": fn_name,
                            "args": fn_args,
                            "result": str(result)[:3000],
                        })
                        messages.append({
                            "role": "user",
                            "content": f"[{fn_name} 结果]\n{str(result)[:5000]}",
                        })
                    continue

                parsed = self._parse_json(content)
                if parsed:
                    parsed["_search_log"] = search_log
                    return parsed
                print(f'[LLM1-PARSE-FAIL] raw(500): {content[:500]}', flush=True)
                return {"error": "JSON解析失败", "raw": content[:2000], "_search_log": search_log}
            except requests.Timeout:
                continue
            except Exception as e:
                return {"error": str(e)[:500], "_search_log": search_log}
        return {"error": f"tool-use 超过 {max_turns} 轮", "_search_log": search_log}

    @staticmethod
    def _call_volc(query: str) -> str:
        try:
            r = requests.post(VOLC_URL, json={
                "bot_id": VOLC_BOT_ID, "stream": False,
                "messages": [{"role": "user", "content": query}],
            }, headers={"Authorization": f"Bearer {VOLC_AGENT_KEY}", "Content-Type": "application/json"}, timeout=90)
            if r.status_code == 200:
                choices = r.json().get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", "")
        except Exception:
            pass
        return ""

    @staticmethod
    def _parse_dsml(content: str) -> list[dict] | None:
        """解析 DeepSeek Flash 偶发的 DSML 格式 tool_call，返回 [{"name":..., "args":{...}}]"""
        # DSML 格式: 〈DSML｜tool_calls〉〈DSML｜invoke name="fn"〉〈DSML｜parameter name="x" string="true"〉val〈/DSML｜parameter〉...
        if 'DSML' not in content and 'tool_calls' not in content:
            return None
        import re as _re
        # 提取 invoke 块: name + 所有 parameter
        invokes = _re.findall(
            r'<[^>]*DSML[^>]*invoke\s+name\s*=\s*"([^"]*)"\s*>(.*?)</[^>]*DSML[^>]*invoke\s*>',
            content, _re.DOTALL)
        if not invokes:
            return None
        results = []
        for fn_name, params_block in invokes:
            args = {}
            for pm in _re.finditer(
                r'<[^>]*DSML[^>]*parameter\s+name\s*=\s*"([^"]*)"[^>]*>\s*(.*?)\s*</[^>]*DSML[^>]*parameter\s*>',
                params_block, _re.DOTALL):
                pname = pm.group(1)
                pval = pm.group(2).strip()
                # 字符串值去掉首尾引号
                if pval.startswith('"') and pval.endswith('"'):
                    pval = pval[1:-1]
                # 尝试转为数字
                try:
                    if '.' in pval:
                        pval = float(pval)
                    else:
                        pval = int(pval)
                except (ValueError, TypeError):
                    pass
                args[pname] = pval
            if fn_name:
                results.append({"name": fn_name, "args": args})
        return results if results else None

    @staticmethod
    def _parse_json(text: str) -> dict | None:
        if not text: return None

        # 1. 先手动剥掉 markdown ```json ... ``` 包裹
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned)
            cleaned = re.sub(r"\n?```\s*$", "", cleaned)

        # 2. 直接解析
        try: return json.loads(cleaned)
        except: pass

        # 3. 找 ``` 代码块中的 JSON
        m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if m:
            try: return json.loads(m.group(1).strip())
            except: pass

        # 4. 找第一个 { 到最后一个 } 之间的内容
        start = text.find('{')
        end = text.rfind('}')
        if start >= 0 and end > start:
            try: return json.loads(text[start:end+1])
            except: pass

        return None

    @staticmethod
    def _p(cb, step, name):
        if cb:
            try: cb(step, name)
            except: pass


# ── 模块级辅助函数 ──────────────────────────

def _safe_int(val) -> int:
    """安全转 int：字符串ID/None/空 → 0，数字 → int"""
    try:
        return int(val)
    except (ValueError, TypeError):
        return 0


def _clean_stock_code(code: str) -> str:
    """清洗股票代码：去 .SH/.SZ 后缀，非6位数字返回空"""
    if not code:
        return ""
    code = str(code).strip().upper()
    # 去 tushare 后缀
    for suffix in (".SH", ".SZ", ".BJ"):
        if code.endswith(suffix):
            code = code[:-3]
            break
    # 必须恰好 6 位数字
    if len(code) == 6 and code.isdigit():
        return code
    return ""


def _is_no_pick(pick: dict) -> bool:
    """判断 top_pick/runner_up 是否为「无高赔率标的」
    LLM 可能把关键词填在 name/code/thesis/node 任意字段，全量检查。"""
    if not isinstance(pick, dict):
        return False
    keyword = "无高赔率标的"
    # 检查所有可能是 LLM 填入关键词的字段
    check_fields = ["stock_name", "stock_code", "investment_thesis", "node_name"]
    for field in check_fields:
        if keyword in str(pick.get(field, "")).strip():
            return True
    return False


def _normalize_pick(pick, label: str = "") -> dict:
    """归一化 top_pick/runner_up：LLM 有时返回纯字符串 "无高赔率标的" 而非 {"stock_name":"..."}"""
    if isinstance(pick, dict):
        # 清洗 stock_code：去后缀、验证6位数字
        raw_code = str(pick.get("stock_code", ""))
        pick["stock_code"] = _clean_stock_code(raw_code)
        return pick
    if isinstance(pick, str):
        return {"stock_name": pick, "stock_code": "", "node_name": "", "investment_thesis": ""}
    return {}
