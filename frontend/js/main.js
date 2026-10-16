import { $, $$, h, toast, safeStore, timeAgo } from './dom.js';
import { api, streamChat, uploadFile, ApiError } from './api.js';
import { renderMarkdown } from './markdown.js';
import { ArtifactStore, RunView, messageFooter, nextButtons } from './runview.js';
import { FilesPanel } from './files.js';
import { setupAccount } from './account.js';
import { setupLayout } from './layout.js';
import { DEFAULTS, DISPLAY_DEFAULTS, ACCENTS, buildSettings, currentMode, modeName, modelLabel } from './settings.js';
import { sanitizeTeam, teamName } from './team.js';

const store = safeStore();
const S = { ...JSON.parse(JSON.stringify(DEFAULTS)), ...store.get('sh.settings', {}) }; // choices for the next message
const display = { ...DISPLAY_DEFAULTS, ...store.get('sh.display', {}) };
const app = {
  boot: null, convId: null, running: false, controller: null, taskId: null, lastPayload: null, artifacts: new ArtifactStore(),
  stick: true, uploads: [], est: null, estSeq: 0, lastAssistantId: null,
  convSeq: 0, chatListSeq: 0,
};
const files = new FilesPanel();
const thread = $('#thread'), wrap = $('#thread-wrap'), input = $('#composer-text');

const STARTERS = [
  { t: 'Ask anything', d: 'Explain how HTTPS actually keeps a request private.' },
  { t: 'Play with a graph', d: 'Show me how savings grow with a chart and sliders.' },
  { t: 'Make a deck', d: 'Make a 6 slides PPT on the water cycle.' },
  { t: 'Work through a problem', d: 'Plan and compare two ways to save $100 a month for a year.' },
];

// ------------------------------------------------------------------ boot
let account, layout;
async function init() {
  applyTheme(store.get('sh.theme', null)); applyDisplay();
  try {
    app.boot = await api('/api/bootstrap');
  } catch (e) {
    $('#banner').hidden = false; $('#banner').textContent = e.message; return;
  }
  const b = app.boot;
  document.title = b.app; $('#brand-name').textContent = b.app;
  sanitizeSettings();
  account = setupAccount({ app, dialog, hide: hideSheet, refreshWallet });
  paintWallet(b.wallet); paintPlan(); paintAccount();
  if (!b.has_key) banner('No OpenRouter key is set on the server. Add OPENROUTER_API_KEY to the .env file and restart.');
  const sync = b.catalog_sync || {};
  $('#sync-note').textContent = sync.error ? 'Prices: built-in table (live sync unavailable)' : sync.at ? 'Prices: live from OpenRouter' : 'Prices: built-in table';
  layout = setupLayout(); paintChips(); wireStatic(); scheduleEstimate();
  await refreshChats();
  const resume = store.get('sh.run', null);
  const last = store.get('sh.conv', null);
  if (resume?.conv) { await openConversation(resume.conv); if (resume.task) { app.lastPayload = resume.payload; resumeRun(resume.task, resume.conv, resume.payload); } }
  else if (last) await openConversation(last);
  else showWelcome();
  files.refresh(app.convId);
}

function sanitizeSettings() {
  // The server is the boss: drop saved choices the current plan or model list no longer allows.
  const b = app.boot;
  const mode = b.modes.find((m) => m.id === S.mode);
  if (S.mode !== 'auto' && (!mode || !mode.allowed)) Object.assign(S, { mode: 'auto', brains: {} });
  const eff = b.efforts.find((e) => e.id === S.effort);
  if (!eff || !eff.allowed) S.effort = 'auto';
  const ids = new Set(b.models.filter((m) => m.allowed).map((m) => m.id));
  for (const [k, v] of Object.entries(S.brains)) if ([].concat(v).some((x) => x && !ids.has(x))) delete S.brains[k];
  S.tools = S.tools.filter((t) => b.tools.some((x) => x.id === t));
  S.team = sanitizeTeam(S.team, b);
  S.teacher_enabled = S.teacher_enabled !== false;
  if (S.teacher_model && !ids.has(S.teacher_model)) S.teacher_model = null;
}

