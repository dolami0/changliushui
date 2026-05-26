"""
产业链利润流分析器 — 双Pass LLM架构

Step 1: 联网搜索1 — 产业事件全局
Step 2: LLM #1 — 产业链推理 → 前2节点
Step 3: 联网搜索2 — 每节点1个query (并行)
Pass 1:
  Step 4: LLM #2 — 提名节点1候选股
  Step 5: tushare + investoday 数据富化
  Step 6: LLM #2 — 评分节点1
  ├─ best >= 6.5 → 输出
  └─ best < 6.5 → Pass 2:
      Step 7: 提名节点2候选股
      Step 8: 数据富化
      Step 9: 混合评分 → 输出
"""

import json, re, time, requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

from data_fetcher import DataFetcher

# ═══════════════════════════════════════
# API 配置
# ═══════════════════════════════════════
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-v4-pro"
VOLC_URL = "https://open.feedcoopapi.com/agent_api/agent/chat/completion"
VOLC_BOT_ID = "7640524154441156122"
VOLC_KEY = "8Kdlfi1ETYGpj04p3PEK5PlM6UnTUERs"

# ═══════════════════════════════════════
# LLM #1 — 产业链节点利润截留分析
# ═══════════════════════════════════════
LLM1_PROMPT = """你是产业链利润流分析师。给定产业资讯和联网搜索结果，判断此产业链上哪些节点截取最多利润，输出前2个节点。

# 分析框架：5维度利润截留评估

对产业链上每个节点（上游/中游/下游的具体环节），从5个维度评估其截留利润的能力：

1. 议价能力 — 该节点对上游能否压价？对下游能否提价？
2. 集中度 — 寡头还是散兵？集中才能留住利润
3. 转换成本 — 客户换供应商有多难？（认证周期/产线绑定/监管壁垒）
4. 增值比例 — 该节点贡献最终产品价值的百分之几？
5. 需求弹性 — 事件直接拉动该节点需求，还是间接蹭到？

# 节点命名规则

节点名必须包含「产业链具体环节+行业定语」。例如不应输出"产品集成与系统制造"，应输出"智能医疗器械整机制造"或"医用AI软件与算法平台"。节点名要能让读者一眼看出这是哪条产业链的哪个环节。

# 隐性上游优先原则

产业链利润往往向"隐性上游"集中——即体积小、价值密度高、认证壁垒极强的上游环节（芯片、特种材料、核心元器件），而非显眼的中游总装。分析时重点关注：

- 若某上游环节占下游成品成本<5%但断供即瘫痪 → 利润截留极高（如宇航芯片、高速光芯片）
- 中游总装即使产值大，若竞争分散、切换成本低，利润截留反而不如隐性上游
- 不要无限向上游追溯：只考虑一阶相关（直接供应商），不取二阶衍生（供应商的供应商）。如光芯片是一阶上游，光芯片的衬底材料是二阶——利润逻辑已不同

信息来源置信度
联网搜索结果多来自雪球等投资社区。硬事实(财报/公告)→高置信；软观点(大V判断/预期)→低置信，仅参考。

# 输出格式（严格执行）
- 只输出纯JSON，不要用 ```json``` 或任何markdown标记包裹
- JSON中不要包含注释（// 或 /* */）
- 输出前后不能有任何其他文字

# 输出JSON (只输出JSON)
{
  "chain_overview": {"industry":"","event_summary":"","nodes":[{"name":"","position":"upstream/midstream/downstream","key_products":[]}]},
  "profit_flow_analysis": [{"node_name":"","position":"","bargaining_power":"high/medium/low","concentration":"high/medium/low","switching_cost":"high/medium/low","value_add_ratio_pct":0,"demand_elasticity":"high/medium/low","profit_retention_score":0,"rationale":""}],
  "top_two_nodes": [{"node_name":"","position":"","profit_retention_score":0,"justification":"","what_to_look_for":"此节点内什么特征的公司会胜出（必须结合此具体行业写，不要泛泛而谈）","key_risk":""}]
}"""

# ═══════════════════════════════════════
# LLM #2 — 个股赔率评分
# ═══════════════════════════════════════
LLM2_NOMINATE_PROMPT = """你是十倍股猎手。给定产业链节点分析和联网搜索结果，为每个节点提名赔率最高的候选个股。

# 提名原则
- 主营集中：主营业务与节点精确对应，非多元化企业
- 赔率优先：市值偏小、卡位稀缺、盈利弹性大的优先
- 优先从联网搜索结果中提取被提及的公司
- 如果搜索结果未覆盖好的标的，用你对A股上市公司的了解补充
- 必须输出真实存在的A股公司（代码为6位数字）
- 每个节点提名2-3只，两节点合计不超过5只

# 输出JSON
{
  "nominations": [
    {"stock_code":"6位代码","stock_name":"公司简称","node_name":"所属节点名","reason":"提名理由"}
  ]
}"""

