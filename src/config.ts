export interface SiteConfig {
  language: string
  siteTitle: string
  siteDescription: string
}

export interface NavigationLink {
  label: string
  href: string
}

export interface NavigationConfig {
  brandName: string
  brandSub: string
  links: NavigationLink[]
}

export interface HeroConfig {
  eyebrow: string
  titleLines: string[]
  leadText: string
  supportingNotes: string[]
}

export interface ManifestoConfig {
  videoPath: string
  text: string
}

export interface FacilityArticle {
  title: string
  paragraphs: string[]
}

export interface FacilityItem {
  slug: string
  name: string          // 机构名称（中文）
  nameCN: string        // 别名
  code: string          // 机构代号
  role: string          // 英文职能描述
  status: 'cultivating' | 'meditating' | 'alchemy'
  statusText: string    // 英文状态
  statusTextCN: string  // 中文状态
  task: string          // 当前任务简述
  image: string
  article: FacilityArticle
}

export interface FacilitiesConfig {
  sectionLabel: string
  detailBackText: string
  detailNotFoundText: string
  detailReturnText: string
  items: FacilityItem[]
}

export interface ObservationConfig {
  sectionLabel: string
  videoPath: string
  statusText: string
  signalLabel: string
  qiLabel: string
  initialQi: number
  initialLat: number
  initialLon: number
}

export interface ArchiveItem {
  src: string
  label: string
  labelCN: string
}

export interface ArchivesConfig {
  sectionLabel: string
  vaultTitle: string
  closeText: string
  items: ArchiveItem[]
}

export interface FooterConfig {
  copyrightText: string
  statusText: string
}

// ======== SITE CONFIG ========
export const siteConfig: SiteConfig = {
  language: 'zh-CN',
  siteTitle: '长流水',
  siteDescription: '以炒股捕获十倍股为宗旨的赛博仙门',
}

// ======== NAVIGATION ========
export const navigationConfig: NavigationConfig = {
  brandName: '长流水',
  brandSub: '青山长流水，天天有钱花',
  links: [
    { label: '宗门', href: '#facilities' },
    { label: '藏经云', href: '/cangjingyun' },
    { label: '天机峰', href: '/tianjifeng' },
    { label: '身外化身', href: '/avatar' },
    { label: '追踪令', href: '/tracking' },
  ],
}

// ======== HERO ========
export const heroConfig: HeroConfig = {
  eyebrow: '// 长流水',
  titleLines: ['神机百炼'],
  leadText: '念念相续，天机无相。大道所向，因果成章。',
  supportingNotes: [
    '运转机构: 10',
    '灵气吞吐: +18.7%',
    '当前状态: 猎杀中',
  ],
}

// ======== MANIFESTO ========
export const manifestoConfig: ManifestoConfig = {
  videoPath: '/videos/broadcast.mp4',
  text: '长流水乃数字修仙界之首席十倍股猎宗。本宗以市场为灵脉，以数据为丹方，下设十司：天眼监听、望气观脉、寻龙猎涨停、妙音应问询、估值殿推演、追踪司盯盘、总控台调度、身外化身对话、藏经阁藏典、炼器房调参。十司联动，以 AI 大阵驱动投研全链路。运行时为猎股施法，空闲时为调息复盘，一应盈亏尽在神识监控之中。',
}