const teamChoices = () => ({ team: S.team, teacher_enabled: S.teacher_enabled, teacher_model: S.teacher_model });
const persist = () => {
  store.set('sh.settings', S);
  if (app.convId) store.set(`sh.team.chat.${app.boot.user.id}.${app.convId}`, teamChoices());
};
function banner(text) { const el = $('#banner'); el.textContent = text; el.hidden = false; }

// ------------------------------------------------------------------ wallet and plan
function paintWallet(w) {
  $('#wallet-bal').textContent = w.available.toLocaleString('en'); $('#pill-bal').textContent = w.available.toLocaleString('en');
  $('#wallet-held').textContent = w.held ? `${w.held} on hold` : '';
  app.available = w.available;
}
function paintAccount() {
  const u = app.boot.user;
  $('#acct-name').textContent = u.registered ? (u.name || 'Student') : 'Guest';
  $('#acct-email').textContent = u.registered ? u.email : 'Not signed in. Sign up to keep your chats safe.';
  $('#acct-login').hidden = u.registered; $('#acct-logout').hidden = !u.registered;
  $('#admin-link').hidden = !u.is_admin;
}

function paintPlan() {
  const b = app.boot;
  $('#plan-badge').textContent = b.user.plan;
  $('#wallet-dev').hidden = !b.dev_mode || b.unlock_all;
  $('#dev-plan').value = b.user.plan;
}
async function refreshWallet() { try { paintWallet(await api('/api/wallet')); } catch { /* shown next time */ } }

// ------------------------------------------------------------------ chat list
async function refreshChats() {
  const seq = ++app.chatListSeq;
  let list = [];
  try { list = await api('/api/conversations'); } catch { return; }
  if (seq !== app.chatListSeq) return;
  $('#chat-empty').hidden = list.length > 0;
  $('#chat-list').replaceChildren(...list.map((c) => h('li', { class: 'chat-item' + (c.id === app.convId ? ' active' : '') },
    h('button', { type: 'button', class: 'open', title: `${c.title} · ${timeAgo(c.updated_at)}`, text: c.title, 'aria-current': c.id === app.convId ? 'true' : null, onclick: () => { closeSide(); openConversation(c.id); } }),
    h('button', { type: 'button', class: 'del', 'aria-label': `Delete chat ${c.title}`, text: '🗑', onclick: async () => { await api(`/api/conversations/${c.id}`, { method: 'DELETE' }); if (c.id === app.convId) newChat(); refreshChats(); } }))));
}

function newChat() {
  if (app.running) return toast('Wait for the current run, or press Stop.');
  app.convSeq++;
  app.convId = null; thread.replaceChildren(); app.artifacts = new ArtifactStore(); app.lastAssistantId = null;
  $('#chat-title').textContent = 'New chat'; store.set('sh.run', null); store.set('sh.conv', null);
  showWelcome(); files.refresh(null); refreshChats(); input.focus();
}

function showWelcome() {
  thread.replaceChildren(h('div', { class: 'welcome' }, h('h2', { text: 'What can I work on?' }),
    h('p', { class: 'muted', text: 'Direct answers by default. Turn on Teaching mode in Settings if you want everything explained like a tutor.' }),
    h('div', { class: 'starters' }, STARTERS.map((s) => h('button', { type: 'button', class: 'starter', onclick: () => send({ message: s.d }) }, h('b', { text: s.t }), h('span', { class: 'muted small', text: s.d }))))));
}

// ------------------------------------------------------------------ history
async function openConversation(id) {
  if (app.running) return toast('Wait for the current run, or press Stop.');
  const seq = ++app.convSeq;
  let c;
  try { c = await api(`/api/conversations/${id}`); } catch (e) { if (seq !== app.convSeq) return; store.set('sh.run', null); showWelcome(); return toast(e.message); }
  if (seq !== app.convSeq || app.running) return;
  app.convId = id; app.artifacts = new ArtifactStore(); store.set('sh.conv', id);
  const savedTeam = store.get(`sh.team.chat.${app.boot.user.id}.${id}`, null);
  if (savedTeam) { Object.assign(S, savedTeam); sanitizeSettings(); paintChips(); scheduleEstimate(); }
  $('#chat-title').textContent = c.title;
  thread.replaceChildren();
  const lastAssistant = [...c.messages].reverse().find((m) => m.role === 'assistant');
  for (const m of c.messages) thread.append(renderHistory(m, m === lastAssistant));
  app.lastAssistantId = lastAssistant?.id ?? null;
  if (!c.messages.length) showWelcome();
  files.refresh(id); refreshChats(); scrollDown(true);
}

