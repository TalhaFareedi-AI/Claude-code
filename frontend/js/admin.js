// Admin console: sign in, then see every user, what they asked, what credits they used, set their limits,
// and edit the plans (price, credits, benefits, what each plan unlocks).
import { h, $, toast, timeAgo, fmtNum } from './dom.js';
import { api, ApiError } from './api.js';
import { renderChart } from './charts.js';

const root = $('#root');
const usd = (n) => '$' + Number(n || 0).toFixed(Number(n) < 1 && Number(n) > 0 ? 4 : 2);
const when = (ts) => (ts ? new Date(ts * 1000).toLocaleString() : '–');
const num = (n) => Number(n || 0).toLocaleString();
let state = { tab: 'overview', plans: [], planIds: [] };

function modal(title, ...content) { $('#modal-title').textContent = title; $('#modal-body').replaceChildren(...content); $('#modal').hidden = false; }
const closeModal = () => { $('#modal').hidden = true; };
$('#modal-close').addEventListener('click', closeModal);
$('#modal').addEventListener('click', (e) => { if (e.target === $('#modal')) closeModal(); });
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeModal(); });

const fail = (e) => toast(e instanceof ApiError ? e.message : 'Something went wrong.', 4500);

function table(cols, rows, onRow) {
  return h('div', { class: 'tbl-wrap' }, h('table', { class: 'tbl' },
    h('thead', null, h('tr', null, cols.map((c) => h('th', { text: c.label })))),
    h('tbody', null, rows.length ? rows.map((r) => {
      const tr = h('tr', { class: onRow ? 'click' : '', tabindex: onRow ? 0 : null }, cols.map((c) => h('td', { class: c.wrap ? 'wrap' : '' }, c.render ? c.render(r) : r[c.key] ?? '')));
      if (onRow) { tr.addEventListener('click', () => onRow(r)); tr.addEventListener('keydown', (e) => { if (e.key === 'Enter') onRow(r); }); }
      return tr;
    }) : [h('tr', null, h('td', { colspan: cols.length, class: 'muted', text: 'Nothing here yet.' }))])));
}
const badge = (text, kind = '') => h('span', { class: `badge ${kind}`, text });

// ------------------------------------------------------------------ login gate
async function start() {
  let b;
  try { b = await api('/api/bootstrap'); } catch (e) { root.replaceChildren(h('p', { class: 'form-error', text: e.message })); return; }
  if (!b.user.is_admin) return loginView(b.user.registered);
  state.me = b.user;
  shell();
}

function loginView(signedIn) {
  const err = h('p', { class: 'form-error', hidden: true, role: 'alert' });
  const email = h('input', { class: 'input', type: 'email', placeholder: 'admin email', autocomplete: 'username' });
  const pass = h('input', { class: 'input', type: 'password', placeholder: 'password', autocomplete: 'current-password' });
  const form = h('form', { class: 'login-card' }, h('h1', { text: '🛡️ Admin console' }),
    signedIn ? h('p', { class: 'form-error', text: 'You are signed in, but this account is not an admin.' }) : h('p', { class: 'muted small', text: 'Sign in with the admin email and password.' }),
    email, pass, err, h('button', { class: 'btn primary', type: 'submit', text: 'Sign in' }), h('a', { href: '/', class: 'muted small', text: '← Back to the app' }));
  form.addEventListener('submit', async (e) => {
    e.preventDefault(); err.hidden = true;
    try { await api('/api/auth/login', { method: 'POST', body: { email: email.value, password: pass.value } }); location.reload(); }
    catch (ex) { err.textContent = ex.message; err.hidden = false; }
  });
  root.replaceChildren(form);
}

