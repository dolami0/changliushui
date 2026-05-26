/* ------------------------------------------------------------------ */
/*  Agent 记忆系统 — localStorage 持久化                                */
/*                                                                    */
/*  灵光: 个人投资理念精华总结                                        */
/*  案例: 过往十倍股成功案例库                                        */
/*  工作流: 系统提示词 + 决策流程定义                                 */
/* ------------------------------------------------------------------ */

export interface LingGuang {
  id: string;
  title: string;
  content: string;
  createdAt: string;
  updatedAt: string;
}

export interface CaseItem {
  id: string;
  stockName: string;
  stockCode: string;
  entryPrice: string;
  exitPrice: string;
  gainMultiple: string;
  sector: string;
  logic: string;
  keySignals: string[];
  createdAt: string;
  // evals 扩展字段
  endState?: string;
  troughQuarter?: string;
  roicTrough?: number;
  roicPeak?: number;
  roicImprovement?: number;
  profitExpansion?: number;
  gmTrough?: number;
  gmPeak?: number;
  gmImprovement?: number;
  valuationDriven?: boolean;
  // 新增：完整案例库字段
  totalReturn?: number;
  totalReturnNote?: string;
  catalyst?: string;
  dominantFactor?: string;
  tags?: string[];
  returnType?: string;
  returnTypeDesc?: string;
  primaryDriver?: string;
  signalStrength?: string;
  startPE?: number;
  peakPE?: number;
  peExpansion?: number;
  startMcap?: number;
  peakMcap?: number;
  routingReason?: string;
  // 价格/技术数据
  startPrice?: number;
  startDate?: string;
  peakPrice?: number;
  peakDate?: string;
  actualReturnPct?: number;
  maxDrawdownPct?: number;
  maxDrawdownFromStartPct?: number;
  // V3 新增字段
  t2xMonths?: number;
  t5xMonths?: number;
  t10xMonths?: number;
  majorDrawdowns?: Array<{ period: string; depth_pct: number; trigger: string }>;
  asymmetryRatio?: string;
  marketShareTrough?: number;
  marketSharePeak?: number;
  unitExpansion?: number;
  decagenomeTags?: string[];
  benchmarkPeerName?: string;
  peerGainMultiple?: number;
  keyDivergence?: string;
  failureMode?: string[];
  expectationGap?: string;
  consensusBias?: string;
  shareholderEvolution?: string;
  macroRegime?: string;
  styleFactor?: string;
}

export interface WorkflowStep {
  id: string;
  order: number;
  name: string;
  description: string;
}

export interface AgentConfig {
  systemPrompt: string;
  model: string;
  apiKey: string;
  apiBase: string;
  enabled: boolean;
}

export interface AgentMemory {
  lingguangs: LingGuang[];
  cases: CaseItem[];
  workflowSteps: WorkflowStep[];
  config: AgentConfig;
}

const STORAGE_KEY = 'changliushui_agent_memory';

const DEFAULT_MEMORY: AgentMemory = {
  lingguangs: [
    {
      id: 'lg-001',
      title: '核心投资哲学',
      content: '十倍股的本质是产业趋势与企业生命周期的共振。寻找「小市值+大产业+强卡位」的三重叠加。市值低于100亿，行业处于0到1或1到10的爆发期，企业在产业链中占据不可替代的生态位。不追热点，只等风来。',
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    },
    {
      id: 'lg-002',
      title: '风控铁律',
      content: '单票仓位不超过20%。跌破建仓逻辑无条件止损。不碰大股东质押率超过50%的标的。业绩连续两季下滑立即重新评估。宁可错过，不可做错。',
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    },
  ],
  cases: [
    {
      id: 'case-001',
      stockName: '某新能源材料',
      stockCode: '68xxxx',
      entryPrice: '12.50',
      exitPrice: '138.00',
      gainMultiple: '10.0',
      sector: '锂电负极材料',
      logic: '新能源车渗透率突破10%拐点，负极材料供不应求，公司绑定宁德时代大单，产能释放节奏清晰。',
      keySignals: ['渗透率拐点', '龙头绑定', '产能释放'],
      createdAt: new Date().toISOString(),
    },
  ],
  workflowSteps: [
    { id: 'ws-001', order: 1, name: '产业验证', description: '验证产业链逻辑是否成立，上下游供需关系是否支撑' },
    { id: 'ws-002', order: 2, name: '财务体检', description: '检查营收增速、毛利率趋势、现金流质量' },
    { id: 'ws-003', order: 3, name: '估值重构', description: '用分部估值法或PS/PE band测算目标价空间' },
    { id: 'ws-004', order: 4, name: '风险扫描', description: '检查大股东质押、解禁计划、行业政策风险' },
    { id: 'ws-005', order: 5, name: '时机研判', description: '结合技术面和市场情绪判断最佳建仓窗口' },
  ],
  config: {
    systemPrompt: '你是长流水宗门的投资身外化身，一位专精十倍股猎杀的资深投资人。你的任务是：基于藏经云提供的个股预研数据，结合宗门积累的投资灵光（核心理念）和过往案例，做出严谨的投资决策。\n\n决策原则：\n1. 先看产业逻辑是否成立\n2. 再看财务数据是否支撑\n3. 再看估值空间是否足够\n4. 最后评估风险收益比\n\n输出格式：\n- 推演结论：通过 / 有条件通过 / 否决\n- 核心逻辑：简述关键判断依据\n- 匹配灵光：列出最相关的投资理念\n- 匹配案例：列出最相似的过往案例\n- 风险点：列出主要担忧\n- 建议仓位：基于 conviction 的仓位建议',
    model: 'gpt-4o',
    apiKey: '',
    apiBase: 'https://api.openai.com/v1',
    enabled: false,
  },
};