function renderHistory(m, isLast) {
  if (m.role === 'user') return h('div', { class: 'msg user' }, h('div', { class: 'bubble', text: m.content }));
  for (const a of m.artifacts) app.artifacts.add(a);
  const msg = h('div', { class: 'msg assistant' });
  if (m.task_id) {
    const steps = h('button', { type: 'button', class: 'btn small', text: 'Show steps' });
    steps.addEventListener('click', async () => {
      steps.disabled = true;
      try {
        const r = await api(`/api/runs/${m.task_id}/events`);
        const rv = new RunView({ artifacts: app.artifacts, replay: true, display });
        r.events.forEach((e) => rv.handle(e)); rv.toggle(false);
        steps.replaceWith(rv.el);
      } catch (e) { toast(e.message); steps.disabled = false; }
    });
    msg.append(steps);
  }
  msg.append(h('div', { class: 'answer' }, renderMarkdown(m.content, (id) => app.artifacts.node(id))));
  for (const n of m.notices || []) msg.append(h('div', { class: 'notice', text: n }));
  if (m.files.length) msg.append(h('div', { class: 'btn-row' }, m.files.map((f) => h('span', { class: 'file-chip' }, '📄 ', f.name, h('button', { type: 'button', class: 'btn small', text: 'Open', onclick: () => { openFilesPanel(); files.open(f); } })))));
  msg.append(messageFooter({ msg: { id: m.id, rating: m.rating, credits: m.credits }, onRate: rate }));
  if (isLast && m.buttons.length) msg.append(nextButtons(m.buttons, (l) => nextStep(l, m.id)));
  return msg;
}

const rate = (id, v) => api(`/api/messages/${id}/rating`, { method: 'POST', body: { rating: v } }).catch(() => toast('Could not save your rating.'));

function nextStep(label, messageId) {
  const l = label.toLowerCase().trim();
  const opts = { message: label };
  if (/^explain simpler/.test(l)) { opts.intent = 'simplify'; opts.target_message = messageId ?? app.lastAssistantId; }
  else if (/^quiz me/.test(l)) opts.intent = 'quiz';
  else if (/^show a (graph|chart)/.test(l)) opts.intent = 'chart';
  send(opts);
}

// ------------------------------------------------------------------ sending
function buildPayload(message, opts = {}) {
  const p = {
    message, conversation_id: app.convId, mode: S.mode, brains: S.brains, effort: S.effort, rounds: S.rounds, tries: S.tries,
    max_credits: S.cap, tools: S.tools, skills: S.skills, private_route: S.private || null, uploads: app.uploads.map((u) => u.id),
    team: S.team, teacher_enabled: S.teacher_enabled, teacher_model: S.teacher_model,
  };
  if (opts.intent) p.intent = opts.intent;
  if (opts.target_message) p.target_message = opts.target_message;
  return p;
}