// ------------------------------------------------------------------ shell and tabs
const TABS = [['overview', 'Overview'], ['users', 'Users'], ['queries', 'Queries'], ['plans', 'Plans'], ['purchases', 'Purchases'], ['activity', 'Activity'], ['models', 'Models']];
function shell() {
  const content = h('div', { id: 'content' });
  const tabs = h('div', { class: 'tabs', role: 'tablist' }, TABS.map(([id, label]) => h('button', { type: 'button', role: 'tab', 'aria-selected': String(state.tab === id), text: label, dataset: { id },
    onclick: () => { state.tab = id; $$tabs(); show(); } })));
  const $$tabs = () => tabs.querySelectorAll('button').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.id === state.tab)));
  root.replaceChildren(h('div', { class: 'adm' },
    h('div', { class: 'adm-top' }, h('h1', { text: '🛡️ Admin console' }), h('span', { class: 'muted small', text: state.me.email }),
      h('a', { class: 'btn small', href: '/', text: 'Open the app' }),
      h('button', { class: 'btn small', type: 'button', text: 'Log out', onclick: async () => { await api('/api/auth/logout', { method: 'POST' }); location.href = '/admin.html'; } })),
    tabs, content));
  show();
}
async function show() {
  const c = $('#content');
  c.replaceChildren(h('p', { class: 'muted', text: 'Loading…' }));
  try { c.replaceChildren(await VIEWS[state.tab]()); } catch (e) { c.replaceChildren(h('p', { class: 'form-error', text: e.message })); }
}

// ------------------------------------------------------------------ overview
async function overview() {
  const o = await api('/api/admin/overview');
  const k = (label, v) => h('div', { class: 'kpi' }, h('b', { text: String(v) }), h('span', { text: label }));
  const chart = o.daily.length ? renderChart({ chart: 'bar', title: 'Runs per day (last 14 days)', inputs: [], data: o.daily.map((d) => ({ label: d.day.slice(5), formula: String(d.runs) })) }) : null;
  return h('div', { class: 'grid' },
    h('div', { class: 'kpis' }, k('Users', o.users), k('With an account', o.registered), k('Active today', o.active_today), k('Active 7 days', o.active_7d), k('Questions today', o.queries_today),
      k('Runs today', o.runs_today), k('Credits used today', num(o.credits_used_today)), k('Credits used total', num(o.credits_used_total)), k('AI cost today', usd(o.ai_cost_usd_today)),
      k('AI cost total', usd(o.ai_cost_usd_total)), k('Revenue 30 days', usd(o.revenue_usd_30d)), k('Revenue total', usd(o.revenue_usd_total)), k('Pending orders', o.pending_purchases),
      k('Blocked users', o.blocked_users), k('Ledger mismatches', o.ledger_mismatches)),
    h('div', { class: 'grid2', style: 'margin-top:16px' },
      h('div', { class: 'panel' }, h('h3', { text: 'Top users by credits used' }), table(userCols(true), o.top_users, openUser)),
      h('div', { class: 'panel' }, h('h3', { text: 'Users by plan' }), table([{ label: 'Plan', key: 'plan' }, { label: 'Users', key: 'users' }], o.by_plan), chart)));
}

// ------------------------------------------------------------------ users
const userCols = (compact) => [
  { label: 'User', render: (u) => h('span', null, h('b', { text: u.name || 'Student' }), ' ', h('span', { class: 'muted tiny', text: u.email || '(guest) ' + u.id })) },
  { label: 'Plan', render: (u) => badge(u.plan, u.plan === 'free' ? '' : 'ok') },
  { label: 'Credits left', render: (u) => num(u.balance) }, { label: 'Used', render: (u) => num(u.credits_used) },
  ...(compact ? [] : [{ label: 'Today / limit', render: (u) => `${num(u.spent_today)} / ${u.limits.daily ?? '∞'}` }, { label: 'Monthly limit', render: (u) => u.limits.monthly ?? '–' },
    { label: 'Chats', key: 'chats' }, { label: 'Queries', key: 'queries' }, { label: 'Runs', key: 'runs' }, { label: 'Last seen', render: (u) => (u.last_seen_at ? timeAgo(u.last_seen_at) : '–') },
    { label: 'Status', render: (u) => badge(u.status === 'blocked' ? 'blocked' : u.role === 'admin' ? 'admin' : 'active', u.status === 'blocked' ? 'bad' : u.role === 'admin' ? 'warn' : 'ok') }]),
];
async function users() {
  const f = { q: '', sort: 'recent', plan: '', status: '' };
  const out = h('div'), box = h('div');
  const run = async () => {
    const qs = new URLSearchParams({ ...f, size: 100 });
    const r = await api('/api/admin/users?' + qs);
    box.replaceChildren(h('p', { class: 'hint', text: `${r.total} user(s). Click a row for the full blueprint, limits and controls.` }), table(userCols(false), r.users, openUser));
  };
  let t;
  const q = h('input', { class: 'input', type: 'search', placeholder: 'Search name, email or id', 'aria-label': 'Search users' });
  q.addEventListener('input', () => { f.q = q.value; clearTimeout(t); t = setTimeout(run, 220); });
  const sel = (key, opts, label) => { const s = h('select', { class: 'select', 'aria-label': label }, opts.map(([v, tx]) => h('option', { value: v, text: tx }))); s.addEventListener('change', () => { f[key] = s.value; run(); }); return s; };
  const plans = await api('/api/admin/plans'); state.planIds = plans.plans.filter((p) => p.kind === 'subscription').map((p) => p.id);
  state.planCaps = Object.fromEntries(plans.plans.map((p) => [p.id, p.rules?.daily_credit_cap ?? '–']));
  out.append(h('div', { class: 'toolbar' }, q, sel('sort', [['recent', 'Recently active'], ['credits', 'Most credits used'], ['runs', 'Most runs'], ['balance', 'Most credits left'], ['newest', 'Newest'], ['name', 'Name']], 'Sort'),
    sel('plan', [['', 'All plans'], ...state.planIds.map((p) => [p, p])], 'Plan'), sel('status', [['', 'Any status'], ['active', 'Active'], ['blocked', 'Blocked']], 'Status')), box);
  await run();
  return out;
}