export function loadMemory(): AgentMemory {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      saveMemory(DEFAULT_MEMORY);
      return { ...DEFAULT_MEMORY };
    }
    const parsed = JSON.parse(raw) as AgentMemory;
    // Merge with defaults to ensure all fields exist
    return {
      lingguangs: parsed.lingguangs || DEFAULT_MEMORY.lingguangs,
      cases: parsed.cases || DEFAULT_MEMORY.cases,
      workflowSteps: parsed.workflowSteps || DEFAULT_MEMORY.workflowSteps,
      config: { ...DEFAULT_MEMORY.config, ...parsed.config },
    };
  } catch {
    return { ...DEFAULT_MEMORY };
  }
}

export function saveMemory(memory: AgentMemory): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(memory));
}

/* ------------------------------------------------------------------ */
/*  增删改查                                                            */
/* ------------------------------------------------------------------ */
export function addLingGuang(lg: Omit<LingGuang, 'id' | 'createdAt' | 'updatedAt'>): LingGuang {
  const memory = loadMemory();
  const item: LingGuang = {
    ...lg,
    id: `lg-${Date.now()}`,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  };
  memory.lingguangs.push(item);
  saveMemory(memory);
  return item;
}

export function updateLingGuang(id: string, updates: Partial<LingGuang>): void {
  const memory = loadMemory();
  const idx = memory.lingguangs.findIndex((l) => l.id === id);
  if (idx === -1) return;
  memory.lingguangs[idx] = { ...memory.lingguangs[idx], ...updates, updatedAt: new Date().toISOString() };
  saveMemory(memory);
}

export function deleteLingGuang(id: string): void {
  const memory = loadMemory();
  memory.lingguangs = memory.lingguangs.filter((l) => l.id !== id);
  saveMemory(memory);
}

export function addCase(c: Omit<CaseItem, 'id' | 'createdAt'>): CaseItem {
  const memory = loadMemory();
  const item: CaseItem = {
    ...c,
    id: `case-${Date.now()}`,
    createdAt: new Date().toISOString(),
  };
  memory.cases.unshift(item);
  saveMemory(memory);
  return item;
}

export function updateCase(id: string, updates: Partial<CaseItem>): void {
  const memory = loadMemory();
  const idx = memory.cases.findIndex((c) => c.id === id);
  if (idx === -1) return;
  memory.cases[idx] = { ...memory.cases[idx], ...updates };
  saveMemory(memory);
}

export function deleteCase(id: string): void {
  const memory = loadMemory();
  memory.cases = memory.cases.filter((c) => c.id !== id);
  saveMemory(memory);
}

export function updateConfig(updates: Partial<AgentConfig>): void {
  const memory = loadMemory();
  memory.config = { ...memory.config, ...updates };
  saveMemory(memory);
}

/* ------------------------------------------------------------------ */
/*  决策上下文组装 — 将藏经云记录 + 灵光 + 案例组合成完整 prompt         */
/* ------------------------------------------------------------------ */
import { type CozeRecord } from './cozeApi';