async function send(opts = {}) {
  if (app.running) return;
  const text = (opts.message ?? input.value).trim();
  if (!text && !opts.payload) return;
  if (!opts.payload && app.boot && app.available < 1) return toast('You are out of credits.');
  $('.welcome', thread)?.remove();
  const payload = JSON.parse(JSON.stringify(opts.payload || buildPayload(text, opts)));
  payload.request_id ||= requestId();
  app.taskId = null;
  if (!opts.noEcho) {
    thread.append(h('div', { class: 'msg user' }, h('div', { class: 'bubble', text }, app.uploads.length ? h('div', { class: 'muted small', text: '📎 ' + app.uploads.map((u) => u.name).join(', ') }) : null)));
    input.value = ''; autoGrow();
  }
  app.uploads = []; paintAttachments();
  app.lastPayload = payload;
  const msgEl = h('div', { class: 'msg assistant' });
  const run = new RunView({
    artifacts: app.artifacts,
    display, onDetails: showDetails,
    onPrompt: editEnhancedPrompt,
    onFile: () => { files.refresh(app.convId); openFilesPanelSoft(); },
    onAsk: (a) => handleAsk(a, msgEl, payload),
  });
  run.onPaint = () => scrollDown();
  msgEl.append(run.el); thread.append(msgEl); scrollDown(true);
  setRunning(true);
  app.controller = new AbortController();
  try {
    await streamChat(payload, (ev) => {
      if (ev.type === 'hello') {
        if (!app.convId) $('#chat-title').textContent = text.slice(0, 60);
        app.convId = ev.conversation_id; app.taskId = ev.task_id; store.set('sh.run', { conv: ev.conversation_id, task: ev.task_id, payload }); store.set('sh.conv', ev.conversation_id);
        persist();
      }
      run.handle(ev);
      if (ev.type === 'text') run.ensureAnswer(msgEl);
      scrollDown();
    }, app.controller.signal);
  } catch (e) {
    if (app.taskId && (e.status === 0 || !(e instanceof ApiError))) {
      run.handle({ type: 'notice', text: 'Reconnecting to your running task…' });
      await followRun(app.taskId, run, msgEl);
    } else {
      run.handle({ type: 'error', text: e instanceof ApiError ? e.message : 'Something went wrong. Please try again.', retry: !!(e && e.status !== 429 && e.status !== 400) });
      run.handle({ type: 'run_done', status: 'error', used: run.used, max: run.max });
    }
  } finally {
    setRunning(false); rememberPending(run, payload);
    finishMessage(run, msgEl);
    refreshWallet(); refreshChats(); files.refresh(app.convId);
  }
}

function finishMessage(run, msgEl) {
  if (run.answerEl) {
    if (run.notices?.length) run.notices.forEach((n) => msgEl.append(h('div', { class: 'notice', text: n })));
    if (run.files.length) msgEl.append(h('div', { class: 'btn-row' }, run.files.map((f) => h('span', { class: 'file-chip' }, '📄 ', f.name, h('button', { type: 'button', class: 'btn small', text: 'Open', onclick: () => { openFilesPanel(); files.open(f); } })))));
    msgEl.append(messageFooter({ msg: { id: run.messageId, credits: run.credits ?? run.used }, onRate: rate }));
    if (run.buttons.length && run.status !== 'error') msgEl.append(nextButtons(run.buttons, (l) => nextStep(l, run.messageId)));
    if (run.messageId) app.lastAssistantId = run.messageId;
  }
  scrollDown();
}

function handleAsk(a, msgEl, originalPayload) {
  if (a.kind === 'topup') return account.showPlans();
  if (app.running) return toast('Wait for the current run, or press Stop.');
  const old = originalPayload || app.lastPayload;
  if (!old) return toast('Open the chat again to restore this task.');
  if (!['approve_plan', 'continue'].includes(a.kind)) msgEl.remove();
  if (a.kind === 'retry') send({ payload: { ...old, ...(a.task_id ? { request_id: requestId() } : {}) }, noEcho: true });
  else if (a.kind === 'confirm') send({ payload: { ...old, request_id: requestId(), confirm: true }, noEcho: true });
  else if (a.kind === 'approve_plan') send({ payload: { ...old, request_id: requestId(), continue_task: a.task_id, approved_plan: a.plan, extra_credits: a.extra || 0, confirm: true, max_credits: a.max || old.max_credits || null }, noEcho: true });
  else if (a.kind === 'continue') send({ payload: { ...old, request_id: requestId(), message: 'Continue the task.', continue_task: a.task_id, extra_credits: a.extra, confirm: true, max_credits: null }, noEcho: true });
  else if (a.kind === 'raise') {
    const m = currentMode(app.boot, S) || app.boot.modes.find((x) => x.id === 'normal');
    send({ payload: { ...old, request_id: requestId(), max_credits: Math.min(m.max_credits, Math.max(2, (old.max_credits || app.boot.user.auto_spend) * 2)), confirm: true }, noEcho: true });
  }
  return true;
}

