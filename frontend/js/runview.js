// The live "run card": plan checklist, steps, tools, thinking, cost, Stop. It only draws events and keeps
// no secret state, so a reload (replay from the saved events) shows the same steps.
import { h, $ } from './dom.js';
import { renderMarkdown } from './markdown.js';
import { renderChart, renderQuiz, renderSvg } from './charts.js';

const TOOL_NAMES = { calculator: 'Calculator', chart: 'Chart maker', diagram: 'Diagram', ppt_builder: 'PowerPoint builder', doc_builder: 'Word builder', web_search: 'Web search' };

export class ArtifactStore {
  constructor() { this.data = new Map(); this.nodes = new Map(); }
  add(a) { this.data.set(a.id, a); }
  node(id) {
    if (this.nodes.has(id)) return this.nodes.get(id);       // reuse, so slider positions survive a re-render
    const a = this.data.get(id);
    if (!a) return null;
    let n = null;
    try {
      if (a.kind === 'chart') n = renderChart(a.data);
      else if (a.kind === 'quiz') n = renderQuiz(a.data);
      else if (a.kind === 'svg') n = renderSvg(a.data.svg);
    } catch (e) { console.error('artifact failed', e); n = h('div', { class: 'notice', text: 'This picture could not be drawn.' }); }
    if (n) this.nodes.set(id, n);
    return n;
  }
}

export class RunView {
  constructor({ artifacts, onFile, onAsk, replay = false }) {
    this.artifacts = artifacts; this.onFile = onFile || (() => {}); this.onAsk = onAsk || (() => {}); this.replay = replay;
    this.planEl = null; this.planItems = []; this.stepsEl = h('ul', { class: 'plan' }); this.tools = new Map();
    this.title = h('span', { class: 'run-title', text: 'Starting…' });
    this.cost = h('span', { class: 'run-cost' });
    this.dot = h('span', { class: 'dot', 'aria-hidden': 'true' });
    this.brains = h('div', { class: 'run-brains' });
    this.body = h('div', { class: 'run-body', 'aria-live': 'polite' }, this.brains);
    this.head = h('button', { type: 'button', class: 'run-head', 'aria-expanded': 'true', onclick: () => this.toggle() }, this.dot, this.title, this.cost);
    this.el = h('div', { class: 'run working' }, this.head, this.body);
    this.status = 'working'; this.taskId = null; this.max = 0; this.used = 0;
    this.text = ''; this.hadDelta = false; this.answerEl = null; this.footEl = null; this.messageId = null; this.buttons = [];
    this.files = []; this.sawAsk = false; this.sawError = false; this.stepsShown = false;
  }

  toggle(force) {
    const collapsed = force ?? !this.el.classList.contains('collapsed');
    this.el.classList.toggle('collapsed', collapsed);
    this.head.setAttribute('aria-expanded', String(!collapsed));
  }

  setCost(used, max) {
    this.used = used; this.max = max;
    this.cost.textContent = max ? `Used ${used} credit${used === 1 ? '' : 's'}, at most ${max}` : `Used ${used}`;
  }

  line(cls, text) { const el = h('div', { class: cls, text }); this.body.append(el); return el; }

  handle(ev) {
    const fn = this[`on_${ev.type}`];
    if (fn) fn.call(this, ev);
  }