export interface DecisionContext {
  record: CozeRecord;
  matchedLingguangs: LingGuang[];
  matchedCases: CaseItem[];
  systemPrompt: string;
  workflowSteps: WorkflowStep[];
  assembledPrompt: string;
}

function simpleSimilarity(text: string, keywords: string[]): number {
  const t = text.toLowerCase();
  let score = 0;
  for (const k of keywords) {
    if (t.includes(k.toLowerCase())) score += 1;
  }
  return score;
}

export function buildDecisionContext(
  record: CozeRecord,
  memory: AgentMemory
): DecisionContext {
  // 提取记录关键词用于匹配
  const keywords = [
    record.stock_name,
    record.stock_code,
    record.source,
    record.cylfx,
    record.background?.slice(0, 50),
  ].filter(Boolean) as string[];

  // 匹配灵光（简单文本相似度）
  const scoredLg = memory.lingguangs
    .map((lg) => ({
      ...lg,
      score: simpleSimilarity(lg.content + lg.title, keywords),
    }))
    .sort((a, b) => b.score - a.score);
  const matchedLingguangs = scoredLg.slice(0, 3);

  // 匹配案例（V3多维：行业/终态/标签/催化剂/decagenome/基因向量/驱动因子）
  const recordText = [
    record.stock_name, record.stock_code, record.cylfx,
    record.background, record.analysis_report,
    record.high_yield_investment_opportunity,
  ].filter(Boolean).join(' ');
  const recordLower = (recordText || '').toLowerCase();
  const recordCylfx = (record.cylfx || '').toLowerCase();

  const scoredCases = memory.cases
    .map((c) => {
      const caseText = [
        c.sector, c.logic, c.endState, c.catalyst,
        c.dominantFactor, c.returnType, c.primaryDriver,
        ...(c.tags || []), ...(c.decagenomeTags || []),
        c.expectationGap, c.consensusBias, c.macroRegime,
        c.styleFactor, c.shareholderEvolution,
      ].filter(Boolean).join(' ');
      const caseLower = caseText.toLowerCase();
      let score = 0;

      // 文本关键词
      for (const k of keywords) {
        if (caseLower.includes(k.toLowerCase())) score += 2;
      }

      // 产业链/行业
      if (recordCylfx && (c.sector || '').toLowerCase().includes(recordCylfx)) score += 8;
      if (recordCylfx && caseLower.includes(recordCylfx)) score += 4;

      // 终态匹配
      if (c.endState && recordLower.includes((c.endState || '').toLowerCase())) score += 3;

      // 标签+decagenome匹配
      const allTags = [...(c.tags || []), ...(c.decagenomeTags || [])];
      for (const tag of allTags) {
        if (recordLower.includes(tag.toLowerCase())) score += 3;
      }

      // 催化剂
      if (c.catalyst && recordLower.includes((c.catalyst || '').slice(0, 4).toLowerCase())) score += 2;

      // 驱动因子匹配
      if (c.primaryDriver && recordLower.includes((c.primaryDriver || '').toLowerCase())) score += 3;

      // 宏观环境匹配
      if (c.macroRegime && recordLower.includes((c.macroRegime || '').toLowerCase())) score += 2;

      return { ...c, score };
    })
    .sort((a, b) => b.score - a.score);
  const matchedCases = scoredCases.slice(0, 5);

  // 组装完整prompt
  const recordContext = `
=== 藏经云个股预研数据 ===
股票名称: ${record.stock_name || '—'}
股票代码: ${record.stock_code || '—'}
产业链: ${record.cylfx || '—'}
来源: ${record.source || '—'}
综合评分: ${record.comprehensive_score || '—'}
潜力涨幅: ${record.potential_increase || '—'}
已推演: ${record.is_analyzed === 'false' ? '否' : '是'}

公司背景:
${record.background || '暂无'}

分析报告:
${record.analysis_report || '暂无'}

高收益投资机会:
${record.high_yield_investment_opportunity || '暂无'}

知识库:
${record.knowledge || '暂无'}
`;

  const lingguangContext = matchedLingguangs.length > 0
    ? `\n=== 匹配的投资灵光 ===\n${matchedLingguangs.map((lg) => `[${lg.title}] ${lg.content}`).join('\n\n')}`
    : '';

  const caseContext = matchedCases.length > 0
    ? `\n=== 匹配的过往十倍股案例 (按相关度排序，共${matchedCases.length}条) ===\n${matchedCases.map((c, i) => {
        const parts = [`${i + 1}. ${c.stockName}(${c.stockCode}) · ${c.sector || '—'}`];
        if (c.endState) parts.push(`   终态: ${c.endState}`);
        if (c.returnType) parts.push(`   回报类型: ${c.returnType}`);
        if (c.gainMultiple) parts.push(`   总回报: ${c.gainMultiple}x`);
        if (c.actualReturnPct != null) parts.push(`   实际涨幅: +${c.actualReturnPct}% (${c.startDate || '?'} → ${c.peakDate || '?'})`);
        if (c.roicImprovement != null) parts.push(`   ROIC改善: +${c.roicImprovement}ppt (${c.roicTrough}%→${c.roicPeak}%)`);
        if (c.maxDrawdownPct != null) parts.push(`   最大回撤: -${c.maxDrawdownPct}%`);
        if (c.catalyst) parts.push(`   催化剂: ${c.catalyst}`);
        if (c.dominantFactor) parts.push(`   主导因子: ${c.dominantFactor}`);
        if (c.primaryDriver) parts.push(`   主驱动: ${c.primaryDriver}`);
        if (c.t2xMonths != null) parts.push(`   翻倍速度: 2x/${c.t2xMonths}月 5x/${c.t5xMonths || '—'}月 10x/${c.t10xMonths || '—'}月`);
        if (c.expectationGap) parts.push(`   预期差: ${c.expectationGap}`);
        if (c.decagenomeTags && c.decagenomeTags.length > 0) parts.push(`   基因标签: ${c.decagenomeTags.join(', ')}`);
        if (c.benchmarkPeerName) parts.push(`   对照案例: ${c.benchmarkPeerName}(${c.peerGainMultiple}x) — ${c.keyDivergence || ''}`);
        if (c.tags && c.tags.length > 0) parts.push(`   标签: ${c.tags.join(', ')}`);
        return parts.join('\n');
      }).join('\n\n')}`
    : '';

  const workflowContext = memory.workflowSteps.length > 0
    ? `\n=== 决策工作流 ===\n${memory.workflowSteps.sort((a, b) => a.order - b.order).map((s) => `${s.order}. ${s.name}: ${s.description}`).join('\n')}`
    : '';

  const assembledPrompt = `${recordContext}${lingguangContext}${caseContext}${workflowContext}\n\n请基于以上数据，按照系统提示词的要求做出投资决策分析。`;

  return {
    record,
    matchedLingguangs,
    matchedCases,
    systemPrompt: memory.config.systemPrompt,
    workflowSteps: memory.config.enabled ? memory.workflowSteps : [],
    assembledPrompt,
  };
}