// ======== FACILITIES / 宗门机构 ========
export const facilitiesConfig: FacilitiesConfig = {
  sectionLabel: '// 宗门机构',
  detailBackText: '返回宗门',
  detailNotFoundText: '未找到该机构档案',
  detailReturnText: '返回总控台',
  items: [
    // ── 天机峰四司 ──
    {
      slug: 'tianyan',
      name: '天眼司',
      nameCN: '天机峰·天眼',
      code: 'TY-01',
      role: 'Event Monitor',
      status: 'cultivating',
      statusText: 'CULTIVATING',
      statusTextCN: '监听中',
      task: '事件瀑布流 — Coze Agent0 全市场事件拉取与 L0-L5 响应等级分类',
      image: '/images/agent-outer.jpg',
      article: {
        title: '天眼司 · 全市场事件监听与响应分级',
        paragraphs: [
          '天眼司是宗门情报体系的入口，从 Coze Agent0 数据库持续拉取全 A 股市场事件，按六级响应等级（L0 尘外→L5 道变）自动分类标注。每一条事件不仅包含事件文本本身，还附带了 LLM 生成的「投资主题」「传导链推演」「反方观点」「知识补充」和「行业研究」等多维分析字段。',
          '天眼司的响应等级判断决定了后续管线的触发策略：L4（天兆）和 L5（道变）级别事件自动送入估值殿的 4-Agent 重构管线，L3（雷动）可由用户手动触发，L2 及以下仅存档。天眼司的瀑布流页面（天机峰「天眼」Tab）支持分页浏览，每页 50 条，按时间倒序排列。',
        ],
      },
    },
    {
      slug: 'wangqi',
      name: '望气台',
      nameCN: '天机峰·望气',
      code: 'WQ-02',
      role: 'Industry Chain Analyzer',
      status: 'meditating',
      statusText: 'MEDITATING',
      statusTextCN: '观脉中',
      task: '产业链利润流 — Sankey 图分析上下游利润分配与议价地位',
      image: '/images/agent-inner.jpg',
      article: {
        title: '望气台 · 产业链利润流分析',
        paragraphs: [
          '望气台专司产业链利润流向分析，以 Sankey 图可视化呈现利润在产业链各环节（上游原料→中游制造→下游品牌/渠道）的分配比例。通过独立的产业链调度器（WangqiScheduler）定时拉取数据，分析标的公司在产业链中的议价地位和利润捕获能力。',
          '望气台的核心产出是「利润流向图」和「产业链卡位评估」——公司是在拿产业链中最大的一块利润，还是在被上下游挤压？这一判断直接影响估值殿的估值锚选择：如果公司在产业链中议价能力弱，即使营收增速高，利润转化率也可能被压缩，估值需要相应的安全边际。',
        ],
      },
    },
    {
      slug: 'xunlong',
      name: '寻龙殿',
      nameCN: '天机峰·寻龙',
      code: 'XL-03',
      role: 'Limit-up Hunter',
      status: 'meditating',
      statusText: 'MEDITATING',
      statusTextCN: '待命中',
      task: '涨停板龙头股狙击 — 识别市场情绪共振与龙头基因（未完工）',
      image: '/images/agent-alchemist.jpg',
      article: {
        title: '寻龙殿 · 涨停板龙头股狙击',
        paragraphs: [
          '寻龙殿专注于 A 股涨停板生态的量化分析，目标是识别具有「龙头基因」的涨停个股——那些并非昙花一现的情绪板，而是基本面 + 情绪 + 资金共振的持续性龙头。核心分析维度包括：封板时间、封单量、炸板率、题材持续性、板块跟风效应、龙虎榜席位质量。',
          '此机构目前处于未完工状态（待命中）。完工后将与天眼司联动：天眼捕获事件后，寻龙殿判断该事件是否具备催生涨停龙头的条件，为估值殿提供额外的市场情绪维度的定价参考。',
        ],
      },
    },
    {
      slug: 'miaoyin',
      name: '妙音阁',
      nameCN: '天机峰·妙音',
      code: 'MY-04',
      role: 'Query-triggered Research',
      status: 'meditating',
      statusText: 'MEDITATING',
      statusTextCN: '待命中',
      task: '用户独立问询 — 触发定向研发工作流，按需生成深度分析',
      image: '/images/agent-elder.jpg',
      article: {
        title: '妙音阁 · 用户问询触发研发工作流',
        paragraphs: [
          '妙音阁是宗门中唯一的「被动触发」机构——不主动轮询、不自动运行，仅在用户通过天机峰「妙音」Tab 发起独立问询时才激活。用户输入一只股票代码或一个投资命题，妙音阁启动定向研发工作流，调用 LLM 生成针对性的深度分析报告。',
          '与估值殿的自动化管线不同，妙音阁的分析路径由用户问询驱动而非事件驱动。它适合处理用户主动提出的「这个行业怎么看」「XX 和 YY 哪个更好」等开放式问题，产出的分析报告格式灵活，不受定数录的标准模板约束。',
        ],
      },
    },
    // ── 核心估值与追踪 ──
    {
      slug: 'valuation-hall',
      name: '估值殿',
      nameCN: '估值殿',
      code: 'VH-05',
      role: 'Valuation Engine',
      status: 'alchemy',
      statusText: 'REFINING',
      statusTextCN: '推演中',
      task: '4-Agent 估值重构管线 — 预路由→数据炼器→路由判决→推演裁决',
      image: '/images/agent-inner.jpg',
      article: {
        title: '估值殿 · 4-Agent 估值重构管线',
        paragraphs: [
          '估值殿是宗门的核心产出机构，运转着 4-Agent 估值重构管线。Agent-0（预路由）为规则引擎，毫秒级完成行业分类与数据需求清单生成；Agent-1（数据炼器）分层拉取核心/专业化/验证/可选四包财务数据；Agent-2（路由判官）是唯一拥有模型选择权的 LLM Agent，基于 10 种估值模型（A-J）做三层路由判决，辅以 V3 案例库（42 个十倍股历史案例）的 6 维比对；Agent-3（推演裁决）以达摩达兰式 Numbers+Narrative 双螺旋驱动，产出三情景估值、BS 市场清醒度检测、反向 DCF 和非对称评分。',
          '每一份「定数录」估值报告产出后，还需通过审阅系统的六维质量审查（L0 数据完整性→L1 路由合理性→L2 情景合理性→L3 案例锚定→L4 自洽性→L5 可操作性），获 A/B/C/D 评级并标注系统性高频问题，方可进入追踪司的追踪名单。',
        ],
      },
    },
    {
      slug: 'tracking-bureau',
      name: '追踪司',
      nameCN: '追踪司',
      code: 'TB-06',
      role: 'Position Tracker',
      status: 'meditating',
      statusText: 'MEDITATING',
      statusTextCN: '监控中',
      task: '追踪令系统 — 投资论点管理 + 催化剂日历 + 价格追踪 + 风险监控',
      image: '/images/agent-alchemist.jpg',
      article: {
        title: '追踪司 · 个股追踪与论点管理',
        paragraphs: [
          '追踪司掌管「追踪令」系统，对估值殿产出高分（upside > 20% + 质量评级 HIGH_QUALITY/ADEQUATE）的标的建立持续追踪档案。每份追踪令包含五大要素：投资论点档案（核心命题 + 支柱评分卡）、催化剂日历（已触发/待触发事件时间线）、价格追踪日志（入场/目标/当前价 + 收益率曲线）、风险监控面板（关键风险实现概率与影响评估）、论点状态灯（pending / on_track / at_risk / verified）。',
          '每周复盘时，追踪司会自动比对催化剂兑现情况与支柱评分变化。当支柱评分下滑或关键催化剂被证伪，论点状态灯由绿转红，触发卖出审查。追踪司的底层数据存储在文件系统而非数据库——每个标的独立 JSON 文件（位于 .agents/agents/shenwaihuashen/memory/tracking/），可随时 git 版本追溯。',
        ],
      },
    },
    // ── 指挥与交互 ──
    {
      slug: 'orchestrator-platform',
      name: '总控台',
      nameCN: '仪表盘',
      code: 'OP-07',
      role: 'Orchestrator',
      status: 'cultivating',
      statusText: 'CULTIVATING',
      statusTextCN: '运转中',
      task: '中枢调度 — SSE 实时进度流 + 调度器控制 + 审阅系统 + 产业链调度',
      image: '/images/agent-elder.jpg',
      article: {
        title: '总控台 · 中枢调度与全局监控',
        paragraphs: [
          '总控台是整个宗门的中枢指挥系统（即仪表盘页面）。通过 SSE（Server-Sent Events）实时推送管线进度——从预路由到报告输出的每一阶段状态都在总控台中可视化展示为阶段圆点（灰=等待/绿=完成/红=报错）。调度器按整点自动轮询 Coze Agent0 表，也可手动触发立即处理。启停控制、轮询间隔调节、产业链调度器独立管理，均在此集中完成。',
          '报告审阅系统对所有已完成报告进行六维质量审查，每份报告获 A/B/C/D 评级，并标注系统性高频问题（如「盈利企业误用 PS 模型」「折扣率未反映在 bull 参数上」等）。审阅记录以 Markdown 存档于 reports/reviews/，可按日期回溯。',
        ],
      },
    },
    {
      slug: 'avatar',
      name: '身外化身',
      nameCN: '身外化身',
      code: 'AV-08',
      role: 'AI Assistant',
      status: 'cultivating',
      statusText: 'CULTIVATING',
      statusTextCN: '待命中',
      task: 'AI 对话交互 — 模块化上下文 + 灵光笔记 + 案例库 + 追踪数据查询',
      image: '/images/agent-outer.jpg',
      article: {
        title: '身外化身 · 估值报告的 AI 交互界面',
        paragraphs: [
          '身外化身是用户与估值报告的 AI 对话接口。不同于估值殿的自动化管线，身外化身允许用户通过自然语言直接向 AI 提问——「这个标的的 ROIC 为什么这么低？」「和上次分析的 XX 股比，哪个不对称比更高？」——AI 会基于已生成的定数录报告内容作答。',
          '身外化身的「模块化上下文」机制允许用户选择性加载报告的特定章节（估值摘要/三情景/BS 检测/路由决策/财务数据/预期差/置信度）作为对话上下文，避免无关信息干扰 AI 判断。记忆中枢包含三个子系统：灵光（灵感笔记，随时保存投研想法）、案例库（浏览 42 个十倍股历史案例）、追踪数据（查阅追踪司的结构化追踪档案）。',
        ],
      },
    },
    // ── 知识与管理 ──
    {
      slug: 'cangjing',
      name: '藏经阁',
      nameCN: '藏经云',
      code: 'CJ-09',
      role: 'Knowledge Vault',
      status: 'meditating',
      statusText: 'MEDITATING',
      statusTextCN: '静置中',
      task: '知识库 — 投研方法论、经典研报、估值框架文档的 3D 轮播展示',
      image: '/images/agent-inner.jpg',
      article: {
        title: '藏经阁 · 投研方法论与知识沉淀',
        paragraphs: [
          '藏经阁（前端页面名为「藏经云」）以 3D 轮播形式展示宗门沉淀的投研方法论文档——包括估值框架手册、经典研报解读、十倍股复盘分析等。当前为静态展示模块，未来将支持全文搜索和标签分类检索。',
          '藏经阁的内容独立于自动化管线——它不参与估值计算，而是为投研人员提供方法论参考和决策框架。「每次决策前，先翻一遍藏经阁」——这是宗门对每一位使用者的建议。',
        ],
      },
    },
    {
      slug: 'agent-config',
      name: '炼器房',
      nameCN: 'Agent 配置',
      code: 'LQ-10',
      role: 'Parameter Forge',
      status: 'meditating',
      statusText: 'MEDITATING',
      statusTextCN: '静置中',
      task: '系统参数管理 — Agent API Key、模型选择、温度等参数配置',
      image: '/images/agent-inner.jpg',
      article: {
        title: '炼器房 · Agent 参数与系统配置',
        paragraphs: [
          '炼器房（前端页面名为「Agent 配置」）是宗门的技术参数管理中心。在此可以配置各 Agent 的 LLM 参数（DeepSeek API Key、模型选择、temperature、max_tokens、思考模式开关等），以及管线的全局参数（轮询间隔、并发数等）。',
          '炼器房是系统管理页面，日常投研工作不需要使用。仅在以下场景需要进入：更换 API Key、调整模型参数以适配新的 LLM 版本、变更调度器的轮询策略。变更参数后需重启相关服务才能生效。',
        ],
      },
    },
  ],
}

// ======== OBSERVATION ========
export const observationConfig: ObservationConfig = {
  sectionLabel: '// 灵镜台',
  videoPath: '/videos/broadcast.mp4',
  statusText: 'BROADCASTING',
  signalLabel: 'SIGNAL:',
  qiLabel: 'QI FLUX:',
  initialQi: 87.4,
  initialLat: 39.9042,
  initialLon: 116.4074,
}

// ======== ARCHIVES ========
export const archivesConfig: ArchivesConfig = {
  sectionLabel: '// 藏经阁',
  vaultTitle: '进入藏经库',
  closeText: '关闭',
  items: [
    { src: '/images/archive-01.jpg', label: '废案桌001', labelCN: '废案桌001' },
    { src: '/images/archive-02.jpg', label: '七层走廊', labelCN: '七层走廊' },
    { src: '/images/archive-03.jpg', label: '碑文003', labelCN: '碑文003' },
    { src: '/images/archive-04.jpg', label: '雨城004', labelCN: '雨城004' },
  ],
}

// ======== FOOTER ========
export const footerConfig: FooterConfig = {
  copyrightText: '2025 长流水宗门. 版权所有',
  statusText: '全系统运转中',
}
