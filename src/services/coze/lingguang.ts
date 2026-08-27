import { cozeQuery, fetchAll, sanitizeJson, DB_LINGGUANG } from './client';
import { cozeUpdate, cozeUpsert } from './write';

// ====== 灵光 (DB_LINGGUANG) ======

export interface LingguangItem {
  id: string; title: string; content: string;
  tags: string[]; source: string; confidence: number;
  matches: unknown[]; revisionHistory: unknown[];
  createdAt: string; updatedAt: string;
}

function toLingguang(row: Record<string, string>): LingguangItem {
  return {
    id: row.slug || "", title: row.title || "", content: row.content || "",
    tags: JSON.parse(sanitizeJson(row.tags_json || "[]")), source: row.source || "",
    confidence: Number(row.confidence) || 0,
    matches: JSON.parse(sanitizeJson(row.matches_json || "[]")),
    revisionHistory: JSON.parse(sanitizeJson(row.revision_json || "[]")),
    createdAt: row.created_at || "", updatedAt: row.updated_at || "",
  };
}

export async function fetchLingguang(): Promise<LingguangItem[]> {
  const items = await fetchAll<Record<string, string>>(DB_LINGGUANG);
  return items.map(toLingguang);
}

export async function fetchLingguangBySlug(slug: string): Promise<LingguangItem | null> {
  const result = await cozeQuery<Record<string, string>>(DB_LINGGUANG, {
    page_size: 1, filter: { logic: "and", conditions: [{ left: "slug", operation: "equal", right: slug }] },
  });
  return result.data?.items?.length ? toLingguang(result.data.items[0]!) : null;
}

export async function saveLingguang(item: LingguangItem): Promise<boolean> {
  item.updatedAt = new Date().toISOString();
  if (!item.createdAt) item.createdAt = item.updatedAt;
  return cozeUpsert(DB_LINGGUANG, "slug", item.id, {
    slug: item.id, title: item.title, content: item.content,
    tags_json: JSON.stringify(item.tags), source: item.source,
    confidence: String(item.confidence), matches_json: JSON.stringify(item.matches),
    revision_json: JSON.stringify(item.revisionHistory),
    created_at: item.createdAt, updated_at: item.updatedAt,
  });
}

export async function deleteLingguang(slug: string): Promise<boolean> {
  // Coze 不支持 delete API, 需要先查 id 再... 直接尝试更新为标记删除
  const r = await cozeQuery<{ id: string }>(DB_LINGGUANG, {
    page_size: 1, filter: { logic: "and", conditions: [{ left: "slug", operation: "equal", right: slug }] },
  });
  const id = r.data?.items?.[0]?.id;
  if (!id) return false;
  return cozeUpdate(DB_LINGGUANG, id, { updated_at: new Date().toISOString(), title: "[已删除]" });
}
