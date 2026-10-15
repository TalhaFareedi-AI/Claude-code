// Account screens: sign up and log in, plans and credit packs, the memory manager, and "my activity".
// Each opens inside the shared dialog. Everything the user sees here is also stored in SQLite on the server.
import { h, $, toast, timeAgo } from './dom.js';
import { api, ApiError } from './api.js';

const usd = (n) => (n === 0 ? 'Free' : `$${Number(n).toFixed(n % 1 ? 2 : 0)}`);
const when = (ts) => (ts ? new Date(ts * 1000).toLocaleString() : '–');

export function setupAccount({ app, dialog, hide, refreshWallet }) {
  const boot = () => app.boot;

  // ---------------------------------------------------------------- sign up / log in
  function showAuth(mode = 'login') {
    const isNew = mode === 'register';
    const err = h('p', { class: 'form-error', role: 'alert', hidden: true });
    const email = h('input', { class: 'input', type: 'email', id: 'au-email', autocomplete: 'email', required: true, placeholder: 'you@example.com' });
    const pass = h('input', { class: 'input', type: 'password', id: 'au-pass', autocomplete: isNew ? 'new-password' : 'current-password', required: true, minlength: 8, placeholder: 'At least 8 characters' });
    const name = h('input', { class: 'input', id: 'au-name', autocomplete: 'name', placeholder: 'What should I call you? (optional)' });
    const submit = h('button', { type: 'submit', class: 'btn primary block', text: isNew ? 'Create my account' : 'Log in' });
    const form = h('form', { class: 'stack' },
      isNew ? h('p', { class: 'muted small', text: 'Your chats, memory and credits so far stay with your new account.' }) : null,
      h('label', { class: 'small' }, 'Email', email), isNew ? h('label', { class: 'small' }, 'Name', name) : null,
      h('label', { class: 'small' }, 'Password', pass), err, submit,
      h('button', { type: 'button', class: 'btn small', text: isNew ? 'I already have an account' : 'Create a new account', onclick: () => showAuth(isNew ? 'login' : 'register') }));
    form.addEventListener('submit', async (e) => {
      e.preventDefault(); submit.disabled = true; err.hidden = true;
      try {
        await api(isNew ? '/api/auth/register' : '/api/auth/login', { method: 'POST', body: { email: email.value, password: pass.value, name: name.value } });
        try { localStorage.removeItem('sh.conv'); localStorage.removeItem('sh.run'); } catch { /* ignore */ }
        location.reload();
      } catch (ex) { err.textContent = ex instanceof ApiError ? ex.message : 'Something went wrong.'; err.hidden = false; submit.disabled = false; }
    });
    dialog(isNew ? 'Create your account' : 'Log in', form);
    email.focus();
  }

  async function logout() {
    await api('/api/auth/logout', { method: 'POST' }).catch(() => {});
    try { localStorage.removeItem('sh.conv'); localStorage.removeItem('sh.run'); } catch { /* ignore */ }
    location.reload();
  }

  // ---------------------------------------------------------------- plans and credits
  async function showPlans() {
    let d;
    try { d = await api('/api/plans'); } catch (e) { return toast(e.message); }
    const buy = async (p, btn) => {
      if (!d.registered) { toast('Create an account first, so your purchase stays with you.'); return showAuth('register'); }
      btn.disabled = true;
      try {
        const r = await api('/api/purchase', { method: 'POST', body: { plan_id: p.id } });
        toast(r.message, 4500);
        if (r.purchase.status === 'paid' && p.kind === 'subscription') { location.reload(); return; }
        refreshWallet(); showPlans();
      } catch (e) { toast(e.message, 4500); btn.disabled = false; }
    };
    const card = (p) => {
      const btn = h('button', { type: 'button', class: 'btn ' + (p.current ? '' : 'primary'), text: p.current ? 'Your plan' : p.price_usd === 0 ? 'Switch to Free' : `Buy for ${usd(p.price_usd)}`, disabled: p.current || null });
      btn.addEventListener('click', () => buy(p, btn));
      return h('div', { class: 'plan-card' + (p.current ? ' current' : '') },
        h('h3', { text: p.name }), h('div', { class: 'price' }, h('b', { text: usd(p.price_usd) }), p.kind === 'subscription' && p.price_usd ? h('span', { class: 'muted small', text: ' / month' }) : null),
        h('div', { class: 'credits', text: `${p.credits.toLocaleString()} credits` }),
        p.kind === 'topup' ? h('div', { class: 'muted tiny', text: `$${p.usd_per_1000_credits} per 1,000 credits` }) : null,
        h('ul', null, (p.benefits || []).map((b) => h('li', { text: b }))), btn);
    };
    const subs = d.plans.filter((p) => p.kind === 'subscription'), packs = d.plans.filter((p) => p.kind === 'topup');
    const note = d.provider === 'test' ? 'Test payments: no real money moves. Credits are added at once.'
      : 'Orders are confirmed by the admin (for example after a bank transfer). Credits arrive once confirmed.';
    dialog('Plans and credits',
      h('p', { class: 'muted small', text: `You have ${boot().wallet.available} credits. ${d.renews_at ? 'Your plan renews on ' + new Date(d.renews_at * 1000).toLocaleDateString() + '.' : ''}` }),
      h('div', { class: 'plan-grid' }, subs.map(card)),
      packs.length ? h('h3', { class: 'sec-title', text: 'Need more? Credit packs' }) : null,
      h('div', { class: 'plan-grid' }, packs.map(card)),
      h('p', { class: 'muted tiny', text: note }),
      d.purchases.length ? h('details', { class: 'fold' }, h('summary', { text: `Your orders (${d.purchases.length})` }),
        h('div', { class: 'md' }, h('table', null, h('tbody', null, d.purchases.map((p) => h('tr', null, h('td', { text: when(p.created_at) }), h('td', { text: p.plan_id }), h('td', { text: usd(p.amount_usd) }), h('td', { text: p.status }))))))) : null);
    $('#dialog .sheet-card').classList.add('wide');
  }

  // ---------------------------------------------------------------- memory manager
  async function showMemory() {
    let d;
    try { d = await api('/api/memory'); } catch (e) { return toast(e.message); }
    const list = h('div', { class: 'mem-list' });
    const search = h('input', { class: 'input', type: 'search', placeholder: 'Search what I remember…', 'aria-label': 'Search memories' });
    let timer;

    const row = (m) => {
      const text = h('span', { class: 'mem-text', tabindex: 0, role: 'button', title: 'Click to edit', text: m.content });
      const edit = () => {
        const inp = h('input', { class: 'input', value: m.content, maxlength: 300 });
        const save = async () => { try { await api(`/api/memory/${m.id}`, { method: 'PUT', body: { content: inp.value } }); } catch (e) { toast(e.message); } load(); };
        inp.addEventListener('keydown', (e) => { if (e.key === 'Enter') save(); if (e.key === 'Escape') load(); });
        inp.addEventListener('blur', save);
        text.replaceWith(inp); inp.focus();
      };
      text.addEventListener('click', edit); text.addEventListener('keydown', (e) => { if (e.key === 'Enter') edit(); });
      const pin = h('button', { type: 'button', class: 'rate', 'aria-pressed': String(!!m.pinned), title: 'Pinned memories are always used', text: '📌', onclick: async () => { await api(`/api/memory/${m.id}`, { method: 'PUT', body: { pinned: !m.pinned } }); load(); } });
      const del = h('button', { type: 'button', class: 'rate', title: 'Delete for good', 'aria-label': 'Delete memory', text: '✕', onclick: async () => { await api(`/api/memory/${m.id}`, { method: 'DELETE' }); load(); } });
      return h('div', { class: 'mem' }, h('span', { class: 'kind-badge', text: m.kind }), text,
        h('span', { class: 'muted tiny', text: m.source === 'user' ? 'you' : 'auto' }), pin, del);
    };

    async function load() {
      const q = search.value.trim();
      const r = await api('/api/memory' + (q ? `?q=${encodeURIComponent(q)}` : ''));
      list.replaceChildren(...(r.items.length ? r.items.map(row) : [h('p', { class: 'muted small', text: q ? 'Nothing matches.' : 'Nothing saved yet. Tell me "remember that…" or just chat: I pick up what matters.' })]));
    }
    search.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(load, 200); });

    const addInput = h('input', { class: 'input', placeholder: 'Add something I should remember…', maxlength: 300, 'aria-label': 'New memory' });
    const kind = h('select', { class: 'select small', 'aria-label': 'Kind' }, d.kinds.map((k) => h('option', { value: k, text: k })));
    const add = async () => {
      if (addInput.value.trim().length < 2) return;
      try { await api('/api/memory', { method: 'POST', body: { content: addInput.value, kind: kind.value, importance: 4, pinned: false } }); addInput.value = ''; load(); } catch (e) { toast(e.message, 4500); }
    };
    addInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); add(); } });

    const sw = h('input', { type: 'checkbox', id: 'mem-on', checked: d.enabled || null });
    sw.addEventListener('change', async () => { await api('/api/memory/enabled', { method: 'PUT', body: { enabled: sw.checked } }); app.boot.user.memory_enabled = sw.checked; toast(sw.checked ? 'Memory is on.' : 'Memory is off. I will not use or save anything.'); });

    const p = d.profile || {};
    const f = (k, label, ph) => h('label', { class: 'small' }, label, h('input', { class: 'input', id: `pf-${k}`, value: Array.isArray(p[k]) ? p[k].join(', ') : (p[k] || ''), placeholder: ph }));
    const profile = h('details', { class: 'fold' }, h('summary', { text: 'Learning profile (level, interests, goal)' }),
      f('level', 'Level (beginner, medium, advanced)', 'beginner'), f('interests', 'Interests (comma separated)', 'cricket, cooking'), f('language', 'Language', 'English'),
      f('likes', 'How you like answers', 'short answers, step by step maths'), f('weak_topics', 'Topics you find hard', 'fractions'), f('goal', 'Your goal', 'pass the physics exam'),
      h('button', { type: 'button', class: 'btn small primary', text: 'Save profile', onclick: async () => {
        const l = (k) => $(`#pf-${k}`).value.split(',').map((x) => x.trim()).filter(Boolean).slice(0, 6);
        await api('/api/profile', { method: 'PUT', body: { level: $('#pf-level').value.trim(), interests: l('interests'), language: $('#pf-language').value.trim(), likes: $('#pf-likes').value.trim(), weak_topics: l('weak_topics'), goal: $('#pf-goal').value.trim() } });
        toast('Profile saved.');
      } }));

    dialog('What I remember about you',
      h('p', { class: 'muted small', text: 'I keep short notes so I can help like a tutor who knows you. You see everything here and can edit, pin or delete any note. I never save passwords, keys or card numbers.' }),
      h('label', { class: 'switch', for: 'mem-on' }, sw, 'Use memory in my chats'),
      h('div', { class: 'row' }, addInput, kind, h('button', { type: 'button', class: 'btn primary', text: 'Add', onclick: add })),
      search, list, profile,
      h('div', { class: 'btn-row' }, h('button', { type: 'button', class: 'btn danger', text: 'Forget everything', onclick: async () => {
        if (!confirm('Delete every saved memory? This cannot be undone.')) return;
        await api('/api/memory', { method: 'DELETE' }); load(); toast('All memories deleted.');
      } })));
    $('#dialog .sheet-card').classList.add('wide');
    load();
  }

  // ---------------------------------------------------------------- my activity (the user's blueprint)
  const KIND = { chat_sent: 'Asked a question', run_finished: 'Run finished', login: 'Logged in', registered: 'Created account', account_created: 'Started',
    purchase_paid: 'Purchase', purchase_started: 'Started a purchase', plan_changed: 'Plan changed', plan_renewed: 'Plan renewed', plan_expired: 'Plan expired',
    memory_learned: 'Memory updated', memory_saved: 'Saved a memory', memory_forgot: 'Forgot a memory', memory_added: 'Added a memory', memory_deleted: 'Deleted a memory',
    admin_credits: 'Admin changed your credits', admin_changed_user: 'Admin changed your account', admin_viewed_chat: 'Admin viewed a chat', password_changed: 'Password changed' };

  async function showActivity() {
    let b;
    try { b = await api('/api/me/blueprint'); } catch (e) { return toast(e.message); }
    const t = b.totals;
    const tile = (label, v) => h('div', { class: 'tile' }, h('b', { text: String(v) }), h('span', { class: 'muted tiny', text: label }));
    dialog('My activity',
      h('div', { class: 'tiles' }, tile('chats', t.conversations), tile('questions', t.messages), tile('runs', t.runs), tile('credits used', t.credits_used),
        tile('credits left', b.wallet.available), tile('memories', t.memories), tile('files made', t.files)),
      b.limits.daily ? h('p', { class: 'muted small', text: `Daily limit: ${b.limits.daily} credits (used today: ${b.wallet.spent_today}).${b.limits.monthly ? ` Monthly limit: ${b.limits.monthly}.` : ''}` }) : null,
      b.by_mode.length ? h('div', { class: 'md' }, h('table', null, h('thead', null, h('tr', null, ['Mode', 'Runs', 'Credits'].map((x) => h('th', { text: x })))),
        h('tbody', null, b.by_mode.map((m) => h('tr', null, h('td', { text: m.mode || '–' }), h('td', { text: m.runs }), h('td', { text: m.credits || 0 })))))) : null,
      h('h3', { class: 'sec-title', text: 'Recent history' }),
      h('ul', { class: 'timeline' }, b.timeline.slice(0, 25).map((e) => h('li', null, h('span', { class: 'muted tiny', text: timeAgo(e.created_at) }), ' ', KIND[e.kind] || e.kind,
        e.detail?.preview ? h('span', { class: 'muted small', text: ` · "${e.detail.preview.slice(0, 60)}"` }) : null))),
      h('div', { class: 'btn-row' },
        h('a', { class: 'btn', href: '/api/me/export', download: 'my-data.json', text: '⬇ Export my data' }),
        h('button', { type: 'button', class: 'btn danger', text: 'Delete my account', onclick: async () => {
          const ans = prompt('This deletes your chats, memory, files and credits for good. Type DELETE to confirm.');
          if (ans !== 'DELETE') return;
          await api('/api/me', { method: 'DELETE', body: { confirm: 'DELETE' } }).catch((e) => toast(e.message));
          try { localStorage.clear(); } catch { /* ignore */ }
          location.reload();
        } })));
    $('#dialog .sheet-card').classList.add('wide');
  }

  return { showAuth, logout, showPlans, showMemory, showActivity };
}