  on_hello(ev) { this.taskId = ev.task_id; }
  on_run_start(ev) {
    this.taskId = ev.task_id;
    this.title.textContent = ev.mode_name ? `${ev.mode_name}${ev.intent && ev.intent !== 'chat' ? ' · ' + ev.intent.replace('_', ' ') : ''}` : 'Working';
    const roles = Object.entries(ev.brains || {}).map(([r, names]) => `${r}: ${names.join(' + ')}`);
    this.brains.textContent = roles.length ? 'Brains → ' + roles.join(' · ') : '';
    this.setCost(0, ev.max || 0);
  }
  on_plan(ev) {
    this.planEl?.remove();
    this.planItems = ev.steps.map((s, i) => h('li', { class: i < (ev.done || 0) ? 'done' : '' }, h('span', { class: 'tick', text: i < (ev.done || 0) ? '✓' : '○' }), h('span', { text: s.title })));
    this.planEl = h('ol', { class: 'plan', 'aria-label': 'Plan' }, this.planItems);
    this.body.insertBefore(this.planEl, this.brains.nextSibling);
  }
  _planItem(n) { return this.planItems[n - 1]; }
  on_step_start(ev) {
    const item = this._planItem(ev.step);
    if (item) { item.className = 'active'; item.firstChild.textContent = '▶'; return; }
    if (!this.stepsShown) { this.body.append(this.stepsEl); this.stepsShown = true; }
    const li = h('li', { class: 'active', dataset: { step: ev.step } }, h('span', { class: 'tick', text: '▶' }), h('span', { text: ev.title }));
    this.stepsEl.append(li);
  }
  on_step_done(ev) {
    let item = this._planItem(ev.step);
    if (!item) item = this.stepsEl.querySelector(`[data-step="${ev.step}"]`);
    if (!item) return;
    item.className = ev.ok === false ? 'fail' : 'done';
    item.firstChild.textContent = ev.ok === false ? '✗' : '✓';
    if (ev.score) item.append(h('span', { class: 'round-chip', text: `score ${ev.score}/10` }));
    if (ev.detail && !item.querySelector('details')) {
      item.append(h('details', { class: 'fold' }, h('summary', { text: 'Details' }), h('pre', { text: String(ev.detail).slice(0, 800) })));
    }
  }
  on_thinking(ev) {
    this.body.append(h('div', { class: 'think' }, `💭 Thought for ${ev.seconds || 1} s${ev.tokens ? ` (${ev.tokens} thinking tokens)` : ''}`,
      ev.summary ? h('details', { class: 'fold' }, h('summary', { text: 'Summary' }), h('pre', { text: ev.summary })) : null));
  }
  on_tool_start(ev) {
    const key = ev.tool + (ev.step || '');
    const card = h('div', { class: 'card' }, h('span', { class: 'k', text: TOOL_NAMES[ev.tool] || ev.tool }), ' · ', h('span', { class: 'what', text: ev.title || 'working…' }), h('span', { class: 'cost' }));
    this.tools.set(ev.tool, card);
    this.body.append(card);
  }
  on_tool_result(ev) {
    const card = this.tools.get(ev.tool);
    if (!card) return;
    card.querySelector('.what').textContent = (ev.ok ? '✓ ' : '✗ ') + (ev.summary || '');
    card.querySelector('.cost').textContent = ev.cost != null ? `${ev.cost} credits so far` : '';
  }
  on_file_created(ev) { this.files.push(ev.file); this.body.append(h('div', { class: 'card' }, h('span', { class: 'k', text: '📄 File made' }), ' · ', ev.file.name)); if (!this.replay) this.onFile(ev); }
  on_artifact(ev) { this.artifacts.add({ id: ev.id, kind: ev.kind, data: ev.data }); }
  on_round(ev) { this.body.append(h('div', null, h('span', { class: 'round-chip', text: `Round ${ev.round} · score ${ev.score}/10` }), ev.problems?.length ? ' ' + ev.problems.join('; ') : '')); }
  on_skill_used(ev) { this.line('think', `🧩 Used skill: ${ev.name}`); }
  on_notice(ev) { this.line('notice', ev.text); }
  on_cost(ev) { this.setCost(ev.used, ev.max); }
  on_check() {}
  on_settled(ev) { this.charged = ev.charged; }
  on_ask(ev) {
    this.sawAsk = true;
    const buttons = h('div', { class: 'btn-row' });
    const card = h('div', { class: 'ask' }, h('div', { text: ev.text }), buttons);
    if (!this.replay) {
      if (ev.kind === 'confirm') buttons.append(h('button', { class: 'btn primary', type: 'button', text: `Continue (up to ${ev.max} credits)`, onclick: () => { card.remove(); this.onAsk({ kind: 'confirm' }); } }), h('button', { class: 'btn', type: 'button', text: 'Cancel', onclick: () => card.remove() }));
      else if (ev.kind === 'more_credits') {
        if (ev.task_id) buttons.append(h('button', { class: 'btn primary', type: 'button', text: 'Continue with +40 credits', onclick: () => { card.remove(); this.onAsk({ kind: 'continue', task_id: ev.task_id, extra: 40 }); } }));
        else buttons.append(h('button', { class: 'btn primary', type: 'button', text: 'Run again with a higher cap', onclick: () => { card.remove(); this.onAsk({ kind: 'raise' }); } }));
      } else if (ev.kind === 'topup') buttons.append(h('button', { class: 'btn primary', type: 'button', text: 'Add credits', onclick: () => this.onAsk({ kind: 'topup' }) }));
    }
    this.body.append(card);
    this.toggle(false);
  }
  on_error(ev) {
    this.sawError = true;
    const buttons = h('div', { class: 'btn-row' });
    if (ev.retry && !this.replay) buttons.append(h('button', { class: 'btn', type: 'button', text: 'Retry', onclick: () => this.onAsk({ kind: 'retry' }) }));
    this.body.append(h('div', { class: 'err', role: 'alert' }, h('div', { text: ev.text }), buttons.children.length ? buttons : null));
    this.toggle(false);
  }

