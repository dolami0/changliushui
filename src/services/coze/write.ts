import { COZE_BASE, TOKEN } from './client';

// ====== Coze 写入 ======

export async function cozeInsert(dbId: string, rows: Record<string, unknown>[]): Promise<boolean> {
  const resp = await fetch(`${COZE_BASE}/${dbId}/records`, {
    method: "POST", headers: { Authorization: `Bearer ${TOKEN}`, "Content-Type": "application/json" },
    body: JSON.stringify({ insert_rows: rows.map((r) => Object.fromEntries(Object.entries(r).map(([k, v]) => [k, String(v ?? "")]))), is_async: false }),
  });
  const d = (await resp.json()) as { code: number };
  return d.code === 0;
}

export async function cozeUpdate(dbId: string, recordId: string, fields: Record<string, string>): Promise<boolean> {
  const resp = await fetch(`${COZE_BASE}/${dbId}/records`, {
    method: "PUT", headers: { Authorization: `Bearer ${TOKEN}`, "Content-Type": "application/json" },
    body: JSON.stringify({ update_fields: Object.entries(fields).map(([k, v]) => ({ field_name: k, value: v })), filter: { logic: "and", conditions: [{ left: "id", operation: "equal", right: recordId }] }, is_async: false }),
  });
  const d = (await resp.json()) as { code: number };
  return d.code === 0;
}

export async function cozeUpsert(dbId: string, matchField: string, matchValue: string, row: Record<string, unknown>): Promise<boolean> {
  const qr = await fetch(`${COZE_BASE}/${dbId}/records/query`, {
    method: "POST", headers: { Authorization: `Bearer ${TOKEN}`, "Content-Type": "application/json" },
    body: JSON.stringify({ page_num: 1, page_size: 1, is_async: false, filter: { logic: "and", conditions: [{ left: matchField, operation: "equal", right: matchValue }] } }),
  });
  const qd = (await qr.json()) as { code: number; data?: { items: { id: string }[] } };
  const existingId = qd.data?.items?.[0]?.id;
  if (existingId) {
    return cozeUpdate(dbId, existingId, Object.fromEntries(Object.entries(row).map(([k, v]) => [k, String(v ?? "")])));
  }
  return cozeInsert(dbId, [row]);
}
