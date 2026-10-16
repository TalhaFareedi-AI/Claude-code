// Interactive chart (section 5). The AI wrote a recipe once; this file draws it and redraws on every
// slider move with no server call, so a slider move costs 0 tokens. Pure SVG, no libraries.
import { h, svg, fmtNum } from './dom.js';
import { compile } from './formula.js';

const COLORS = ['var(--c1)', 'var(--c2)', 'var(--c3)', 'var(--c4)', 'var(--c5)', 'var(--c6)'];
const M = { l: 56, r: 14, t: 14, b: 38 };

function niceTicks(lo, hi, n = 5) {
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) return [0, 1];
  if (!(hi > lo)) {
    const pad = Math.abs(lo) * 0.05 || 1;
    const lower = lo - pad, upper = hi + pad;
    if (Number.isFinite(lower)) lo = lower;
    if (Number.isFinite(upper)) hi = upper;
  }
  const span = hi - lo, step0 = span / n;
  // Finite recipes may have an overflowing range, or a range smaller than one
  // representable tick at this magnitude. Endpoints give those ranges a scale.
  if (!Number.isFinite(span) || !(step0 > 0)) return [lo, hi];
  const mag = Math.pow(10, Math.floor(Math.log10(step0)));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= step0) || 10 * mag;
  if (!Number.isFinite(step) || !(step > 0)) return [lo, hi];
  const start = Math.floor(lo / step) * step, out = [];
  // Never increment a float until it passes a bound: v + step can equal v and
  // freeze the tab. Index-based ticks also keep ordinary ranges evenly spaced.
  for (let k = 0; k < 32; k++) {
    const v = start + k * step;
    if (!Number.isFinite(v) || (out.length && v <= out[out.length - 1])) return [lo, hi];
    out.push(v);
    if (v >= hi) return out.length > 1 ? out : [lo, hi];
  }
  return [lo, hi];
}

