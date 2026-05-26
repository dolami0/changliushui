import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/** 简易 Markdown → HTML 渲染器 (增强版: #1-6 标题 | 分隔线 | 表格 | 列表 | 内联格式) */
export function renderMarkdown(md: string): string {
  if (!md) return '';
  const lines = md.split('\n');
  const out: string[] = [];
  let inTable = false;
  let tableHeaderDone = false;

  const push = (s: string) => out.push(s);

  // 内联格式化
  const fmt = (s: string): string =>
    s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
     .replace(/\*(.+?)\*/g, '<em>$1</em>')
     .replace(/`([^`]+)`/g, '<code>$1</code>');

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // ── 分隔线: *** 或 --- 独立一行 ──
    if (/^(\*{3,}|-{3,})\s*$/.test(line.trim())) {
      push('<hr>');
      continue;
    }

    // ── 标题: # ~ ###### ──
    const headingMatch = line.match(/^(#{1,6})\s+(.+)/);
    if (headingMatch) {
      const level = headingMatch[1].length;
      const content = fmt(headingMatch[2]);
      const sizes = [0, 24, 20, 17, 15, 14, 13];
      const margins = [0, 22, 18, 14, 10, 8, 6];
      push(`<h${Math.min(level, 6)} style="margin:${margins[level]}px 0 8px;font-size:${sizes[level]}px;font-weight:${level <= 2 ? 700 : 600};line-height:1.5;color:${level <= 2 ? '#ADFF00' : '#DDD'};">${content}</h${Math.min(level, 6)}>`);
      continue;
    }

    // ── 表格 ──
    if (line.trim().startsWith('|') && line.trim().endsWith('|')) {
      if (!inTable) { inTable = true; tableHeaderDone = false; push('<table>'); }
      const isSep = /^\|[\s\-:]+\|$/.test(line.trim());
      if (isSep) { tableHeaderDone = true; continue; }
      const cells = line.split('|').filter(c => c.trim());
      const tag = tableHeaderDone ? 'td' : 'th';
      push('<tr>');
      cells.forEach(c => { push(`<${tag}>${fmt(c.trim())}</${tag}>`) });
      push('</tr>');
      if (i + 1 >= lines.length || !lines[i + 1].trim().startsWith('|')) {
        push('</table>');
        inTable = false;
      }
      continue;
    }

    // ── 空行 ──
    if (!line.trim()) { push('<br>'); continue; }

    // ── 无序列表 ──
    const ulMatch = line.match(/^(\s*)[-*]\s+(.+)/);
    if (ulMatch) {
      push(`<li>${fmt(ulMatch[2])}</li>`);
      continue;
    }

    // ── 有序列表 ──
    const olMatch = line.match(/^(\s*)\d+[.)]?\s+(.+)/);
    if (olMatch) {
      push(`<li>${fmt(olMatch[2])}</li>`);
      continue;
    }

    // ── 块引用 ──
    if (line.startsWith('> ')) {
      push(`<blockquote>${fmt(line.slice(2))}</blockquote>`);
      continue;
    }

    // ── 普通段落 ──
    push(`<p>${fmt(line)}</p>`);
  }

  return out.join('\n');
}