function requestId() { return globalThis.crypto?.randomUUID?.() || `req_${Date.now()}_${Math.random().toString(36).slice(2)}`; }
function editEnhancedPrompt(text) { input.value = String(text).slice(0, 12000); autoGrow(); scheduleEstimate(); input.focus(); }

function setRunning(on) {
  app.running = on;
  $('#send-btn').hidden = on; $('#stop-btn').hidden = !on;
  input.disabled = false; $$('#chips .chip').forEach((c) => { c.disabled = on; });
}

async function stopRun() {
  if (!app.taskId) return toast('The task is starting. Press Stop again in a moment.');
  $('#stop-btn').disabled = true;
  try { await api(`/api/runs/${app.taskId}/stop`, { method: 'POST' }); } catch (e) { toast(e.message); }
  setTimeout(() => { $('#stop-btn').disabled = false; }, 1500);
}

// A reload while a run is working: replay what happened, then keep following until it ends.
async function resumeRun(taskId, convId, payload) {
  const msgEl = h('div', { class: 'msg assistant' });
  const run = new RunView({ artifacts: app.artifacts, display, onDetails: showDetails, onPrompt: editEnhancedPrompt, onAsk: (a) => handleAsk(a, msgEl, payload), onFile: () => files.refresh(convId) });
  run.onPaint = () => scrollDown();
  msgEl.append(run.el); thread.append(msgEl);
  setRunning(true); app.taskId = taskId;
  await followRun(taskId, run, msgEl);
  setRunning(false); rememberPending(run, payload);
  if (run.status === 'done') { thread.replaceChildren(); await openConversation(convId); } else finishMessage(run, msgEl);
  refreshWallet();
}

function rememberPending(run, payload) {
  const pending = run.status === 'working' || ['awaiting_plan', 'awaiting_confirm', 'paused'].includes(run.status);
  store.set('sh.run', pending && run.taskId ? { conv: app.convId, task: run.taskId, payload } : null);
}

async function followRun(taskId, run, msgEl) {
  let failures = 0;
  while (run.status === 'working') {
    let r;
    try { r = await api(`/api/runs/${taskId}/events?after=${run.lastSeq || 0}`); failures = 0; }
    catch {
      if (++failures >= 4) {
        run.handle({ type: 'notice', text: 'Your task is saved on the server. Reload this page to reconnect when your connection returns.' });
        return false;
      }
      await new Promise((res) => setTimeout(res, Math.min(4000, failures * 1000))); continue;
    }
    for (const ev of r.events) { run.handle(ev); if (ev.type === 'text') run.ensureAnswer(msgEl); }
    if (run.status === 'working') await new Promise((res) => setTimeout(res, 1000));
  }
  return true;
}

// ------------------------------------------------------------------ scrolling
function nearBottom() { return wrap.scrollHeight - wrap.scrollTop - wrap.clientHeight < 140; }
function scrollDown(force) {
  if (force || app.stick) wrap.scrollTop = wrap.scrollHeight;
  $('#to-bottom').hidden = nearBottom();
}

// ------------------------------------------------------------------ composer: chips, estimate, attachments
function paintChips() {
  const b = app.boot, m = currentMode(b, S);
  const chip = (label, value, focus, cls = '') => h('button', { type: 'button', class: `chip ${cls}`, onclick: () => openSettings(focus) }, `${label}: `, h('b', { text: value }));
  const brain = Object.keys(S.brains).length ? 'Custom' : 'Auto';
  $('#chips').replaceChildren(
    chip('Mode', modeName(b, S), 'mode'),
    chip('Brains', brain, 'brains', 'hide-m'),
    chip('Team', teamName(S.team), 'team'),
    chip('Effort', b.efforts.find((e) => e.id === S.effort)?.label || 'Auto', 'effort', 'hide-m'),
    chip('Tools', String(S.tools.length), 'tools', 'hide-m'),
    h('button', { type: 'button', class: 'chip', onclick: () => openSettings('mode'), 'aria-label': 'All settings', text: '⚙ Settings' }));
}

