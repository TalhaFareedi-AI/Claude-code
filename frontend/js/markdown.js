// A small, safe Markdown renderer. Text goes in, DOM nodes come out (no innerHTML).
// Supports: headings, paragraphs, bold, italic, code, fences, lists, tables, quotes, links (http/https only),
// and [[artifact:ID]] markers, which the caller turns into charts, quizzes and pictures.
import { h } from './dom.js';

const INLINE = /(`[^`\n]+`|\*\*[^*\n]+\*\*|__[^_\n]+__|\*[^*\s][^*\n]*?\*|\[[^\]\n]+\]\(https?:\/\/[^)\s]+\))/;

export function inline(text) {
  const out = [];
  for (const part of text.split(INLINE)) {
    if (!part) continue;
    if (part.startsWith('`') && part.endsWith('`') && part.length > 2) out.push(h('code', { text: part.slice(1, -1) }));
    else if ((part.startsWith('**') && part.endsWith('**') && part.length > 4) || (part.startsWith('__') && part.endsWith('__') && part.length > 4)) out.push(h('strong', null, inline(part.slice(2, -2))));
    else if (part.startsWith('*') && part.endsWith('*') && part.length > 2) out.push(h('em', null, inline(part.slice(1, -1))));
    else if (part.startsWith('[') && /\]\(https?:\/\//.test(part)) {
      const m = part.match(/^\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)$/);
      out.push(m ? h('a', { href: m[2], target: '_blank', rel: 'noopener noreferrer nofollow', text: m[1] }) : part);
    } else out.push(part);
  }
  return out;
}

const isBlockStart = (l) => /^(#{1,3}\s|```|>\s?|\s*[-*]\s+|\s*\d+[.)]\s+|---+\s*$|\[\[artifact:)/.test(l);
const cells = (l) => l.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim());

export function renderMarkdown(src, onArtifact) {
  const root = h('div', { class: 'md' });
  const lines = String(src || '').replace(/\r/g, '').split('\n');
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) { i++; continue; }
    const fence = line.match(/^```(\w*)/);
    if (fence) {
      const buf = []; i++;
      while (i < lines.length && !/^```/.test(lines[i])) buf.push(lines[i++]);
      i++;
      root.append(h('pre', null, h('code', { text: buf.join('\n') })));
      continue;
    }
    const art = line.trim().match(/^\[\[artifact:(a_[0-9a-f]+)\]\]$/);
    if (art) { const n = onArtifact && onArtifact(art[1]); if (n) root.append(n); i++; continue; }
    const hd = line.match(/^(#{1,3})\s+(.*)$/);
    if (hd) { root.append(h('h' + Math.min(3, hd[1].length), null, inline(hd[2]))); i++; continue; }
    if (/^---+\s*$/.test(line)) { root.append(h('hr')); i++; continue; }
    if (line.includes('|') && i + 1 < lines.length && /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(lines[i + 1])) {
      const head = cells(line); i += 2;
      const rows = [];
      while (i < lines.length && lines[i].includes('|') && lines[i].trim()) rows.push(cells(lines[i++]));
      root.append(h('table', null, h('thead', null, h('tr', null, head.map((c) => h('th', null, inline(c))))),
        h('tbody', null, rows.map((r) => h('tr', null, head.map((_, k) => h('td', null, inline(r[k] || ''))))))));
      continue;
    }
    if (/^>\s?/.test(line)) {
      const buf = [];
      while (i < lines.length && /^>\s?/.test(lines[i])) buf.push(lines[i++].replace(/^>\s?/, ''));
      root.append(h('blockquote', null, inline(buf.join(' '))));
      continue;
    }
    const li = line.match(/^(\s*)([-*]|\d+[.)])\s+(.*)$/);
    if (li) {
      const ordered = /\d/.test(li[2]);
      const list = h(ordered ? 'ol' : 'ul');
      while (i < lines.length) {
        const m = lines[i].match(/^(\s*)([-*]|\d+[.)])\s+(.*)$/);
        if (!m) break;
        if (m[1].length >= 2 && list.lastChild) {   // one nested level
          let sub = list.lastChild.querySelector(':scope > ul, :scope > ol');
          if (!sub) { sub = h(/\d/.test(m[2]) ? 'ol' : 'ul'); list.lastChild.append(sub); }
          sub.append(h('li', null, inline(m[3])));
        } else list.append(h('li', null, inline(m[3])));
        i++;
      }
      root.append(list);
      continue;
    }
    const buf = [line];
    i++;
    while (i < lines.length && lines[i].trim() && !isBlockStart(lines[i])) buf.push(lines[i++]);
    root.append(h('p', null, inline(buf.join(' '))));
  }
  return root;
}
