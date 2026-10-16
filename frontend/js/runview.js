// The live "run card": plan checklist, steps, tools, thinking, cost, Stop. It only draws events and keeps
// no secret state, so a reload (replay from the saved events) shows the same steps.
import { h, $ } from './dom.js';
import { renderMarkdown } from './markdown.js';
setMarkdownRenderer((t) => renderMarkdown(t));
import { renderChart, renderQuiz, renderSvg, renderFlashcards, renderTable, renderDoc, renderImage, renderD3Diagram, renderSciencePlot, setMarkdownRenderer } from './charts.js';

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
      else if (a.kind === 'flashcards') n = renderFlashcards(a.data);
      else if (a.kind === 'table') n = renderTable(a.data);
      else if (a.kind === 'doc' || a.kind === 'slides') n = renderDoc(a.data, a.kind);
      else if (a.kind === 'image') n = renderImage(a.data);
      else if (a.kind === 'd3_diagram') n = renderD3Diagram(a.data);
      else if (a.kind === 'science_plot') n = renderSciencePlot(a.data);
    } catch (e) { console.error('artifact failed', e); n = h('div', { class: 'notice', text: 'This picture could not be drawn.' }); }
    if (n) this.nodes.set(id, n);
    return n;
  }
}

export class RunView {
  constructor({ artifacts, onFile, onAsk, onDetails, onPrompt, display = {}, replay = false }) {
    this.display = display; this.onDetails = onDetails || (() => {}); this.timers = new Map(); this.doneCount = 0; this.stepCount = 0; this.calls = [];
    this.artifacts = artifacts; this.onFile = onFile || (() => {}); this.onAsk = onAsk || (() => {}); this.replay = replay;
    this.onPrompt = onPrompt;
    this.planEl = null; this.planItems = []; this.stepsEl = h('ul', { class: 'plan' }); this.tools = new Map();
    this.title = h('span', { class: 'run-title', text: 'Starting…' });
    this.cost = h('span', { class: 'run-cost' });
    this.dot = h('span', { class: 'dot', 'aria-hidden': 'true' });
    this.brains = h('div', { class: 'run-brains' });
    this.body = h('div', { class: 'run-body', 'aria-live': 'polite' }, this.brains);
    this.bar = h('i');
    this.progress = h('div', { class: 'progress indeterminate', role: 'progressbar', 'aria-label': 'Progress', 'aria-valuemin': '0', 'aria-valuemax': '100' }, this.bar);
    this.head = h('button', { type: 'button', class: 'run-head', 'aria-expanded': 'true', onclick: () => this.toggle() }, this.dot, this.title, this.cost);
    this.el = h('div', { class: 'run working' }, this.head, this.progress, this.body);
    if (display.open === 'never') this.toggle(true);
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
    const from = this.used || 0;
    this.used = used; this.max = max;
    const paint = (n) => { this.cost.textContent = max ? `Used ${n} credit${n === 1 ? '' : 's'}, at most ${max}` : `Used ${n}`; };
    if (this.display.anim === 'off' || from === used || this.replay) return paint(used);
    const t0 = performance.now();
    const tick = (t) => { const k = Math.min(1, (t - t0) / 350); paint(Math.round(from + (used - from) * k)); if (k < 1) requestAnimationFrame(tick); };
    requestAnimationFrame(tick);
  }

  setProgress(done, total) {
    const known = total > 0;
    this.progress.classList.toggle('indeterminate', !known && this.status === 'working');
    const pct = this.status === 'done' ? 100 : known ? Math.round((done / total) * 100) : Math.min(90, 12 + done * 14);
    this.bar.style.width = pct + '%';
    this.progress.setAttribute('aria-valuenow', String(pct));
  }

  _startTimer(item, step) {
    const t = h('span', { class: 't', text: '0.0 s' });
    item.append(t);
    const t0 = performance.now();
    const id = setInterval(() => { t.textContent = ((performance.now() - t0) / 1000).toFixed(1) + ' s'; }, 100);
    this.timers.set(step, { id, t, t0 });
  }
  _stopTimer(step) {
    const x = this.timers.get(step);
    if (!x) return;
    clearInterval(x.id);
    x.t.textContent = ((performance.now() - x.t0) / 1000).toFixed(1) + ' s';
    this.timers.delete(step);
  }
  _stopAll() { for (const k of [...this.timers.keys()]) this._stopTimer(k); }

  line(cls, text) { const el = h('div', { class: cls, text }); this.body.append(el); return el; }