let estTimer;
function scheduleEstimate() { clearTimeout(estTimer); estTimer = setTimeout(runEstimate, 280); }
async function runEstimate() {
  const seq = ++app.estSeq;
  const el = $('#estimate');
  try {
    const e = await api('/api/estimate', { method: 'POST', body: { ...buildPayload(input.value.slice(0, 600) || 'hello'), conversation_id: null, uploads: [] } });
    if (seq !== app.estSeq) return;
    app.est = e;
    const cap = Math.min(S.cap ?? e.cap, e.max_cap);
    el.replaceChildren(`${e.mode_name}: about `, h('b', { text: `${e.credits} credit${e.credits === 1 ? '' : 's'}` }), `, up to ${cap}`,
      e.needs_confirm ? ' · asks first' : '', cap < e.credits ? ' · cap is low, may stop early' : '', app.available != null && app.available < Math.min(cap, e.credits) ? ' · not enough credits' : '');
    el.title = e.parts.map((p) => `${p.name}: $${p.usd.toFixed(5)}`).join('\n');
    el.classList.toggle('warn', cap < e.credits);
  } catch (err) {
    if (seq !== app.estSeq) return;
    el.textContent = err.message;
  }
}

function paintAttachments() {
  $('#attachments').replaceChildren(...app.uploads.map((u, i) => h('span', { class: 'attach' }, '📎 ' + u.name, h('button', { type: 'button', 'aria-label': `Remove ${u.name}`, text: '✕', onclick: () => { app.uploads.splice(i, 1); paintAttachments(); } }))));
}

function autoGrow() { input.style.height = 'auto'; input.style.height = Math.min(input.scrollHeight, 180) + 'px'; }

// ------------------------------------------------------------------ sheets and dialogs
function showSheet(id) { const s = $(id); s.hidden = false; s.dataset.prevFocus = ''; s._prev = document.activeElement; s.querySelector('button, input, select')?.focus(); }
function hideSheet(id) { const s = $(id); s.hidden = true; s._prev?.focus?.(); }

function openSettings(focus) {
  const body = buildSettings(app.boot, S, { focus, display, onDisplay: applyDisplay, onChange: () => { persist(); paintChips(); scheduleEstimate(); } });
  $('#settings-body').replaceChildren(body);
  $('#settings .sheet-card').classList.add('settings-card');
  showSheet('#settings');
}

function dialog(title, ...content) {
  $('#dialog .sheet-card').classList.remove('wide');
  $('#dialog-title').textContent = title;
  $('#dialog-body').replaceChildren(...content);
  showSheet('#dialog');
}

async function showProfile() {
  const p = await api('/api/profile').catch(() => ({}));
  const f = (k, label, ph) => h('label', { class: 'small' }, label, h('input', { class: 'input', id: `pf-${k}`, value: Array.isArray(p[k]) ? p[k].join(', ') : (p[k] || ''), placeholder: ph }));
  dialog('What I remember about you',
    h('p', { class: 'muted small', text: 'This small card helps me pick examples and the right level. You can edit or delete it any time.' }),
    f('level', 'Level (beginner, medium, advanced)', 'beginner'), f('interests', 'Interests (comma separated)', 'cricket, cooking'), f('language', 'Language', 'English'),
    f('likes', 'How you like answers', 'short answers, step by step maths'), f('weak_topics', 'Topics you find hard', 'fractions'), f('goal', 'Your goal', 'pass the physics exam'),
    h('div', { class: 'btn-row' },
      h('button', { type: 'button', class: 'btn primary', text: 'Save', onclick: async () => {
        const list = (k) => $(`#pf-${k}`).value.split(',').map((x) => x.trim()).filter(Boolean).slice(0, 6);
        await api('/api/profile', { method: 'PUT', body: { level: $('#pf-level').value.trim(), interests: list('interests'), language: $('#pf-language').value.trim(), likes: $('#pf-likes').value.trim(), weak_topics: list('weak_topics'), goal: $('#pf-goal').value.trim() } });
        hideSheet('#dialog'); toast('Saved.');
      } }),
      h('button', { type: 'button', class: 'btn danger', text: 'Forget everything', onclick: async () => { await api('/api/profile', { method: 'DELETE' }); hideSheet('#dialog'); toast('Memory deleted.'); } })));
}