  // text: either streamed pieces (delta) or the final cleaned version (replace)
  on_text(ev) {
    if (this.replay) return;
    if (ev.replace) {
      const had = this.hadDelta;
      this.text = ev.delta;
      if (!had && this.text.length > 60) return this._typeOut();
    } else { this.text += ev.delta; this.hadDelta = true; }
    this._renderSoon();
  }
  ensureAnswer(parent) {
    if (!this.answerEl) { this.answerEl = h('div', { class: 'answer', 'aria-live': 'polite' }); parent.append(this.answerEl); }
    return this.answerEl;
  }
  _renderSoon() {
    if (this._raf) return;
    this._raf = requestAnimationFrame(() => { this._raf = 0; this.paint(); });
  }
  paint(final = false) {
    if (!this.answerEl) return;
    const md = renderMarkdown(this.text, (id) => this.artifacts.node(id));
    this.answerEl.replaceChildren(md);
    this.answerEl.classList.toggle('cursor', !final && this.status === 'working');
    this.onPaint?.();
  }
  _typeOut() {
    const full = this.text; let n = 0; const step = Math.ceil(full.length / 14);
    const tick = () => { n += step; this.text = full.slice(0, n); this.paint(); if (n < full.length) setTimeout(tick, 30); else { this.text = full; this.paint(); } };
    tick();
  }
  on_answer(ev) { this.messageId = ev.message_id; this.buttons = ev.buttons || []; this.credits = ev.credits; this.notices = ev.notices || []; }
  on_run_done(ev) {
    this.status = ev.status;
    this.el.classList.remove('working');
    if (ev.status === 'done' && !this.sawError && !this.sawAsk) this.toggle(true);
    this.title.textContent = `${this.title.textContent.split(' · ')[0]} · ${({ done: 'finished', stopped: 'stopped', paused: 'paused', error: 'failed', awaiting_confirm: 'waiting for your yes', blocked: 'not started' })[ev.status] || ev.status}`;
    this.setCost(ev.used, ev.max);
    if (!this.replay) { if (this._raf) cancelAnimationFrame(this._raf); this.paint(true); }
  }
}

export function messageFooter({ msg, onNext, onRate }) {
  const foot = h('div', { class: 'msg-foot' });
  if (msg.credits != null) foot.append(h('span', { text: `Used ${msg.credits} credit${msg.credits === 1 ? '' : 's'}` }));
  if (msg.id) {
    const up = h('button', { type: 'button', class: 'rate', 'aria-label': 'Helpful', 'aria-pressed': String(msg.rating === 1), text: '👍' });
    const down = h('button', { type: 'button', class: 'rate', 'aria-label': 'Not helpful', 'aria-pressed': String(msg.rating === -1), text: '👎' });
    const set = (v) => { const next = (v === 1 ? up : down).getAttribute('aria-pressed') === 'true' ? 0 : v; up.setAttribute('aria-pressed', String(next === 1)); down.setAttribute('aria-pressed', String(next === -1)); onRate(msg.id, next); };
    up.onclick = () => set(1); down.onclick = () => set(-1);
    foot.append(up, down);
  }
  return foot;
}

export function nextButtons(labels, onNext) {
  return h('div', { class: 'btn-row', role: 'group', 'aria-label': 'Next steps' }, (labels || []).map((l) => h('button', { type: 'button', class: 'next-btn', text: l, onclick: () => onNext(l) })));
}