  handle(ev) {
    if (ev.seq) this.lastSeq = Math.max(this.lastSeq || 0, ev.seq);
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
    this.planItems = ev.steps.map((s, i) => h('li', { class: i < (ev.done || 0) ? 'done' : '' }, h('span', { class: 'tick', text: i < (ev.done || 0) ? '✓' : '○' }),
      h('div', { class: 'step-info' }, h('span', { text: s.title || s.goal }), s.goal && s.goal !== s.title ? h('div', { class: 'muted tiny', text: `Goal: ${s.goal}` }) : null,
        s.check ? h('div', { class: 'muted tiny', text: `Check: ${s.check}` }) : null)));
    this.planEl = h('ol', { class: 'plan', 'aria-label': 'Plan' }, this.planItems);
    if (this.stepsShown) this.stepsEl.after(this.planEl); else this.body.insertBefore(this.planEl, this.brains.nextSibling);
    this.planTotal = ev.steps.length; this.doneCount = ev.done || 0; this.setProgress(this.doneCount, this.planTotal);
  }
  _planItem(n) { return this.planItems[n - 1]; }
  on_step_start(ev) {
    const item = this._planItem(ev.step);
    if (item) {
      item.className = 'active'; item.firstChild.textContent = ''; this._startTimer(item, ev.step);
      const metadata = [ev.agent, ev.model, ev.effort && `${ev.effort} effort`].filter(Boolean).join(' · ');
      if (metadata) (item.querySelector('.step-info') || item).append(h('div', { class: 'muted tiny', text: metadata }));
      return;
    }
    if (!this.stepsShown) { this.body.append(this.stepsEl); this.stepsShown = true; }
    this.stepCount++;
    const li = h('li', { class: 'active', dataset: { step: ev.step } }, h('span', { class: 'tick', text: '' }), h('span', { class: 'what', text: ev.title }));
    this.stepsEl.append(li);
    this._startTimer(li, ev.step);
    this.setProgress(this.doneCount, this.planTotal || 0);
  }
  on_step_done(ev) {
    let item = this._planItem(ev.step);
    if (!item) item = this.stepsEl.querySelector(`[data-step="${ev.step}"]`);
    if (!item) return;
    this._stopTimer(ev.step);
    item.className = ev.ok === false ? 'fail' : 'done';
    item.firstChild.textContent = ev.ok === false ? '✗' : '✓';
    this.doneCount++; this.setProgress(this.doneCount, this.planTotal || 0);
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
    const key = `${ev.tool}:${ev.agent || ''}:${ev.step || ''}`;
    const card = h('div', { class: 'card' }, h('span', { class: 'k', text: TOOL_NAMES[ev.tool] || ev.tool }), ' · ', h('span', { class: 'what', text: ev.title || 'working…' }), h('span', { class: 'cost' }));
    const pending = this.tools.get(key) || []; pending.push(card); this.tools.set(key, pending);
    this.body.append(card);
  }
  on_tool_result(ev) {
    const prefix = `${ev.tool}:${ev.agent || ''}:`;
    const exactKey = prefix + (ev.step || '');
    const key = this.tools.get(exactKey)?.length ? exactKey : [...this.tools.keys()].find((k) => k.startsWith(prefix) && this.tools.get(k).length);
    const pending = this.tools.get(key) || []; const card = pending.shift();
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
  on_call(ev) {
    this.calls.push(ev);
    const parts = [`${ev.model}`, `${(ev.ms / 1000).toFixed(1)} s`, `${ev.tokens_in}→${ev.tokens_out} tokens`];
    if (ev.thinking) parts.push(`${ev.thinking} thinking`);
    this.body.append(h('div', { class: 'callrow', text: '⚡ ' + parts.join(' · ') }));
  }
  on_memory(ev) {
    const text = ev.action === 'recalled' ? `🧠 Using ${ev.count} saved memor${ev.count === 1 ? 'y' : 'ies'}${ev.recalled_chats ? ' and earlier chats' : ''}` : '🧠 ' + ev.text;
    this.body.append(h('div', { class: 'think', text }));
  }
  on_check() {}
  on_task_card(ev) {
    const card = ev.card || {};
    const details = h('details', { class: 'fold' }, h('summary', { text: 'Task understanding' }),
      card.goal ? h('p', { class: 'small', text: card.goal }) : null,
      Array.isArray(card.constraints) && card.constraints.length ? h('ul', { class: 'small' }, card.constraints.slice(0, 12).map((c) => h('li', { text: String(c) }))) : null,
      Array.isArray(card.missing) && card.missing.length ? h('p', { class: 'small', text: 'Open questions: ' + card.missing.map(String).join('; ') }) : null);
    this.body.append(details);
  }
  on_prompt_enhanced(ev) {
    const details = h('details', { class: 'fold' }, h('summary', { text: 'Enhanced prompt' }), h('pre', { text: ev.text }));
    if (this.onPrompt && !this.replay) details.append(h('button', { class: 'btn small', type: 'button', text: 'Edit as next message', onclick: () => this.onPrompt(ev.text) }));
    this.body.append(details);
  }
  on_sources(ev) {
    this.sourceUrls ||= new Set();
    const chips = h('div', { class: 'btn-row source-chips', 'aria-label': `${ev.agent || 'Research'} sources` });
    for (const source of ev.sources || []) {
      let url;
      try { url = new URL(source.url); } catch { continue; }
      if (!['https:', 'http:'].includes(url.protocol) || this.sourceUrls.has(url.href)) continue;
      this.sourceUrls.add(url.href);
      chips.append(h('a', { class: 'next-btn', href: url.href, target: '_blank', rel: 'noopener noreferrer', text: `[${this.sourceUrls.size}] ${source.title || url.hostname}` }));
    }
    if (chips.children.length) this.body.append(chips);
  }
  on_agent_start(ev) {
    this.agents ||= new Map();
    const id = ev.id || ev.agent_id || ev.agent || ev.role;
    const card = h('div', { class: 'card agent-card', dataset: { agent: id } }, h('b', { text: ev.title || ev.agent || ev.role || 'Agent' }),
      h('div', { class: 'muted tiny', text: [ev.model, ev.effort && `${ev.effort} effort`, ev.goal].filter(Boolean).join(' · ') }),
      h('span', { class: 'agent-status', text: 'Working…' }));
    this.agents.set(id, card); this.body.append(card);
  }
  on_agent_done(ev) {
    const card = this.agents?.get(ev.id || ev.agent_id || ev.agent || ev.role);
    if (!card) return;
    card.querySelector('.agent-status').textContent = [ev.ok === false || ['failed', 'stopped', 'skipped'].includes(ev.status) ? (ev.status || 'Needs attention') : 'Finished', ev.ms != null ? `${(ev.ms / 1000).toFixed(1)} s` : '', ev.credits != null ? `${ev.credits} credits` : ''].filter(Boolean).join(' · ');
    if (ev.summary) card.append(h('details', { class: 'fold' }, h('summary', { text: 'Result' }), h('pre', { text: String(ev.summary).slice(0, 1500) })));
  }
  on_critic_report(ev) {
    const verdict = ev.verdict || 'pass';
    const card = h('div', { class: `card critic-card verdict-${verdict}` },
      h('span', { class: `verdict-chip ${verdict}`, text: `${ev.role || 'critic'}: ${verdict}` }),
      ' · ',
      h('span', { class: 'what', text: ev.finding || 'Checked.' }),
      ev.fix ? h('div', { class: 'muted tiny', text: `Suggested fix: ${ev.fix}` }) : null);
    this.body.append(card);
  }
  on_harness_improved(ev) {
    const fold = h('details', { class: 'fold harness-diff' },
      h('summary', { text: `🔄 Self-improve (${ev.mode}): ${ev.base_harness || 'H0'} → ${ev.new_harness || 'H1'}` }),
      ev.observation ? h('p', { class: 'small', text: ev.observation }) : null,
      ev.lessons?.length ? h('ul', { class: 'small' }, ev.lessons.map((l) => h('li', { text: l }))) : null,
      ev.after?.system_rule ? h('pre', { text: `Before: ${ev.before?.system_rule || 'H0'}\nAfter:  ${ev.after.system_rule}` }) : null);
    if (ev.id && !this.replay) {
      const undoBtn = h('button', { type: 'button', class: 'btn small', text: 'Undo harness edit', onclick: async () => {
        try {
          await fetch('/api/harness/undo', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ record_id: ev.id }) });
          undoBtn.textContent = 'Undone (reverted to H0)';
          undoBtn.disabled = true;
        } catch { /* ignore */ }
      } });
      fold.append(undoBtn);
    }
    this.body.append(fold);
  }
  on_settled(ev) { this.charged = ev.charged; }
  on_ask(ev) {
    this.sawAsk = true;
    const buttons = h('div', { class: 'btn-row' });
    const card = h('div', { class: 'ask' }, h('div', { text: ev.text }), buttons);
    if (!this.replay) {
      if (ev.kind === 'approve_plan') {
        const plan = (ev.plan || ev.steps || []).map((step) => ({ ...step }));
        const editor = h('ol', { class: 'plan-editor', 'aria-label': 'Edit the proposed plan' });
        const inputs = plan.map((step, i) => {
          const goal = h('textarea', { class: 'input', rows: 2, maxLength: 500, value: step.goal || step.title || '', 'aria-label': `Step ${i + 1} goal` });
          const check = h('input', { class: 'input', maxLength: 500, value: step.check || '', 'aria-label': `Step ${i + 1} check`, placeholder: 'How to check this step' });
          editor.append(h('li', null, h('label', { class: 'small' }, `Step ${i + 1} goal`, goal), h('label', { class: 'small' }, 'Check', check)));
          return { goal, check };
        });
        const error = h('p', { class: 'tiny', role: 'alert', hidden: true });
        card.insertBefore(editor, buttons); card.insertBefore(error, buttons);
        const remaining = Math.max(0, this.max - this.used);
        card.insertBefore(h('p', { class: 'muted tiny', text: `Planning used ${this.used} credit${this.used === 1 ? '' : 's'}. Approval can use up to ${remaining} remaining credits.` }), buttons);
        buttons.append(h('button', { class: 'btn primary', type: 'button', text: 'Approve plan and continue', onclick: () => {
          if (!inputs.length || inputs.some(({ goal }) => !goal.value.trim())) { error.textContent = 'Give every step a goal before approving.'; error.hidden = false; return; }
          if (!remaining) { error.textContent = 'Planning used the current budget. Increase the cost cap in Settings and start the task again.'; error.hidden = false; return; }
          const approved = plan.map((step, i) => ({ ...step, goal: inputs[i].goal.value.trim(), title: inputs[i].goal.value.trim(), check: inputs[i].check.value.trim() }));
          if (this.onAsk({ kind: 'approve_plan', task_id: ev.task_id || this.taskId, plan: approved, extra: remaining, max: remaining })) card.remove();
        } }));
      }
      else if (ev.kind === 'confirm') buttons.append(h('button', { class: 'btn primary', type: 'button', text: `Continue (up to ${ev.max} credits)`, onclick: () => { if (this.onAsk({ kind: 'confirm' })) card.remove(); } }), h('button', { class: 'btn', type: 'button', text: 'Cancel', onclick: () => card.remove() }));
      else if (ev.kind === 'more_credits') {
        if (ev.task_id) buttons.append(h('button', { class: 'btn primary', type: 'button', text: 'Continue with +40 credits', onclick: () => { if (this.onAsk({ kind: 'continue', task_id: ev.task_id, extra: 40 })) card.remove(); } }));
        else buttons.append(h('button', { class: 'btn primary', type: 'button', text: 'Run again with a higher cap', onclick: () => { if (this.onAsk({ kind: 'raise' })) card.remove(); } }));
      } else if (ev.kind === 'image_model') {
        for (const o of ev.options || []) {
          buttons.append(h('button', { class: 'btn', type: 'button', text: `${o.name} ($${Number(o.price_out).toFixed(2)}/M out)`,
            onclick: () => { card.remove(); this.onAsk({ kind: 'image_model', model: o.id }); } }));
        }
        if (!(ev.options || []).length) buttons.append(h('span', { class: 'muted small', text: 'Ask an admin to approve an image model.' }));
      } else if (ev.kind === 'topup') buttons.append(h('button', { class: 'btn primary', type: 'button', text: 'Add credits', onclick: () => this.onAsk({ kind: 'topup' }) }));
    }
    this.body.append(card);
    this.toggle(false);
  }
  on_error(ev) {
    this.sawError = true;
    const buttons = h('div', { class: 'btn-row' });
    if (ev.retry && !this.replay) buttons.append(h('button', { class: 'btn', type: 'button', text: 'Retry', onclick: () => this.onAsk({ kind: 'retry', task_id: this.taskId }) }));
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
    this._stopAll();
    this.el.classList.remove('working');
    this.setProgress(this.doneCount, this.planTotal || 0);
    this.progress.classList.remove('indeterminate');
    if (ev.status !== 'done') this.progress.classList.add('stopped');
    if (this.taskId && !this.replay) this.body.append(h('button', { type: 'button', class: 'btn small', text: '🔍 Run details', onclick: () => this.onDetails(this.taskId) }));
    const keep = this.display.open === 'always';
    if (ev.status === 'done' && !this.sawError && !this.sawAsk && !keep) this.toggle(true);
    // Plan section 14: a finished run folds to one line, such as "8 steps, 41 credits".
    const steps = Math.max(this.planTotal || 0, this.stepCount || 0);
    const credits = `${ev.used} credit${ev.used === 1 ? '' : 's'}`;
    if (ev.status === 'done' && !this.sawError && !this.sawAsk) {
      this.title.textContent = steps ? `${steps} step${steps === 1 ? '' : 's'}, ${credits}` : `Done, ${credits}`;
      this.cost.textContent = 'Show steps';
    } else {
      this.title.textContent = `${this.title.textContent.split(' · ')[0]} · ${({ done: 'finished', stopped: 'stopped', paused: 'paused', error: 'failed', awaiting_confirm: 'waiting for your yes', awaiting_plan: 'waiting for plan approval', blocked: 'not started' })[ev.status] || ev.status}`;
      this.setCost(ev.used, ev.max);
    }
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