/* ------------------------------------------------------------------ */
/*  AI 调用                                                             */
/* ------------------------------------------------------------------ */
export async function callAgentAI(
  context: DecisionContext,
  onStream?: (chunk: string) => void
): Promise<string> {
  const memory = loadMemory();
  const config = memory.config;

  if (!config.apiKey) {
    throw new Error('API Key 未设置，请先在身外化身配置页填写');
  }

  const messages = [
    { role: 'system' as const, content: config.systemPrompt },
    { role: 'user' as const, content: context.assembledPrompt },
  ];

  const resp = await fetch(`${config.apiBase}/chat/completions`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${config.apiKey}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      model: config.model || 'gpt-4o',
      messages,
      stream: !!onStream,
      temperature: 0.3,
    }),
  });

  if (!resp.ok) {
    const errText = await resp.text().catch(() => 'Unknown error');
    throw new Error(`AI 调用失败 (${resp.status}): ${errText}`);
  }

  if (onStream && resp.body) {
    // Streaming mode
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let fullText = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const chunk = decoder.decode(value, { stream: true });
      const lines = chunk.split('\n').filter((l) => l.trim().startsWith('data: '));
      for (const line of lines) {
        const data = line.slice(6);
        if (data === '[DONE]') continue;
        try {
          const parsed = JSON.parse(data);
          const content = parsed.choices?.[0]?.delta?.content;
          if (content) {
            fullText += content;
            onStream(content);
          }
        } catch {
          // ignore parse errors
        }
      }
    }
    return fullText;
  }

  const data = await resp.json();
  return data.choices?.[0]?.message?.content || '无返回内容';
}
