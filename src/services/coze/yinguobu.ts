import { cozeQuery, DB_YINGUOBU } from './client';

// ====== 因果簿 (7640928034144698374) ======
export interface YinguobuRecord {
  id: string;
  source_record_id: string;
  industry_chain: string;
  event_summary: string;
  chain_analysis_json: string;
  stock_analysis_json: string;
  top5_json: string;
  top_nodes_json: string;
  top_pick_code: string;
  top_pick_name: string;
  top_pick_score: string;
  top_pick_thesis: string;
  runner_up_code: string;
  runner_up_name: string;
  runner_up_score: string;
  runner_up_thesis: string;
  web_research: string;
  news_content: string;
  step_one_data: string;
  analysis_date: string;
  status: string;
  uuid: string;
  bstudio_create_time: string;
}

export async function fetchYinguobu(pageSize = 500): Promise<YinguobuRecord[]> {
  const result = await cozeQuery<YinguobuRecord>(DB_YINGUOBU, {
    page_size: pageSize,
    order_by: [{ direction: 'desc', field_name: 'bstudio_create_time' }],
  });
  return result.data?.items || [];
}

// 望气 (与因果簿同表, 字段映射为 IndustryChain 组件格式)
export interface WangqiResult {
  source_record_id: string;
  news_content: string;
  industry_chain: string;
  event_summary: string;
  top_nodes_json: string;
  top_pick_code: string;
  top_pick_name: string;
  top_pick_score: string;
  top_pick_thesis: string;
  runner_up_code: string;
  runner_up_name: string;
  runner_up_score: string;
  runner_up_thesis: string;
  top5_json: string;
  analysis_date: string;
  status: string;
}

export async function fetchWangqi(pageSize = 100): Promise<WangqiResult[]> {
  const items = await fetchYinguobu(pageSize);
  return items.map((r) => ({
    source_record_id: r.source_record_id || r.uuid || "",
    news_content: r.news_content || "",
    industry_chain: r.industry_chain || "",
    event_summary: r.event_summary || "",
    top_nodes_json: r.top_nodes_json || "",
    top_pick_code: r.top_pick_code || "",
    top_pick_name: r.top_pick_name || "",
    top_pick_score: r.top_pick_score || "",
    top_pick_thesis: r.top_pick_thesis || "",
    runner_up_code: r.runner_up_code || "",
    runner_up_name: r.runner_up_name || "",
    runner_up_score: r.runner_up_score || "",
    runner_up_thesis: r.runner_up_thesis || "",
    top5_json: r.top5_json || "",
    analysis_date: r.bstudio_create_time || "",
    status: r.status === "done" ? "done" : "pending",
  }));
}