async function openUser(u) {
  let b;
  try { b = await api(`/api/admin/users/${encodeURIComponent(u.id)}`); } catch (e) { return fail(e); }
  const x = b.user, lim = b.limits;
  const field = (label, el) => h('label', null, label, el);
  const name = h('input', { class: 'input', value: x.name || '' });
  const plan = h('select', { class: 'select' }, state.planIds.map((p) => h('option', { value: p, text: p, selected: p === x.plan || null })));
  const status = h('select', { class: 'select' }, ['active', 'blocked'].map((p) => h('option', { value: p, text: p, selected: p === x.status || null })));
  const role = h('select', { class: 'select' }, ['user', 'admin'].map((p) => h('option', { value: p, text: p, selected: p === x.role || null })));
  const daily = h('input', { class: 'input', type: 'number', min: 0, placeholder: 'plan default', value: x.daily_limit ?? '' });
  const monthly = h('input', { class: 'input', type: 'number', min: 0, placeholder: 'no limit', value: x.monthly_limit ?? '' });
  const auto = h('input', { class: 'input', type: 'number', min: 1, value: x.auto_spend ?? 20 });
  const extend = h('input', { class: 'input', type: 'number', min: 1, placeholder: 'days to add' });
  const memory = h('input', { type: 'checkbox', checked: x.memory_enabled ? true : null });
  const note = h('textarea', { class: 'input', maxlength: 1000, placeholder: 'Private admin note about this user' });
  note.value = x.note || '';
  const save = h('button', { class: 'btn primary', type: 'button', text: 'Save changes', onclick: async () => {
    const body = { name: name.value, plan: plan.value, status: status.value, role: role.value, memory_enabled: memory.checked, auto_spend: +auto.value || 20, note: note.value };
    if (daily.value === '') body.clear_daily_limit = true; else body.daily_limit = +daily.value;
    if (monthly.value === '') body.clear_monthly_limit = true; else body.monthly_limit = +monthly.value;
    if (extend.value) body.extend_plan_days = +extend.value;
    try { await api(`/api/admin/users/${encodeURIComponent(x.id)}`, { method: 'PUT', body }); toast('Saved.'); openUser(u); } catch (e) { fail(e); }
  } });
  const delta = h('input', { class: 'input', type: 'number', placeholder: '+500 or -100' });
  const reason = h('input', { class: 'input', placeholder: 'Reason (shown in their history)' });
  const adjust = h('button', { class: 'btn', type: 'button', text: 'Add or remove credits', onclick: async () => {
    try { const r = await api(`/api/admin/users/${encodeURIComponent(x.id)}/credits`, { method: 'POST', body: { delta: +delta.value, reason: reason.value } }); toast(`Balance is now ${r.balance}.`); openUser(u); } catch (e) { fail(e); }
  } });
  const t = b.totals;
  const kpi = (l, v) => h('div', { class: 'kpi' }, h('b', { text: String(v) }), h('span', { text: l }));
  modal(`${x.name || 'Student'} · ${x.email || x.id}`,
    h('div', { class: 'kpis' }, kpi('Credits left', num(b.wallet.available)), kpi('Used today', num(b.wallet.spent_today)), kpi('Used 30 days', num(b.wallet.spent_month)), kpi('Credits used', num(t.credits_used)),
      kpi('Chats', t.conversations), kpi('Questions', t.messages), kpi('Runs', t.runs), kpi('Files', t.files), kpi('AI cost', usd(t.ai_cost_usd)), kpi('Paid by user', usd(t.purchases_usd)),
      kpi('👍 / 👎', `${t.thumbs_up} / ${t.thumbs_down}`), kpi('Memories', t.memories)),
    h('div', { class: 'panel' }, h('h3', { text: 'Account controls' }),
      h('div', { class: 'form-grid' }, field('Name', name), field('Plan', plan), field('Extend plan (days)', extend), field('Status', status), field('Role', role),
        field(`Daily credit limit (plan default: ${plansDefault(plan.value)})`, daily), field('Monthly credit limit', monthly), field('Auto-spend per task', auto),
        h('label', { class: 'check' }, memory, 'Memory enabled')), field('Admin note', note), save,
      h('p', { class: 'hint', text: `Plan renews: ${when(x.plan_renews_at)} · Joined: ${when(x.created_at)} · Last seen: ${when(x.last_seen_at)} · id ${x.id}` })),
    h('div', { class: 'panel' }, h('h3', { text: 'Credits' }), h('div', { class: 'form-grid' }, field('Change', delta), field('Reason', reason)), adjust),
    h('div', { class: 'grid2' },
      h('div', { class: 'panel' }, h('h3', { text: 'Chats (click to read)' }), table([{ label: 'Title', key: 'title', wrap: true }, { label: 'Messages', key: 'messages' }, { label: 'Updated', render: (c) => timeAgo(c.updated_at) }], b.conversations, (c) => openChat(c.id))),
      h('div', { class: 'panel' }, h('h3', { text: 'Usage by mode' }), table([{ label: 'Mode', key: 'mode' }, { label: 'Runs', key: 'runs' }, { label: 'Credits', render: (m) => num(m.credits) }, { label: 'AI cost', render: (m) => usd(m.usd) }], b.by_mode),
        h('h3', { text: 'Usage by model' }), table([{ label: 'Model', key: 'model' }, { label: 'Calls', key: 'calls' }, { label: 'Tokens in/out', render: (m) => `${num(m.tokens_in)} / ${num(m.tokens_out)}` }, { label: 'Cost', render: (m) => usd(m.usd) }], b.by_model))),
    h('div', { class: 'grid2' },
      h('div', { class: 'panel' }, h('h3', { text: 'What the AI remembers about them' }), table([{ label: 'Kind', key: 'kind' }, { label: 'Note', key: 'content', wrap: true }, { label: 'By', key: 'source' }], b.memories),
        b.profile && Object.keys(b.profile).length ? h('p', { class: 'hint', text: 'Profile: ' + JSON.stringify(b.profile) }) : null),
      h('div', { class: 'panel' }, h('h3', { text: 'Purchases' }), table([{ label: 'When', render: (p) => when(p.created_at) }, { label: 'What', key: 'plan_id' }, { label: 'Paid', render: (p) => usd(p.amount_usd) }, { label: 'Status', key: 'status' }], b.purchases),
        h('h3', { text: 'Credit history' }), table([{ label: 'Change', render: (l) => (l.delta > 0 ? '+' : '') + l.delta }, { label: 'Reason', key: 'reason' }, { label: 'When', render: (l) => timeAgo(l.created_at) }], b.ledger))),
    h('div', { class: 'panel' }, h('h3', { text: 'Full activity timeline' }),
      table([{ label: 'When', render: (e) => when(e.created_at) }, { label: 'What', key: 'kind' }, { label: 'By', render: (e) => (e.actor === x.id ? 'user' : e.actor) }, { label: 'Detail', wrap: true, render: (e) => JSON.stringify(e.detail).slice(0, 200) }], b.timeline)),
    h('div', { class: 'btn-row' }, h('button', { class: 'btn danger', type: 'button', text: 'Delete this user and all their data', onclick: async () => {
      const id = prompt(`This permanently deletes ${x.id} and everything they own. Type the user id to confirm.`);
      if (id !== x.id) return;
      try { await api(`/api/admin/users/${encodeURIComponent(x.id)}`, { method: 'DELETE', body: { confirm: id } }); toast('User deleted.'); closeModal(); show(); } catch (e) { fail(e); }
    } })));
}
const plansDefault = (id) => state.planCaps?.[id] ?? '–';

