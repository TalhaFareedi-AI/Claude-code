// A small, safe Markdown + LaTeX math renderer. Text goes in, DOM nodes come out (no innerHTML).
// Supports: headings, paragraphs, bold, italic, code, fences, lists, tables, quotes, links (http/https only),
// LaTeX formulas ($$ ... $$ display math and \( ... \) inline math, never turning $5 and $10 into math),
// and [[artifact:ID]] markers, which the caller turns into charts, D3 diagrams, quizzes and pictures.
import { h, toast } from './dom.js';

const GREEK = {
  alpha: 'α', beta: 'β', gamma: 'γ', delta: 'δ', epsilon: 'ε', zeta: 'ζ', eta: 'η', theta: 'θ',
  iota: 'ι', kappa: 'κ', lambda: 'λ', mu: 'μ', nu: 'ν', xi: 'ξ', pi: 'π', rho: 'ρ', sigma: 'σ',
  tau: 'τ', phi: 'φ', chi: 'χ', psi: 'ψ', omega: 'ω',
  Gamma: 'Γ', Delta: 'Δ', Theta: 'Θ', Lambda: 'Λ', Xi: 'Ξ', Pi: 'Π', Sigma: 'Σ', Phi: 'Φ', Psi: 'Ψ', Omega: 'Ω',
  times: '×', div: '÷', cdot: '·', pm: '±', mp: '∓', le: '≤', leq: '≤', ge: '≥', geq: '≥',
  ne: '≠', neq: '≠', approx: '≈', equiv: '≡', to: '→', rightarrow: '→', leftarrow: '←',
  Rightarrow: '⇒', infty: '∞', partial: '∂', nabla: '∇', sum: '∑', prod: '∏', int: '∫',
  sqrt: '√', in: '∈', subset: '⊂', cup: '∪', cap: '∩', forall: '∀', exists: '∃',
};

function copyLatex(raw) {
  try {
    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(raw).then(() => toast('Copied LaTeX formula')).catch(() => {});
      return;
    }
  } catch { /* fallback below */ }
  const ta = document.createElement('textarea');
  ta.value = raw;
  document.body.appendChild(ta);
  ta.select();
  try { document.execCommand('copy'); toast('Copied LaTeX formula'); } catch { /* ignore */ }
  ta.remove();
}

export function formatMathDom(latex, displayMode = false) {
  const raw = String(latex || '').trim();
  let s = raw
    .replace(/\\left\s*([(\[{|])/g, '$1')
    .replace(/\\right\s*([)\]}|])/g, '$1')
    .replace(/\\text\s*\{([^}]*)\}/g, '$1')
    .replace(/\\mathrm\s*\{([^}]*)\}/g, '$1')
    .replace(/\\mathbf\s*\{([^}]*)\}/g, '$1');

  // Replace \frac{a}{b} with (a)/(b) or stacked fraction in display mode
  s = s.replace(/\\frac\s*\{([^{}]+)\}\s*\{([^{}]+)\}/g, (_, num, den) => `(${num}) / (${den})`);
  s = s.replace(/\\sqrt\s*\{([^{}]+)\}/g, (_, inner) => `√(${inner})`);
  s = s.replace(/\\([A-Za-z]+)/g, (m, cmd) => GREEK[cmd] || cmd);
  s = s.replace(/\^\{([^{}]+)\}/g, '^$1').replace(/_\{([^{}]+)\}/g, '_$1');

  const copyBtn = h('button', {
    type: 'button',
    class: 'math-copy',
    title: 'Copy LaTeX source',
    'aria-label': 'Copy LaTeX',
    text: 'Copy LaTeX',
    onclick: (e) => { e.stopPropagation(); copyLatex(raw); },
  });

  if (displayMode) {
    return h('div', { class: 'math-block', role: 'math', 'aria-label': raw },
      h('span', { class: 'math-expr', text: s }),
      copyBtn);
  }
  return h('span', { class: 'math-inline', role: 'math', 'aria-label': raw, title: `LaTeX: ${raw}` },
    h('span', { class: 'math-expr', text: s }),
    copyBtn);
}

const INLINE = /(`[^`\n]+`|\\\([\s\S]+?\\\)|\*\*[^*\n]+\*\*|__[^_\n]+__|\*[^*\s][^*\n]*?\*|\[[^\]\n]+\]\(https?:\/\/[^)\s]+\))/;

export function inline(text) {
  const out = [];
  for (const part of String(text || '').split(INLINE)) {
    if (!part) continue;
    if (part.startsWith('`') && part.endsWith('`') && part.length > 2) out.push(h('code', { text: part.slice(1, -1) }));
    else if (part.startsWith('\\(') && part.endsWith('\\)') && part.length > 4) out.push(formatMathDom(part.slice(2, -2), false));
    else if ((part.startsWith('**') && part.endsWith('**') && part.length > 4) || (part.startsWith('__') && part.endsWith('__') && part.length > 4)) out.push(h('strong', null, inline(part.slice(2, -2))));
    else if (part.startsWith('*') && part.endsWith('*') && part.length > 2) out.push(h('em', null, inline(part.slice(1, -1))));
    else if (part.startsWith('[') && /\]\(https?:\/\//.test(part)) {
      const m = part.match(/^\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)$/);
      out.push(m ? h('a', { href: m[2], target: '_blank', rel: 'noopener noreferrer nofollow', text: m[1] }) : part);
    } else out.push(part);
  }
  return out;
}

const isBlockStart = (l) => /^(#{1,3}\s|```|\$\$|>[\s]?|\s*[-*]\s+|\s*\d+[.)]\s+|---+\s*$|\[\[artifact:)/.test(l);
const cells = (l) => l.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim());

export function renderMarkdown(src, onArtifact) {
  const root = h('div', { class: 'md' });
  let cleaned = String(src || '').replace(/\r/g, '');
  // Hold an unclosed streaming $$ formula until its closing $$ arrives so broken code never flickers (page 30)
  const ddCount = (cleaned.match(/\$\$/g) || []).length;
  if (ddCount % 2 === 1) {
    const lastIdx = cleaned.lastIndexOf('$$');
    cleaned = cleaned.slice(0, lastIdx) + '\n*(rendering formula…)*';
  }
  const lines = cleaned.split('\n');
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) { i++; continue; }
    if (line.trim().startsWith('$$')) {
      const single = line.trim().match(/^\$\$(.+)\$\$$/);
      if (single) {
        root.append(formatMathDom(single[1], true));
        i++;
        continue;
      }
      const buf = [line.trim().slice(2)];
      i++;
      while (i < lines.length && !lines[i].includes('$$')) buf.push(lines[i++]);
      if (i < lines.length) {
        buf.push(lines[i].replace(/\$\$.*$/, ''));
        i++;
      }
      root.append(formatMathDom(buf.join(' '), true));
      continue;
    }
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
        if (m[1].length >= 2 && list.lastChild) {
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