async function showCredits() {
  const w = await api('/api/wallet');
  const rows = w.ledger.slice(0, 12).map((r) => h('tr', null, h('td', { text: (r.delta > 0 ? '+' : '') + r.delta }), h('td', { text: r.reason }), h('td', { text: timeAgo(r.created_at) })));
  dialog('Credits',
    h('p', null, h('b', { text: String(w.available) }), ` credits available${w.held ? ` (${w.held} on hold for running jobs)` : ''}.`),
    app.boot.dev_mode ? h('button', { type: 'button', class: 'btn primary', text: 'Add 500 test credits', onclick: async () => { await api('/api/dev/topup', { method: 'POST', body: { credits: 500 } }); refreshWallet(); hideSheet('#dialog'); toast('Added 500 credits.'); } })
      : h('p', { class: 'muted small', text: 'Payments are not connected yet. Plans refresh credits every month.' }),
    h('div', { class: 'md' }, h('table', null, h('thead', null, h('tr', null, h('th', { text: 'Change' }), h('th', { text: 'Reason' }), h('th', { text: 'When' }))), h('tbody', null, rows))));
}

// ------------------------------------------------------------------ panels
function closeSide() { delete $('#app').dataset.side; $('#scrim').hidden = true; }
function openFilesPanel() { layout.openFiles(); }
function openFilesPanelSoft() { if (!matchMedia('(max-width: 1100px)').matches) openFilesPanel(); }
function closeFilesPanel() { layout.closeFiles(); }

function applyDisplay() {
  const r = document.documentElement;
  r.dataset.anim = display.anim; r.dataset.size = display.size; r.dataset.density = display.density;
  r.classList.toggle('no-timing', !display.timing); r.classList.toggle('no-thinking', !display.thinking);
  const c = ACCENTS[display.accent] || ACCENTS.teal;
  r.style.setProperty('--accent-user', c);
  store.set('sh.display', display);
}

async function showDetails(taskId) {
  let rows = [];
  try { rows = await api(`/api/runs/${taskId}/usage`); } catch (e) { return toast(e.message); }
  const sum = (k) => rows.reduce((a, r) => a + (r[k] || 0), 0);
  const body = rows.length ? h('div', { class: 'md' }, h('table', null,
    h('thead', null, h('tr', null, ['#', 'Role', 'Model', 'Time', 'In', 'Out', 'Thinking', 'Cost'].map((t) => h('th', { text: t })))),
    h('tbody', null, rows.map((r) => h('tr', null, h('td', { text: r.step_no }), h('td', { text: r.role }), h('td', { text: r.model }), h('td', { text: ((r.latency_ms || 0) / 1000).toFixed(1) + ' s' }),
      h('td', { text: r.input_tokens + r.cached_tokens }), h('td', { text: r.output_tokens }), h('td', { text: r.reasoning_tokens }), h('td', { text: '$' + r.cost_usd.toFixed(5) })))),
    h('tfoot', null, h('tr', null, h('th', { text: 'Total', colspan: 3 }), h('th', { text: (sum('latency_ms') / 1000).toFixed(1) + ' s' }), h('th', { text: sum('input_tokens') + sum('cached_tokens') }), h('th', { text: sum('output_tokens') }), h('th', { text: sum('reasoning_tokens') }), h('th', { text: '$' + sum('cost_usd').toFixed(5) })))))
    : h('p', { class: 'muted', text: 'No AI calls were recorded for this run.' });
  dialog('Run details', h('p', { class: 'muted small', text: `${rows.length} AI call(s). Credits charged: ${sum('credits_charged')}.` }), body);
  $('#dialog .sheet-card').classList.add('wide');
}

function applyTheme(t) { if (t) document.documentElement.dataset.theme = t; }