async function openChat(cid) {
  let c;
  try { c = await api(`/api/admin/conversations/${encodeURIComponent(cid)}`); } catch (e) { return fail(e); }
  modal(c.title || 'Chat', h('p', { class: 'hint', text: 'Opening a chat is recorded in the user\'s activity history.' }),
    c.summary ? h('p', { class: 'hint', text: 'Summary: ' + c.summary }) : null, c.notes ? h('p', { class: 'hint', text: 'Session notes: ' + c.notes }) : null,
    h('div', { class: 'convo' }, c.messages.map((m) => h('div', { class: 'm ' + m.role }, h('span', { class: 'muted tiny', text: `${m.role} · ${when(m.created_at)}${m.mode ? ' · ' + m.mode : ''}${m.credits_used != null && m.role === 'user' ? ' · ' + m.credits_used + ' credits' : ''}` }), h('div', { text: m.content })))));
}

// ------------------------------------------------------------------ queries
async function queries() {
  const f = { q: '', user_id: '', page: 0 };
  const box = h('div');
  const run = async () => {
    const r = await api('/api/admin/queries?' + new URLSearchParams({ ...f, size: 50 }));
    box.replaceChildren(h('p', { class: 'hint', text: `${num(r.total)} question(s) in total. Click one to read the whole chat.` }),
      table([{ label: 'When', render: (x) => timeAgo(x.created_at) }, { label: 'User', render: (x) => x.email || x.name || x.user_id }, { label: 'Question', key: 'content', wrap: true, render: (x) => x.content.slice(0, 220) },
        { label: 'Mode', key: 'mode' }, { label: 'Status', key: 'status' }, { label: 'Credits', render: (x) => x.credits_used ?? 0 }], r.queries, (x) => openChat(x.conversation_id)),
      h('div', { class: 'toolbar' }, h('button', { class: 'btn small', type: 'button', text: '← Newer', disabled: f.page === 0 || null, onclick: () => { f.page--; run(); } }),
        h('span', { class: 'muted small', text: `Page ${f.page + 1}` }), h('button', { class: 'btn small', type: 'button', text: 'Older →', disabled: (f.page + 1) * 50 >= r.total || null, onclick: () => { f.page++; run(); } })));
  };
  let t;
  const q = h('input', { class: 'input', type: 'search', placeholder: 'Search what users asked', 'aria-label': 'Search queries' });
  q.addEventListener('input', () => { f.q = q.value; f.page = 0; clearTimeout(t); t = setTimeout(run, 250); });
  const uid = h('input', { class: 'input', placeholder: 'Only this user id (optional)' });
  uid.addEventListener('input', () => { f.user_id = uid.value.trim(); f.page = 0; clearTimeout(t); t = setTimeout(run, 250); });
  await run();
  return h('div', null, h('div', { class: 'toolbar' }, q, uid), box);
}