LLM2_SCORE_PROMPT = """你是十倍股赔率评估师。基于实时财务数据和V3案例库经验，对候选个股评分排序。输出前2名推荐。

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

1. 事件冲击比(45%)：暴露度 × 赔率杠杆
   暴露度 = 公司收入中事件品类的占比。用investoday的operating_data/business_status/main_business_conclusion三字段交叉判断。
   10=暴露>70% + 市值<50亿  (事件砸中小微盘,冲击极大)
   7 =暴露50-70% + 市值50-100亿
   4 =暴露30-50% + 市值100-200亿
   1 =暴露<30% 或 市值200-300亿

2. V3模式匹配(25%)：不猜具体利润倍数，匹配V3中4种十倍股原型
   10=亏损反转型 (寒武纪型): 当前亏损/微利,事件将赋予技术壁垒+市场垄断,利润从负→正大幅反转
   7 =隐形冠军型 (九安型): 公司不起眼,事件突然赋予垄断地位(FDA/牌照/独家认证),利润非线性暴增
   4 =加速成长型 (中际型): 公司已盈利,事件带来技术代际切换(800G→1.6T),量价齐升加速成长
   1 =周期β型 (协创型): 低壁垒蹭热度,涨幅来自市场情绪而非基本面质变
   未匹配到V3模式 → 给4分(中性),不扣分也不加分

3. 空间弹性(20%)：市值越小向上空间越大(已过滤>300亿)
   10=<30亿  8=30-50亿  6=50-100亿  4=100-200亿  2=200-300亿
   按腾讯财经市值数据直接阶梯打分。

4. 唯一性溢价(10%)：A股还有没有第二个纯正标的？
   10=该节点在A股唯一纯正标的
   7 =该节点仅2-3家纯正标的
   4 =该节点有4-8家公司
   1 =竞争激烈>8家

# V3案例库关键经验
42个A股十倍股起涨状态：市值中位数39亿，ROIC中位数0.4%，PE中位数44。
起涨时财务数据往往平庸甚至差——关键是事件兑现后的弹性。
利润截留能力是十倍股最重要特征：42例中90%处于中高利润截留节点。
寒武纪案例最典型：起涨ROIC=-23.8%，AI芯片TAM巨大，亏损反转型，47个点的反转创造29倍涨幅。

# 数据校验规则
- 主营与节点明显无关-> impact_score不超过3分，rationale标注"主营不匹配"
- 主营为X却被市场炒作Y概念-> 可给中等分，标注矛盾，impact_score扣1-2分
- investoday硬数据与雪球舆论冲突-> 以investoday为准，标注冲突

# 亏损不作惩罚
亏损是弹射起点。*ST退市风险在rationale中标注即可。

# 输出JSON
{
  "scored_stocks": [
    {"stock_code":"","stock_name":"","node_name":"所属节点","market_cap_billion":0,"impact_score":0,"v3match_score":0,"space_score":0,"scarcity_score":0,"total_score":0,"rationale":"","key_risk":""}
  ],
  "top_pick":{"stock_code":"","stock_name":"","node_name":"","investment_thesis":""},
  "runner_up":{"stock_code":"","stock_name":"","node_name":"","investment_thesis":""}
}
scored_stocks按total_score降序。top_pick = 总分最高者（优先第一节点），runner_up = 总分第二高者。
总分 = impact*0.45 + v3match*0.25 + space*0.20 + scarcity*0.10

# 阈值硬规则（不可违反）
- 所有候选股total_score均 < 6.5 -> top_pick和runner_up都填"无高赔率标的"
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
        rid = str(record.get("id", ""))

        if not news.strip():
            return {"status": "skipped", "error": "news_content 为空"}

        try:
            if eval_mode:
                # 评测模式：跳过联网搜索，纯推理
                web1, web2 = "", ""
            else:
                # Step 1: 联网搜索1 — 产业事件
                self._p(progress_cb, 1, "联网搜索1-产业事件")
                web1 = self._search(news, step_one)

            # Step 2: LLM #1 — 产业链推理
            self._p(progress_cb, 2, "LLM产业链推理")
            chain = self._llm(LLM1_PROMPT, self._msg_llm1(news, step_one, web1))

            # 校验 LLM #1 输出：industry空或top_two_nodes空 → 重试一次
            # 注意：JSON解析失败({error:...})也要重试，只跳过HTTP硬错误
            industry = chain.get("chain_overview", {}).get("industry", "")
            nodes = chain.get("top_two_nodes", [])
            is_hard_error = chain.get("error", "").startswith("API ")
            if (not industry or not nodes) and not is_hard_error:
                print(f"[LLM1-EMPTY] industry='{industry}' nodes={len(nodes)}, retrying...", flush=True)
                chain = self._llm(LLM1_PROMPT,
                    self._msg_llm1(news, step_one, web1)
                    + "\n\n上次输出industry或top_two_nodes为空。请确保chain_overview.industry不为空、top_two_nodes包含2个节点。")

            if not eval_mode:
                # Step 3: 联网搜索2 — 每节点1个query (并行)
                self._p(progress_cb, 3, "联网搜索2-节点详情")
                web2 = self._search_nodes(chain)

            # ── Pass 1: 先提名+评分 第一节点候选股 ──
            self._p(progress_cb, 4, "Pass1-提名节点1候选股")
            node1 = chain.get("top_two_nodes", [{}])[0]
            noms1 = self._llm(LLM2_NOMINATE_PROMPT, self._msg_nominate_single(node1, chain, web1, web2))

            self._p(progress_cb, 5, "Pass1-批量查询实时数据")
            enriched1 = self._enrich(noms1)

            self._p(progress_cb, 6, "Pass1-评分排序")
            msg1 = self._msg_score_single(node1, chain, enriched1, web2)
            scores1 = self._llm(LLM2_SCORE_PROMPT, msg1)
            scores1 = self._validate_and_retry_score(scores1, msg1)

            # 判断节点1最高分是否达标
            ss1 = scores1.get("scored_stocks", [])
            best1 = ss1[0].get("total_score", 0) if ss1 else 0
            node1_ok = best1 >= 6.5

            if node1_ok:
                # ✅ 节点1有达标标的，直接输出
                print(f"[PASS1-OK] node1 best={best1}, using node1 only", flush=True)
                final_scores = scores1
                final_noms = noms1
                final_enriched = enriched1
            else:
                # ❌ 节点1无达标标的 → Pass 2 加入节点2
                print(f"[PASS1-FAIL] node1 best={best1} < 6.5, adding node2...", flush=True)

                self._p(progress_cb, 7, "Pass2-提名节点2候选股")
                node2 = chain.get("top_two_nodes", [{}, {}])[1]
                noms2 = self._llm(LLM2_NOMINATE_PROMPT, self._msg_nominate_single(node2, chain, web1, web2))

                self._p(progress_cb, 8, "Pass2-批量查询实时数据")
                enriched2 = self._enrich(noms2)

                # 合并两节点数据
                all_enriched = {**enriched1, **enriched2}
                all_noms = {
                    "nominations": (noms1.get("nominations", []) + noms2.get("nominations", []))
                }

                self._p(progress_cb, 9, "Pass2-混合评分排序")
                msg_all = self._msg_score(chain, all_enriched, web2)
                final_scores = self._llm(LLM2_SCORE_PROMPT, msg_all)
                final_scores = self._validate_and_retry_score(final_scores, msg_all)
                final_noms = all_noms
                final_enriched = all_enriched

            return self._assemble(record, chain, final_noms, final_scores, final_enriched, web1, web2)

        except Exception as e:
            return {"status": "error", "error": str(e)[:1000], "record_id": rid}

    # ── Step 1: 联网搜索1 ──────────────

    def _search(self, news: str, step_one: str) -> str:
        """模板直出查询 —— 不浪费LLM调用改写query"""
        chain_hint = ""
        if step_one:
            parts = [p.strip() for p in step_one.split(",")]
            for p in parts:
                if p and "level" not in p.lower() and "产业模式" not in p:
                    chain_hint = p
                    break
        chain_clause = f"聚焦「{chain_hint}」产业链。" if chain_hint else ""

        query = (
            f"全网搜索并整理关于以下产业事件的深度分析报告。\n\n"
            f"资讯：{news}\n\n"
            f"{chain_clause}"
            f"要求：\n"
            f"1. 拆解产业链各环节（上游/中游/下游），列出每个环节真正有主营业务的A股公司（含代码）\n"
            f"2. 分析事件的利润分配格局——哪个环节截取最多价值？\n"
            f"3. 找出赔率最高的环节和个股\n"
            f"4. 优先引用券商研报和公司公告，区分硬事实与投资者讨论\n"
            f"5. 排除纯概念炒作无实质业务的公司"
        )
        return self._call_volc(query)

    # ── Step 2: LLM #1 ─────────────────

    @staticmethod
    def _msg_llm1(news: str, step_one: str, web: str) -> str:
        parts = [f"# 产业资讯\n{news}"]
        if step_one:
            parts.append(f"\n# Agent0初步分析\n{step_one}")
        if web:
            parts.append(f"\n# 联网搜索结果(雪球/全网,note置信度)\n{web[:3000]}")
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
                f"全网搜索「{name}」产业链节点，整理一份深度分析报告。\n\n"
                f"背景事件：{evt}\n\n"
                f"要求：\n"
                f"1. 只列出主营业务直接属于「{name}」的A股公司（含股票代码），"
                f"说明各家主营与此节点的关系\n"
                f"2. 哪些公司最符合此特征：{what}\n"
                f"3. 各公司的竞争壁垒、市场份额、近期业绩\n"
                f"4. 区分硬事实（财报/公告/研报）与软观点（投资者讨论）\n"
                f"5. 优先引用券商研报和公司公告等权威来源\n\n"
                f"重要约束：\n"
                f"- 排除仅因概念炒作被提及、但主营与「{name}」无关的公司\n"
                f"- 例如不要因为是军工股就归入商业航天，不要因为有AI概念就归入医疗设备\n"
                f"- 如果某公司主营产品与节点核心产品不是同一品类，不要列入\n"
                f"- 宁缺毋滥，只列出真正在此节点有实质业务的公司"
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
    def _msg_nominate_single(node: dict, chain: dict, web1: str, web2: str) -> str:
        """单节点提名：只为指定节点提名 2-5 只候选股"""
        node_name = node.get("node_name", "")
        what = node.get("what_to_look_for", "")
        pfa = json.dumps(chain.get("profit_flow_analysis", []), ensure_ascii=False, indent=2)

        parts = [
            f"# 目标节点: {node_name}",
            f"利润截留分: {node.get('profit_retention_score', 0)}",
            f"选股特征: {what}",
            f"入选理由: {node.get('justification', '')}",
            f"\n# 全部节点利润流分析\n{pfa}",
        ]
        if web2:
            parts.append(f"\n# 联网搜索结果\n{web2}")
        parts.append(f"\n请只为「{node_name}」这一个节点提名2-5只赔率最高的A股候选个股。不要提名其他节点的公司。")
        return "\n".join(parts)

    # ── Step 5: investoday 批量查询 ────

    def _enrich(self, noms: dict) -> dict:
        """A.tushare批量市值+PE+财务  B.investoday主营业务(仅保留评分有用的6字段)"""
        nominations = noms.get("nominations", [])
        codes = [n.get("stock_code", "") for n in nominations if n.get("stock_code")]
        if not codes:
            return {}

        enriched = {c: {} for c in codes}

        # ── A. tushare 批量市值+PE+流通盘+换手率 ──
        try:
            import tushare as ts
            with open('valuation_app/config.json') as f:
                cfg = json.load(f)
            pro = ts.pro_api(cfg.get('tushare_token', ''))

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
                        enriched[c]['market_cap'] = float(row['total_mv']) / 1e4  # 万元→亿
                        enriched[c]['pe_ttm'] = float(row['pe_ttm']) if row['pe_ttm'] else 0
                        enriched[c]['pb'] = float(row['pb']) if row['pb'] else 0
                        enriched[c]['total_share'] = float(row['total_share']) / 1e4  # 万股→亿股
                        enriched[c]['float_share'] = float(row['float_share']) / 1e4 if row['float_share'] else 0
                        enriched[c]['turnover_rate'] = float(row['turnover_rate']) if row['turnover_rate'] else 0
                except Exception:
                    pass
        except Exception as e:
            print(f'[tushare] error: {e}', flush=True)

        # ── B. investoday 主营业务（仅保留评分需要的6字段，砍brand_channel/tech_path_rd） ──
        KEEP_FIELDS = ['business_status','industry_chain_capacity','investment_theme',
                       'operating_data','development_prospect','main_business_conclusion']

        def fetch_business(code: str) -> tuple:
            try:
                biz = self.fetcher.fetch_business_themes(code)
                return code, {k: biz.get(k, '') or '' for k in KEEP_FIELDS}
            except Exception:
                return code, {}

        with ThreadPoolExecutor(max_workers=5) as ex:
            futures = [ex.submit(fetch_business, c) for c in codes]
            for f in as_completed(futures):
                try:
                    code, biz = f.result(timeout=30)
                    for k, v in biz.items():
                        enriched[code][k] = v
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
    def _msg_score(chain: dict, enriched: dict, web2: str) -> str:
        nodes = chain.get("top_two_nodes", [])
        nodes_text = json.dumps(nodes, ensure_ascii=False, indent=2)
        pfa = json.dumps(chain.get("profit_flow_analysis", []), ensure_ascii=False, indent=2)

        lines = [
            f"# 前2节点\n{nodes_text}",
            f"\n# 全部节点利润流分析\n{pfa}",
            f"\n# 候选个股实时数据",
        ]

        for code, data in enriched.items():
            mcap = data.get('market_cap', 0) or 0
            if mcap > 300:
                continue  # 硬过滤：市值>300亿直接跳过，不送入LLM

            pe = data.get('pe_ttm', 0) or 0
            pb = data.get('pb', 0) or 0
            ind = data.get('industry', '') or ''
            ts = data.get('total_share', 0) or 0
            fs = data.get('float_share', 0) or 0
            tr = data.get('turnover_rate', 0) or 0
            bs = data.get('business_status', '') or ''
            icc = data.get('industry_chain_capacity', '') or ''
            it = data.get('investment_theme', '') or ''
            od = data.get('operating_data', '') or ''
            dp = data.get('development_prospect', '') or ''
            mc = data.get('main_business_conclusion', '') or ''

            name = data.get('stock_name', '') or ''
            if not name:
                for n in (noms.get("nominations", []) or []):
                    if n.get("stock_code") == code:
                        name = n.get("stock_name", '')
                        break
            if not name:
                name = f'({code})'

            card = (
                f"\n### {name}({code})\n"
                f"市值{mcap:.0f}亿 | PE={pe:.1f} | PB={pb:.1f} | 换手率{tr:.1f}%\n"
                f"行业: {ind} | 总股本{ts:.1f}亿 | 流通{fs:.1f}亿\n"
                f"主营业务: {bs}\n"
                f"投资主题: {it}\n"
                f"产业链能力: {icc}\n"
                f"经营数据: {od}\n"
                f"发展前景: {dp}\n"
                f"主营结论: {mc}"
            )
            lines.append(card)

        if web2:
            lines.append(f"\n# 节点联网搜索结果\n{web2}")

        lines.append("\n请基于以上数据对候选股评分排序。")
        return "\n".join(lines)

    @staticmethod
    def _msg_score_single(node: dict, chain: dict, enriched: dict, web2: str) -> str:
        """单节点评分：只有一个节点的候选股，简单评分"""
        node_name = node.get("node_name", "")
        evt = chain.get("chain_overview", {}).get("event_summary", "")

        lines = [
            f"# 评分节点: {node_name}",
            f"事件: {evt}",
            f"\n# 候选个股实时数据",
        ]

        for code, data in enriched.items():
            mcap = data.get('market_cap', 0) or 0
            if mcap > 300:
                continue  # 硬过滤
            pe = data.get('pe_ttm', 0) or 0
            name = data.get('stock_name', code) or code
            ind = data.get('industry', '') or ''
            bs = data.get('business_status', '') or ''
            icc = data.get('industry_chain_capacity', '') or ''
            it = data.get('investment_theme', '') or ''
            od = data.get('operating_data', '') or ''
            mc = data.get('main_business_conclusion', '') or ''

            card = (
                f"\n### {name}({code})\n"
                f"市值{mcap:.0f}亿 | PE={pe:.1f} | 行业: {ind}\n"
                f"主营: {bs}\n"
                f"投资主题: {it}\n"
                f"产业链能力: {icc}\n"
                f"经营数据: {od}\n"
                f"主营结论: {mc}"
            )
            lines.append(card)

        if web2:
            lines.append(f"\n# 联网搜索结果\n{web2}")

        lines.append(f"\n请对以上「{node_name}」节点的候选股评分排序。每只打出impact/v3match/space/scarcity四个分，选出top_pick和runner_up。")
        return "\n".join(lines)

    def _validate_and_retry_score(self, scores: dict, msg: str) -> dict:
        """校验 LLM #2 输出：空则用同一份prompt重试一次"""
        ss = scores.get("scored_stocks", [])
        tp = scores.get("top_pick", {})
        if (not ss or (not tp.get("stock_code", "") and tp.get("stock_name") != "无高赔率标的")) and not scores.get("error", "").startswith("API "):
            print(f"[LLM2-EMPTY] scored_stocks={len(ss)} top_pick_code='{tp.get('stock_code','')}', retrying...", flush=True)
            scores = self._llm(LLM2_SCORE_PROMPT,
                msg + "\n\n上次输出缺少有效的scored_stocks或top_pick。请确保输出完整，top_pick和runner_up必须有stock_code。")
        return scores

    # ── 组装结果 ────────────────────────

    def _assemble(self, record, chain, noms, scores, enriched, web1, web2) -> dict:
        tp = scores.get("top_pick", {})
        ru = scores.get("runner_up", {})
        ss = scores.get("scored_stocks", [])

        # ── 归一化 top_pick/runner_up ──
        tp = _normalize_pick(tp, "top_pick")
        ru = _normalize_pick(ru, "runner_up")

        # 处理"无高赔率标的"
        tp_name = tp.get("stock_name", "")
        ru_name = ru.get("stock_name", "")
        is_no_pick = (tp_name == "无高赔率标的")
        is_no_runner = (ru_name == "无高赔率标的")

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
            "web_research": f"=== 产业事件搜索 ===\n{web1}\n\n=== 节点详情搜索 ===\n{web2}",
            "source_record_id": _safe_int(record.get("id", 0)),
            "industry_chain": chain.get("chain_overview", {}).get("industry", ""),
            "event_summary": chain.get("chain_overview", {}).get("event_summary", ""),
            "top_nodes_json": json.dumps(chain.get("top_two_nodes", []), ensure_ascii=False),
            "top5_json": json.dumps(ss[:5], ensure_ascii=False),
            "chain_analysis_json": json.dumps(chain, ensure_ascii=False),
            "stock_analysis_json": json.dumps(scores, ensure_ascii=False),
            "top_pick_code": "" if is_no_pick else tp.get("stock_code", ""),
            "top_pick_name": tp_name,
            "top_pick_node": "" if is_no_pick else tp.get("node_name", ""),
            "top_pick_score": "" if is_no_pick else (str(ss[0].get("total_score", "")) if ss else ""),
            "top_pick_thesis": "" if is_no_pick else tp.get("investment_thesis", ""),
            "runner_up_code": "" if is_no_runner else ru.get("stock_code", ""),
            "runner_up_name": ru_name,
            "runner_up_node": "" if is_no_runner else ru.get("node_name", ""),
            "runner_up_score": "" if is_no_runner else (str(ss[1].get("total_score", "")) if len(ss) > 1 else ""),
            "runner_up_thesis": "" if is_no_runner else ru.get("investment_thesis", ""),
        }

    # ── LLM 调用 ────────────────────────

    def _llm(self, system: str, user: str, label: str = "") -> dict:
        for attempt in range(3):
            try:
                r = requests.post(DEEPSEEK_URL, json={
                    "model": DEEPSEEK_MODEL,
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                    "max_tokens": 30720,
                    "stream": False, "temperature": 0,
                    "thinking": {"type": "enabled"},
                    "reasoning_effort": "max",
                }, headers={"Authorization": f"Bearer {self.dk}", "Content-Type": "application/json"}, timeout=600)
                if r.status_code != 200:
                    if attempt < 2: time.sleep(3 * (attempt + 1)); continue
                    return {"error": f"API {r.status_code}", "raw": r.text[:500]}
                content = r.json()["choices"][0]["message"]["content"]
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
                return {"error": str(e)[:500]}
        return {"error": "重试耗尽"}

    @staticmethod
    def _call_volc(query: str) -> str:
        try:
            r = requests.post(VOLC_URL, json={
                "bot_id": VOLC_BOT_ID, "stream": False,
                "messages": [{"role": "user", "content": query}],
            }, headers={"Authorization": f"Bearer {VOLC_KEY}", "Content-Type": "application/json"}, timeout=90)
            if r.status_code == 200:
                choices = r.json().get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", "")
        except Exception:
            pass
        return ""

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


def _normalize_pick(pick, label: str = "") -> dict:
    """归一化 top_pick/runner_up：LLM 有时返回纯字符串 "无高赔率标的" 而非 {"stock_name":"..."}"""
    if isinstance(pick, dict):
        return pick
    if isinstance(pick, str):
        return {"stock_name": pick, "stock_code": "", "node_name": "", "investment_thesis": ""}
    return {}