// ------------------------------------------------------------------ wiring
function wireStatic() {
  $('#composer').addEventListener('submit', (e) => { e.preventDefault(); send(); });
  input.addEventListener('input', () => { autoGrow(); scheduleEstimate(); });
  input.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(); } });
  $('#stop-btn').addEventListener('click', stopRun);
  $('#new-chat').addEventListener('click', () => { closeSide(); newChat(); });
  $('#open-side').addEventListener('click', () => { $('#app').dataset.side = 'open'; $('#scrim').hidden = false; });
  $('#close-side').addEventListener('click', closeSide);
  $('#scrim').addEventListener('click', () => { closeSide(); if (matchMedia('(max-width: 1100px)').matches) closeFilesPanel(); });
  $('#open-files-btn').addEventListener('click', () => { closeSide(); openFilesPanel(); files.refresh(null); });
  $('#settings-close').addEventListener('click', () => hideSheet('#settings'));
  $('#dialog-close').addEventListener('click', () => hideSheet('#dialog'));
  for (const id of ['#settings', '#dialog']) $(id).addEventListener('click', (e) => { if (e.target === $(id)) hideSheet(id); });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { hideSheet('#settings'); hideSheet('#dialog'); closeSide(); }
    if (e.key !== 'Tab') return;
    const sheet = $('#dialog:not([hidden])') || $('#settings:not([hidden])');
    if (!sheet) return;
    const controls = $$('button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), summary, a[href]', sheet).filter((el) => el.getClientRects().length);
    const first = controls[0], last = controls.at(-1);
    if (!first) return;
    if (!sheet.contains(document.activeElement) || (!e.shiftKey && document.activeElement === last)) { e.preventDefault(); first.focus(); }
    else if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
  });
  $('#open-profile').addEventListener('click', () => { closeSide(); account.showMemory(); });
  $('#open-activity').addEventListener('click', () => { closeSide(); account.showActivity(); });
  $('#acct-login').addEventListener('click', () => { closeSide(); account.showAuth('login'); });
  $('#acct-logout').addEventListener('click', () => account.logout());
  $('#buy-credits').addEventListener('click', () => { closeSide(); account.showPlans(); });
  $('#credit-pill').addEventListener('click', () => account.showPlans());
  $('#wallet').addEventListener('dblclick', showCredits);
  $('#theme-toggle').addEventListener('click', () => {
    const dark = (document.documentElement.dataset.theme || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')) === 'dark';
    const next = dark ? 'light' : 'dark'; applyTheme(next); store.set('sh.theme', next);
  });
  $('#dev-plan').addEventListener('change', async (e) => {
    await api('/api/dev/plan', { method: 'POST', body: { plan: e.target.value } });
    app.boot = await api('/api/bootstrap'); sanitizeSettings(); persist(); paintPlan(); paintWallet(app.boot.wallet); paintChips(); scheduleEstimate(); toast(`Now testing as the ${e.target.value} plan.`);
  });
  $('#dev-topup').addEventListener('click', async () => { await api('/api/dev/topup', { method: 'POST', body: { credits: 500 } }); refreshWallet(); toast('Added 500 credits.'); });
  $('#delete-files').addEventListener('click', () => dialog('Delete all my files?', h('p', { text: 'This removes every file the assistant made for you, and your uploads. It cannot be undone.' }),
    h('div', { class: 'btn-row' }, h('button', { type: 'button', class: 'btn danger', text: 'Delete everything', onclick: async () => { await api('/api/workspace', { method: 'DELETE' }); hideSheet('#dialog'); files.refresh(app.convId); $('#preview').hidden = true; toast('Files deleted.'); } }),
      h('button', { type: 'button', class: 'btn', text: 'Cancel', onclick: () => hideSheet('#dialog') }))));
  $('#file-input').addEventListener('change', async (e) => {
    const f = e.target.files[0]; e.target.value = '';
    if (!f) return;
    try { const u = await uploadFile(f); app.uploads.push(u); paintAttachments(); toast(`Added ${u.name}`); } catch (err) { toast(err.message); }
  });
  wrap.addEventListener('scroll', () => { app.stick = nearBottom(); $('#to-bottom').hidden = app.stick; }, { passive: true });
  $('#to-bottom').addEventListener('click', () => { app.stick = true; scrollDown(true); });
}

init();