// ------------------------------------------------------------------ plans: price, credits, benefits, rules
const RULE_NUM = [['daily_credit_cap', 'Daily credit cap'], ['storage_mb', 'Storage (MB)'], ['retention_days', 'Keep files (days)'], ['max_rounds', 'Think Again rounds'], ['max_tries', 'Overthink tries'], ['charts_per_day', 'Charts per day']];
async function plans() {
  const r = await api('/api/admin/plans');
  state.planCaps = Object.fromEntries(r.plans.map((p) => [p.id, p.rules?.daily_credit_cap ?? '–']));
  const out = h('div', { class: 'grid' }, h('p', { class: 'hint', text: 'Change anything here and it changes for every user at once: the store, the credits and what each plan unlocks. Hidden plans keep their current users.' }));
  const editor = (p, isNew) => {
    const f = {
      id: h('input', { class: 'input', value: p.id || '', placeholder: 'e.g. team', disabled: isNew ? null : true }), name: h('input', { class: 'input', value: p.name || '' }),
      kind: h('select', { class: 'select' }, [['subscription', 'Monthly plan'], ['topup', 'Credit pack']].map(([v, t]) => h('option', { value: v, text: t, selected: v === (p.kind || 'subscription') || null }))),
      price: h('input', { class: 'input', type: 'number', min: 0, step: '0.01', value: p.price_usd ?? 0 }), credits: h('input', { class: 'input', type: 'number', min: 0, value: p.credits ?? 0 }),
      days: h('input', { class: 'input', type: 'number', min: 1, value: p.period_days ?? 30 }), sort: h('input', { class: 'input', type: 'number', value: p.sort ?? 0 }),
      active: h('input', { type: 'checkbox', checked: p.active === 0 ? null : true }),
      benefits: h('textarea', { class: 'input', placeholder: 'One benefit per line' }),
    };
    f.benefits.value = (p.benefits || []).join('\n');
    const rules = p.rules || {};
    const num = Object.fromEntries(RULE_NUM.map(([k]) => [k, h('input', { class: 'input', type: 'number', min: 0, value: rules[k] ?? '' })]));
    const effort = h('select', { class: 'select' }, ['off', 'low', 'medium', 'high', 'max'].map((e) => h('option', { value: e, text: e, selected: e === (rules.max_effort || 'low') || null })));
    const tiers = ['quick', 'smart', 'genius'].map((t) => h('input', { type: 'checkbox', value: t, checked: (rules.tiers || []).includes(t) || null }));
    const modes = r.modes.map((m) => h('input', { type: 'checkbox', value: m.id, checked: (rules.modes || []).includes(m.id) || null }));
    const flags = ['images', 'mcp', 'private_default'].map((k) => [k, h('input', { type: 'checkbox', checked: rules[k] || null })]);
    const sub = () => f.kind.value === 'subscription';
    const body = h('div', { class: 'panel' }, h('h3', { text: isNew ? 'New plan or pack' : `${p.name} (${p.id}) · ${p.users} user(s)` }),
      h('div', { class: 'form-grid' }, h('label', null, 'Id', f.id), h('label', null, 'Name shown to users', f.name), h('label', null, 'Type', f.kind), h('label', null, 'Price (USD)', f.price),
        h('label', null, 'Credits', f.credits), h('label', null, 'Period / validity (days)', f.days), h('label', null, 'Order in the store', f.sort), h('label', { class: 'check' }, f.active, 'Visible in the store')),
      h('label', { style: 'display:grid;gap:4px' }, h('span', { class: 'muted small', text: 'Benefits (shown on the plan card)' }), f.benefits),
      h('div', { class: 'sub-rules' }, h('h3', { text: 'What this plan unlocks' }),
        h('div', { class: 'form-grid' }, h('label', null, 'Highest effort', effort), ...RULE_NUM.map(([k, l]) => h('label', null, l, num[k]))),
        h('div', { class: 'chk-row' }, h('span', { class: 'muted small', text: 'Brain tiers:' }), ...tiers.map((c) => h('label', null, c, c.value))),
        h('div', { class: 'chk-row' }, h('span', { class: 'muted small', text: 'Modes:' }), ...modes.map((c, i) => h('label', null, c, r.modes[i].name))),
        h('div', { class: 'chk-row' }, ...flags.map(([k, c]) => h('label', null, c, k.replace('_', ' '))))));
    const save = h('button', { class: 'btn primary', type: 'button', text: isNew ? 'Create' : 'Save plan', onclick: async () => {
      const payload = { id: f.id.value.trim() || undefined, name: f.name.value, kind: f.kind.value, price_usd: +f.price.value, credits: +f.credits.value, period_days: +f.days.value, sort: +f.sort.value,
        active: f.active.checked, benefits: f.benefits.value.split('\n').map((x) => x.trim()).filter(Boolean),
        rules: sub() ? { ...Object.fromEntries(RULE_NUM.filter(([k]) => num[k].value !== '').map(([k]) => [k, +num[k].value])), max_effort: effort.value,
          tiers: tiers.filter((c) => c.checked).map((c) => c.value), modes: modes.filter((c) => c.checked).map((c) => c.value), ...Object.fromEntries(flags.map(([k, c]) => [k, c.checked])) } : {} };
      try { await api(isNew ? '/api/admin/plans' : `/api/admin/plans/${p.id}`, { method: isNew ? 'POST' : 'PUT', body: payload }); toast('Saved. Users see the change now.'); show(); } catch (e) { fail(e); }
    } });
    const hide = !isNew && p.id !== 'free' ? h('button', { class: 'btn danger', type: 'button', text: 'Hide from store', onclick: async () => { await api(`/api/admin/plans/${p.id}`, { method: 'DELETE' }).catch(fail); show(); } }) : null;
    f.kind.addEventListener('change', () => { body.querySelector('.sub-rules').hidden = !sub(); });
    body.querySelector('.sub-rules').hidden = !sub();
    body.append(h('div', { class: 'btn-row' }, save, hide));
    return body;
  };
  out.append(...r.plans.map((p) => editor(p, false)), editor({ kind: 'subscription', active: 1, rules: { tiers: ['quick'], max_effort: 'low', modes: ['fast', 'normal'] } }, true));
  return out;
}