export function renderChart(recipe) {
  // Each chart owns its geometry, including the closures used by hover events.
  let W = 640, H = 320;
  const inputs = recipe.inputs || [];
  const values = Object.fromEntries(inputs.map((i) => [i.id, i.value]));
  const isCat = recipe.chart === 'bar' || recipe.chart === 'pie';
  const lines = isCat ? [] : (recipe.lines || []).map((l) => ({ name: l.name, f: compile(l.formula) }));
  const cats = isCat ? (recipe.data || []).map((d) => ({ label: d.label, f: compile(d.formula) })) : [];
  const xFrom = isCat ? null : compile(recipe.x.from), xTo = isCat ? null : compile(recipe.x.to);
  const steps = recipe.steps || 60;

  const readouts = {};
  const controls = h('div', { class: 'chart-controls' }, inputs.map((i) => {
    const out = h('b', { text: fmtNum(i.value) });
    readouts[i.id] = out;
    const input = h('input', {
      type: i.type === 'slider' ? 'range' : 'number', id: `ctl-${Math.random().toString(36).slice(2, 8)}`,
      min: i.type === 'slider' ? i.min : null, max: i.type === 'slider' ? i.max : null, step: i.type === 'slider' ? i.step : 'any', value: i.value,
      'aria-label': i.label,
    });
    input.addEventListener('input', () => {
      const v = parseFloat(input.value);
      if (Number.isFinite(v)) { values[i.id] = v; out.textContent = fmtNum(v); schedule(); }
    });
    input.dataset.id = i.id;
    return h('div', { class: 'ctl' }, h('label', null, h('span', { text: i.label }), out), input);
  }));

  const box = h('div', { class: 'chart-box' });
  const tip = h('div', { class: 'tip', hidden: true });
  const legend = h('div', { class: 'legend' });
  const note = h('p', { class: 'muted tiny' });
  const reset = h('button', { type: 'button', class: 'btn small', text: 'Reset sliders', onclick: () => {
    for (const i of inputs) values[i.id] = i.value;
    controls.querySelectorAll('input').forEach((el) => { el.value = values[el.dataset.id]; readouts[el.dataset.id].textContent = fmtNum(values[el.dataset.id]); });
    draw();
  } });
  const root = h('div', { class: 'art chart', role: 'group', 'aria-label': `Chart: ${recipe.title}` },
    h('h3', { text: recipe.title }), inputs.length ? controls : null, box, legend, note, inputs.length ? reset : null);
  box.append(tip);

  let raf = 0;
  function schedule() { if (!raf) raf = requestAnimationFrame(() => { raf = 0; draw(); }); }

  function compute() {
    if (isCat) {
      const vals = cats.map((c) => { try { return c.f(values); } catch { return NaN; } });
      return { labels: cats.map((c) => c.label), series: [{ name: recipe.title, vals }] };
    }
    let lo, hi;
    try { lo = xFrom(values); hi = xTo(values); } catch { lo = 0; hi = 1; }
    if (!Number.isFinite(lo) || !Number.isFinite(hi) || hi <= lo) { lo = 0; hi = 1; }
    const xs = Array.from({ length: steps + 1 }, (_, k) => lo * (1 - k / steps) + hi * (k / steps));
    const series = lines.map((l) => ({ name: l.name, vals: xs.map((x) => { try { return l.f({ ...values, x }); } catch { return NaN; } }) }));
    return { xs, series };
  }

  function draw() {
    box.querySelector('svg')?.remove();
    W = Math.round(Math.max(280, Math.min(640, box.clientWidth || 600)));
    H = W < 460 ? 250 : 320;
    const data = compute();
    const bad = data.series.some((s) => s.vals.some((v) => !Number.isFinite(v)));
    note.textContent = bad ? 'Some values cannot be worked out at these slider settings, so the line has gaps.' : '';
    legend.replaceChildren(...data.series.map((s, k) => h('span', null, h('i', { style: `background:${COLORS[k % 6]}` }), s.name)));
    if (recipe.chart === 'pie') return drawPie(data);
    const root = svg('svg', { class: 'chart-svg', viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': recipe.title });
    const all = data.series.flatMap((s) => s.vals).filter(Number.isFinite);
    let lo = Math.min(...all, recipe.chart === 'line' || recipe.chart === 'scatter' ? Infinity : 0);
    let hi = Math.max(...all, -Infinity);
    if (!all.length) { lo = 0; hi = 1; }
    if (recipe.chart === 'bar' || recipe.chart === 'area') lo = Math.min(lo, 0);
    const yt = niceTicks(lo, hi), y0 = yt[0], y1 = yt[yt.length - 1];
    const px = (v, a, b, lo2, hi2) => {
      const span = hi2 - lo2;
      const ratio = Number.isFinite(span) ? (v - lo2) / (span || 1) : (v / 2 - lo2 / 2) / (hi2 / 2 - lo2 / 2);
      return a + ratio * (b - a);
    };
    const Y = (v) => px(v, H - M.b, M.t, y0, y1);
    for (const t of yt) {
      root.append(svg('line', { class: 'grid', x1: M.l, x2: W - M.r, y1: Y(t), y2: Y(t) }));
      root.append(svg('text', { x: M.l - 8, y: Y(t) + 4, 'text-anchor': 'end' }, fmtNum(t)));
    }
    root.append(svg('line', { class: 'axis', x1: M.l, x2: W - M.r, y1: H - M.b, y2: H - M.b }));
    const hover = svg('g', { 'pointer-events': 'none' });
    let onMove;
    if (isCat) {
      const n = data.labels.length, bw = (W - M.l - M.r) / n;
      data.labels.forEach((lab, k) => {
        const v = data.series[0].vals[k];
        if (Number.isFinite(v)) root.append(svg('rect', { x: M.l + k * bw + bw * 0.15, width: bw * 0.7, y: Math.min(Y(v), Y(0)), height: Math.abs(Y(v) - Y(0)), fill: COLORS[k % 6], rx: 3 }));
        root.append(svg('text', { x: M.l + k * bw + bw / 2, y: H - M.b + 16, 'text-anchor': 'middle' }, lab.length > 10 ? lab.slice(0, 9) + '…' : lab));
      });
      onMove = (ux) => { const k = Math.min(n - 1, Math.max(0, Math.floor((ux - M.l) / bw))); return { x: M.l + k * bw + bw / 2, head: data.labels[k], rows: [[recipe.title, data.series[0].vals[k], COLORS[k % 6]]], pts: [] }; };
    } else {
      const xs = data.xs, xlo = xs[0], xhi = xs[xs.length - 1], X = (v) => px(v, M.l, W - M.r, xlo, xhi);
      for (const t of niceTicks(xlo, xhi)) {
        if (t < xlo - 1e-9 || t > xhi + 1e-9) continue;
        root.append(svg('line', { class: 'grid', x1: X(t), x2: X(t), y1: M.t, y2: H - M.b, opacity: 0.4 }));
        root.append(svg('text', { x: X(t), y: H - M.b + 16, 'text-anchor': 'middle' }, fmtNum(t)));
      }
      root.append(svg('text', { x: (M.l + W - M.r) / 2, y: H - 4, 'text-anchor': 'middle' }, recipe.x.label));
      data.series.forEach((s, k) => {
        let d = '', pen = false;
        s.vals.forEach((v, j) => { if (Number.isFinite(v)) { d += `${pen ? 'L' : 'M'}${X(xs[j]).toFixed(1)},${Y(v).toFixed(1)}`; pen = true; } else pen = false; });
        if (recipe.chart === 'scatter') {
          s.vals.forEach((v, j) => { if (Number.isFinite(v) && j % Math.max(1, Math.floor(steps / 40)) === 0) root.append(svg('circle', { cx: X(xs[j]), cy: Y(v), r: 3.5, fill: COLORS[k % 6] })); });
        } else {
          if (recipe.chart === 'area' && d && !bad) root.append(svg('path', { d: `${d}L${X(xhi)},${Y(0)}L${X(xlo)},${Y(0)}Z`, fill: COLORS[k % 6], opacity: 0.18 }));
          root.append(svg('path', { d, fill: 'none', stroke: COLORS[k % 6], 'stroke-width': 2.4, 'stroke-linejoin': 'round', 'stroke-linecap': 'round' }));
        }
      });
      onMove = (ux) => {
        const j = Math.round(((Math.min(W - M.r, Math.max(M.l, ux)) - M.l) / (W - M.l - M.r)) * steps);
        return { x: X(xs[j]), head: `${recipe.x.label}: ${fmtNum(xs[j])}`, rows: data.series.map((s, k) => [s.name, s.vals[j], COLORS[k % 6]]),
          pts: data.series.map((s, k) => Number.isFinite(s.vals[j]) ? [X(xs[j]), Y(s.vals[j]), COLORS[k % 6]] : null).filter(Boolean) };
      };
    }
    root.append(hover);
    attachHover(root, hover, onMove);
    box.prepend(root);
  }

  function attachHover(root, hover, onMove) {
    const show = (ev) => {
      const r = root.getBoundingClientRect();
      const ux = ((ev.clientX - r.left) / r.width) * W;
      const info = onMove(ux);
      hover.replaceChildren(svg('line', { x1: info.x, x2: info.x, y1: M.t, y2: H - M.b, stroke: 'var(--muted)', 'stroke-dasharray': '3 3' }),
        ...info.pts.map(([x, y, c]) => svg('circle', { cx: x, cy: y, r: 4.5, fill: c, stroke: 'var(--panel)', 'stroke-width': 2 })));
      tip.replaceChildren(h('div', { text: info.head, style: 'font-weight:600' }),
        ...info.rows.map(([n, v, c]) => h('div', null, h('i', { style: `display:inline-block;width:8px;height:8px;border-radius:50%;background:${c};margin-right:6px` }), `${n}: ${fmtNum(v)}`)));
      tip.hidden = false;
      const bx = box.getBoundingClientRect();
      const left = Math.min(Math.max(8, (info.x / W) * r.width - 20), bx.width - tip.offsetWidth - 8);
      tip.style.left = `${left}px`; tip.style.top = '8px';
    };
    root.addEventListener('pointermove', show);
    root.addEventListener('pointerdown', show);
    root.addEventListener('pointerleave', () => { hover.replaceChildren(); tip.hidden = true; });
  }

  function drawPie(data) {
    const vals = data.series[0].vals.map((v) => (Number.isFinite(v) && v > 0 ? v : 0));
    const total = vals.reduce((a, b) => a + b, 0);
    const root = svg('svg', { class: 'chart-svg', viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': recipe.title });
    legend.replaceChildren(...data.labels.map((lab, k) => h('span', null, h('i', { style: `background:${COLORS[k % 6]}` }), `${lab}: ${fmtNum(data.series[0].vals[k])}${total ? ` (${Math.round((vals[k] / total) * 100)}%)` : ''}`)));
    if (!total) { box.prepend(root); return; }
    const cx = W / 2, cy = H / 2, r = 120;
    let a0 = -Math.PI / 2;
    vals.forEach((v, k) => {
      if (!v) return;
      const a1 = a0 + (v / total) * Math.PI * 2, big = a1 - a0 > Math.PI ? 1 : 0;
      const p = (a) => `${(cx + r * Math.cos(a)).toFixed(1)},${(cy + r * Math.sin(a)).toFixed(1)}`;
      const path = vals.filter(Boolean).length === 1 ? svg('circle', { cx, cy, r, fill: COLORS[k % 6] })
        : svg('path', { d: `M${cx},${cy}L${p(a0)}A${r},${r} 0 ${big} 1 ${p(a1)}Z`, fill: COLORS[k % 6], stroke: 'var(--panel)', 'stroke-width': 2 });
      path.addEventListener('pointermove', (ev) => {
        tip.replaceChildren(h('div', { text: data.labels[k], style: 'font-weight:600' }), h('div', { text: `${fmtNum(data.series[0].vals[k])} (${Math.round((v / total) * 100)}%)` }));
        tip.hidden = false; const b = box.getBoundingClientRect();
        tip.style.left = `${Math.min(Math.max(8, ev.clientX - b.left + 10), b.width - tip.offsetWidth - 8)}px`; tip.style.top = `${ev.clientY - b.top + 10}px`;
      });
      path.addEventListener('pointerleave', () => { tip.hidden = true; });
      root.append(path);
      a0 = a1;
    });
    box.prepend(root);
  }

  draw();
  if (typeof ResizeObserver !== 'undefined') {
    let lastW = 0, t = 0;
    new ResizeObserver(() => {
      const w = box.clientWidth;
      if (!w || Math.abs(w - lastW) < 24) return;
      lastW = w; clearTimeout(t); t = setTimeout(draw, 80);
    }).observe(box);
  }
  return root;
}

export function renderQuiz(quiz) {
  let right = 0, answered = 0;
  const total = quiz.questions.length;
  const score = h('p', { class: 'muted small', 'aria-live': 'polite' });
  const root = h('div', { class: 'art quiz' }, h('h3', { text: 'Quick quiz' }),
    quiz.questions.map((q, qi) => {
      const why = h('div', { class: 'why', hidden: true, text: q.why || '' });
      const opts = h('div', { class: 'opts' });
      q.options.forEach((o, oi) => opts.append(h('button', { type: 'button', class: 'opt', text: o, onclick: (ev) => {
        if (opts.dataset.done) return;
        opts.dataset.done = '1'; answered++;
        const ok = oi === q.answer; if (ok) right++;
        ev.currentTarget.classList.add(ok ? 'right' : 'wrong');
        if (!ok) opts.children[q.answer].classList.add('right');
        why.hidden = !q.why;
        score.textContent = answered === total ? `You got ${right} of ${total}.` : '';
      } })));
      return h('div', { class: 'q' }, h('b', { text: `${qi + 1}. ${q.q}` }), opts, why);
    }), score);
  return root;
}

export function renderSvg(svgText) {
  const url = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svgText);   // an <img> never runs scripts
  return h('div', { class: 'art svg-art' }, h('img', { src: url, alt: 'Diagram made by the assistant', loading: 'lazy' }));
}

// Flashcards: flip, step and shuffle entirely in the browser. Reviewing a deck costs 0 tokens.
export function renderFlashcards(deck) {
  let order = deck.cards.map((_, i) => i), at = 0, shown = false;
  const known = new Set();
  const face = h('div', { class: 'card-face' });
  const counter = h('span', { class: 'muted small' });
  const score = h('span', { class: 'muted small' });
  const hintBtn = h('button', { type: 'button', class: 'btn small', text: 'Hint' });
  const flip = h('button', { type: 'button', class: 'btn primary', text: 'Show answer' });

  function paint() {
    const c = deck.cards[order[at]];
    face.replaceChildren(h('div', { class: 'card-side' + (shown ? ' back' : ''), text: shown ? c.back : c.front }));
    counter.textContent = `${at + 1} of ${deck.cards.length}`;
    score.textContent = known.size ? `${known.size} marked known` : '';
    flip.textContent = shown ? 'Show question' : 'Show answer';
    hintBtn.hidden = shown || !c.hint;
  }
  const step = (d) => { at = (at + d + deck.cards.length) % deck.cards.length; shown = false; paint(); };
  flip.addEventListener('click', () => { shown = !shown; paint(); });
  hintBtn.addEventListener('click', () => { const c = deck.cards[order[at]]; if (c.hint) face.append(h('div', { class: 'muted small', text: 'Hint: ' + c.hint })); hintBtn.hidden = true; });
  face.addEventListener('click', () => { shown = !shown; paint(); });

  const root = h('div', { class: 'art flashcards' }, h('h3', { text: deck.title }),
    face,
    h('div', { class: 'btn-row' },
      h('button', { type: 'button', class: 'btn small', text: '← Back', onclick: () => step(-1) }),
      flip, hintBtn,
      h('button', { type: 'button', class: 'btn small', text: 'Next →', onclick: () => step(1) })),
    h('div', { class: 'btn-row' },
      h('button', { type: 'button', class: 'btn small', text: '✓ I knew it', onclick: () => { known.add(order[at]); step(1); } }),
      h('button', { type: 'button', class: 'btn small', text: '🔀 Shuffle', onclick: () => { order = order.map((v) => [Math.random(), v]).sort((a, b) => a[0] - b[0]).map((p) => p[1]); at = 0; shown = false; paint(); } }),
      counter, score));
  paint();
  return root;
}

// Sortable table. Clicking a header re-sorts in the browser, so it costs no tokens.
export function renderTable(t) {
  let sortKey = null, asc = true;
  const body = h('tbody');
  const cell = (col, row) => {
    const v = row[col.key];
    if (col.type === 'number') return v == null ? '–' : (col.unit ? `${col.unit}${fmtNum(v)}` : fmtNum(v));
    return String(v ?? '');
  };
  function paint() {
    const rows = [...t.rows];
    if (sortKey) {
      const col = t.columns.find((c) => c.key === sortKey);
      rows.sort((a, b) => {
        const x = a[sortKey], y = b[sortKey];
        if (col.type === 'number') return ((x ?? -Infinity) - (y ?? -Infinity)) * (asc ? 1 : -1);
        return String(x).localeCompare(String(y), undefined, { numeric: true }) * (asc ? 1 : -1);
      });
    }
    body.replaceChildren(...rows.map((r) => h('tr', null, t.columns.map((c) => h('td', { class: c.type === 'number' ? 'num' : '', text: cell(c, r) })))));
  }
  const head = h('tr', null, t.columns.map((c) => {
    const btn = h('button', { type: 'button', class: 'th-sort', 'aria-label': `Sort by ${c.label}` }, c.label, h('span', { class: 'arrow' }));
    btn.addEventListener('click', () => {
      asc = sortKey === c.key ? !asc : true; sortKey = c.key;
      head.querySelectorAll('.arrow').forEach((a) => { a.textContent = ''; });
      btn.querySelector('.arrow').textContent = asc ? ' ▲' : ' ▼';
      paint();
    });
    return h('th', { class: c.type === 'number' ? 'num' : '' }, btn);
  }));
  paint();
  return h('div', { class: 'art table-art' }, h('h3', { text: t.title }),
    h('div', { class: 'tbl-scroll' }, h('table', { class: 'data-table' }, h('thead', null, head), body)),
    h('p', { class: 'muted tiny', text: 'Click a column heading to sort.' }));
}

// A written document or deck. The full text lives in a real file in the workspace; this is the card for it.
export function renderDoc(d, kind = 'doc') {
  const open = () => document.dispatchEvent(new CustomEvent('sh:open-file', { detail: { id: d.file_id, name: d.name, kind } }));
  const meta = kind === 'slides' ? `${d.slides} slides` : `${(d.words || 0).toLocaleString('en')} words`;
  const preview = h('div', { class: 'doc-preview' });
  preview.append(renderMarkdownInto(d.body.slice(0, 1200)));
  const card = h('div', { class: 'art doc-art', role: 'group', 'aria-label': `${kind === 'slides' ? 'Deck' : 'Document'}: ${d.title}` },
    h('div', { class: 'doc-head' },
      h('span', { class: 'doc-ico', 'aria-hidden': 'true', text: kind === 'slides' ? '📊' : '📄' }),
      h('div', { class: 'doc-meta' }, h('b', { text: d.title }), h('span', { class: 'muted tiny', text: `${meta} · saved as ${d.name}` })),
      h('button', { type: 'button', class: 'btn small primary', text: 'Open', onclick: open })),
    preview,
    h('button', { type: 'button', class: 'doc-more', text: 'Open the full document →', onclick: open }));
  return card;
}

// renderMarkdown lives in markdown.js; charts.js stays free of that import by resolving it lazily.
let mdRender = null;
export function setMarkdownRenderer(fn) { mdRender = fn; }
function renderMarkdownInto(text) {
  if (mdRender) return mdRender(text);
  return h('pre', { class: 'muted small', text });
}

// A generated picture. The bytes live in the user's workspace, so the <img> uses a short-lived signed link.
export function renderImage(d) {
  const img = h('img', { alt: d.prompt || 'Generated picture', loading: 'lazy' });
  const box = h('div', { class: 'art image-art' },
    img,
    h('div', { class: 'img-foot' },
      h('span', { class: 'muted tiny', text: `${d.name} · drawn by ${d.model}` }),
      h('button', { type: 'button', class: 'btn small', text: 'Open', onclick: () => document.dispatchEvent(new CustomEvent('sh:open-file', { detail: { id: d.file_id, name: d.name, kind: 'image' } })) })));
  fetch(`/api/files/${encodeURIComponent(d.file_id)}/link`)
    .then((r) => (r.ok ? r.json() : Promise.reject(new Error('link'))))
    .then(({ url }) => { img.src = url; })
    .catch(() => { box.replaceChildren(h('p', { class: 'muted small', text: 'The picture is no longer available.' })); });
  return box;
}