// ------------------------------------------------------------------ purchases, activity, models
async function purchases() {
  const r = await api('/api/admin/purchases');
  const act = (p, kind, label, cls) => h('button', { class: 'btn small ' + cls, type: 'button', text: label, onclick: async () => { await api(`/api/admin/purchases/${p.id}/${kind}`, { method: 'POST' }).catch(fail); toast('Done.'); show(); } });
  return h('div', null, h('p', { class: 'hint', text: 'With manual payments, an order stays Pending until you confirm the money arrived. Marking it paid adds the credits or switches the plan, once.' }),
    table([{ label: 'When', render: (p) => when(p.created_at) }, { label: 'User', render: (p) => p.email || p.name || p.user_id }, { label: 'What', key: 'plan_id' }, { label: 'Amount', render: (p) => usd(p.amount_usd) },
      { label: 'Credits', render: (p) => num(p.credits) }, { label: 'Provider', key: 'provider' }, { label: 'Status', render: (p) => badge(p.status, p.status === 'paid' ? 'ok' : p.status === 'pending' ? 'warn' : 'bad') },
      { label: '', render: (p) => (p.status === 'pending' ? h('span', null, act(p, 'paid', 'Mark paid', 'primary'), ' ', act(p, 'cancel', 'Cancel', '')) : '') }], r.purchases));
}
async function activityView() {
  const r = await api('/api/admin/activity?limit=200');
  return h('div', null, h('p', { class: 'hint', text: 'Everything every user and admin did, newest first.' }),
    table([{ label: 'When', render: (e) => when(e.created_at) }, { label: 'User', render: (e) => e.email || e.name || e.user_id }, { label: 'What', key: 'kind' }, { label: 'By', render: (e) => (e.actor === e.user_id ? 'user' : e.actor) },
      { label: 'Detail', wrap: true, render: (e) => JSON.stringify(e.detail).slice(0, 220) }], r.events));
}
async function models() {
  const rows = await api('/api/admin/catalog');
  const sync = h('button', { class: 'btn', type: 'button', text: 'Sync prices from OpenRouter', onclick: async () => { try { const r = await api('/api/admin/catalog/sync', { method: 'POST' }); toast(`Synced. ${r.updated} updated, ${r.new} new waiting for approval.`, 5000); show(); } catch (e) { fail(e); } } });
  const approve = async (m, on, tier) => { await api('/api/admin/catalog/approve', { method: 'POST', body: { model_id: m.id, on, tier } }).catch(fail); show(); };
  return h('div', null, h('div', { class: 'toolbar' }, sync, h('span', { class: 'hint', text: 'New models from OpenRouter wait here until you approve them and choose a tier.' })),
    table([{ label: 'Model', render: (m) => h('span', null, h('b', { text: m.name }), ' ', h('span', { class: 'muted tiny', text: m.id })) }, { label: 'Tier', render: (m) => h('select', { class: 'select small', onchange: (e) => approve(m, !!m.approved, e.target.value) }, ['quick', 'smart', 'genius'].map((t) => h('option', { value: t, text: t, selected: t === m.tier || null }))) },
      { label: 'In / out $ per 1M', render: (m) => `${fmtNum(m.price_in)} / ${fmtNum(m.price_out)}` }, { label: 'Thinks', render: (m) => (m.thinks ? 'yes' : 'no') }, { label: 'Available', render: (m) => (m.available ? 'yes' : badge('gone', 'bad')) },
      { label: 'Approved', render: (m) => h('input', { type: 'checkbox', checked: m.approved ? true : null, 'aria-label': 'Approved', onchange: (e) => approve(m, e.target.checked) }) }], rows));
}
const VIEWS = { overview, users, queries, plans, purchases, activity: activityView, models };
start();
