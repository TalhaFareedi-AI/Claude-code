// The picker: mode, brain, effort, rounds, cost cap, tools, skills, privacy. Web and phone read the same lists
// from the server, so a new mode or model appears here without a new release.
import { h, $ } from './dom.js';
import { buildTeamSettings, teamName } from './team.js';

export const DISPLAY_DEFAULTS = { anim: 'on', open: 'running', timing: true, thinking: true, size: 'm', density: 'cozy', accent: 'teal' };
export const ACCENTS = { teal: '#2a7f6f', blue: '#2f6fd1', violet: '#7a55c9', orange: '#c4622d', rose: '#c2415d' };

export const DEFAULTS = {
  mode: 'auto', brains: {}, effort: 'auto', rounds: null, tries: null, cap: null,
  tools: ['chart', 'diagram', 'documents', 'ppt', 'web'], skills: null, private: false,
  team: {}, teacher_enabled: false, teacher_model: null,
};

const TIER_LABEL = { quick: 'Quick (cheap, fast)', smart: 'Smart (all-rounder)', genius: 'Genius (strongest)' };
const regionTag = (m) => (m.region === 'china' ? '🇨🇳 China lab' : m.region === 'west' ? '🌐 Western lab' : m.lab);
export const modelLabel = (m) => `${m.name} · ${regionTag(m)} · ${m.thinks ? 'thinks' : 'no thinking'} · ${m.level}${m.allowed ? '' : ' · higher plan'}`;

export function currentMode(boot, S) {
  return boot.modes.find((m) => m.id === S.mode) || null;
}

export function modeName(boot, S) {
  return S.mode === 'auto' ? 'Auto' : (currentMode(boot, S)?.name || 'Normal');
}

function brainSelect(boot, value, onPick, { label }) {
  const sel = h('select', { class: 'select', 'aria-label': label });
  sel.append(h('option', { value: '', text: 'Auto (best fit)' }));
  for (const tier of ['quick', 'smart', 'genius']) {
    const opts = boot.models.filter((m) => m.tier === tier);
    if (!opts.length) continue;
    sel.append(h('optgroup', { label: TIER_LABEL[tier] }, opts.map((m) => h('option', { value: m.id, text: modelLabel(m), disabled: !m.allowed }))));
  }
  sel.value = value || '';
  sel.addEventListener('change', () => onPick(sel.value));
  return sel;
}

// Tabs: each one is one clear job, so nothing is buried in a long scroll.
export const TABS = [
  { id: 'mode', icon: '🎛️', label: 'Mode', hint: 'How the AI works on your message' },
  { id: 'brains', icon: '🧠', label: 'Brains', hint: 'Which AI model does each job' },
  { id: 'planning', icon: '🗺️', label: 'Planning', hint: 'A team that plans big tasks first' },
  { id: 'research', icon: '🔎', label: 'Research', hint: 'Web search with sources' },
  { id: 'build', icon: '✅', label: 'Build and check', hint: 'Who writes and reviews, and the teaching mode' },
  { id: 'limits', icon: '⚡', label: 'Effort and limits', hint: 'How hard to think and how much to spend' },
  { id: 'tools', icon: '🧰', label: 'Tools and skills', hint: 'What the AI may use' },
  { id: 'display', icon: '🎨', label: 'Display', hint: 'How it looks and moves' },
];
const FOCUS_TAB = { mode: 'mode', brain: 'brains', brains: 'brains', team: 'planning', planning: 'planning', research: 'research', build: 'build', effort: 'limits', limits: 'limits', tools: 'tools', skills: 'tools', display: 'display', privacy: 'limits' };
let activeTab = 'mode';

// One tap sets every brain role: cheapest, balanced, or strongest model your plan allows.
function strategyBrains(boot, mode, strategy) {
  const ok = boot.models.filter((m) => m.allowed);
  if (!ok.length || strategy === 'auto') return {};
  const score = (m) => m.price_out + 0.3 * m.price_in;
  const sorted = [...ok].sort((a, b) => score(a) - score(b));
  const pickOne = strategy === 'cheapest' ? sorted[0] : strategy === 'strongest' ? sorted[sorted.length - 1] : sorted[Math.floor((sorted.length - 1) / 2)];
  const out = {};
  for (const [role, slot] of Object.entries(mode.slots)) out[role] = Array.isArray(slot) ? slot.map((_, k) => sorted[Math.min(sorted.length - 1, (strategy === 'strongest' ? sorted.length - 1 - k : k))].id) : pickOne.id;
  return out;
}

export function buildSettings(boot, S, { onChange, focus, display, onDisplay }) {
  const root = h('div', { class: 'settings-layout' });
  const rail = h('div', { class: 'tab-rail', role: 'tablist', 'aria-label': 'Settings sections', 'aria-orientation': 'vertical' });
  const pane = h('div', { class: 'tab-pane', role: 'tabpanel' });
  root.append(rail, pane);
  const mode = () => currentMode(boot, S);
  const rules = boot.plans[boot.user.plan]?.rules || {};
  const set = (patch) => { Object.assign(S, patch); onChange(); paint(); };
  const team = buildTeamSettings(boot, S, { onChange: () => { onChange(); paintRail(); }, brainSelect });
  if (focus && FOCUS_TAB[focus]) activeTab = FOCUS_TAB[focus];

  const section = (title, hint, ...kids) => h('div', { class: 'pane-section' }, h('h3', { text: title }), hint ? h('p', { class: 'tab-intro', text: hint }) : null, ...kids);

  const views = {
    mode() {
      const list = h('div', { class: 'mode-list', role: 'radiogroup', 'aria-label': 'Mode' });
      const all = [{ id: 'auto', name: 'Auto', blurb: 'I pick Fast, Normal or Deep for each message', allowed: true }, ...boot.modes];
      for (const m of all) {
        list.append(h('button', { type: 'button', class: 'mode-opt', role: 'radio', 'aria-checked': String(S.mode === m.id), 'aria-disabled': String(!m.allowed),
          onclick: () => { if (!m.allowed) return; set({ mode: m.id, brains: {}, rounds: null, tries: null, cap: null }); } },
        h('div', null, h('div', { class: 't', text: m.name }), h('div', { class: 'd', text: m.blurb })), m.allowed ? null : h('span', { class: 'lock', text: '🔒 ' + (m.locked || 'Higher plan') })));
      }
      return section('Mode', 'A mode is a ready-made way of thinking. Auto is a good choice if you are unsure.', list);
    },

    brains() {
      const m = mode() || { name: 'Auto', slots: { answer: 'tier:smart', worker: 'tier:smart' }, params: {}, auto: true };
      const quick = h('div', { class: 'seg', role: 'group', 'aria-label': 'Quick pick' }, [['auto', 'Auto'], ['cheapest', 'Cheapest'], ['balanced', 'Balanced'], ['strongest', 'Strongest']].map(([id, label]) =>
        h('button', { type: 'button', text: label, onclick: () => set({ brains: strategyBrains(boot, m, id) }) })));
      const rows = h('div', { class: 'brain-rows' });
      for (const [role, slot] of Object.entries(m.slots)) {
        const label = m.auto ? (role === 'answer' ? 'Answering brain' : 'Working brain (bigger tasks)') : (boot.roles[role] || role);
        if (Array.isArray(slot)) {
          const min = m.params.min_members || m.params.min_thinkers || 2, max = m.params.max_members || m.params.max_thinkers || 5;
          const cur = Array.isArray(S.brains[role]) ? S.brains[role] : slot.map(() => '');
          const wrap = h('div', { class: 'brain-group' }, h('div', { class: 'small b', text: label }));
          cur.forEach((v, k) => wrap.append(h('div', { class: 'role-row' }, h('span', { class: 'small', text: `${label} ${k + 1}` }),
            brainSelect(boot, v, (val) => { const next = [...cur]; next[k] = val; const b = { ...S.brains }; if (next.every(Boolean)) b[role] = next; else delete b[role]; Object.assign(S, { brains: b }); onChange(); }, { label: `${label} ${k + 1}` }))));
          wrap.append(h('div', { class: 'btn-row' },
            h('button', { type: 'button', class: 'btn small', text: '＋ Add', disabled: cur.length >= max, onclick: () => set({ brains: { ...S.brains, [role]: [...cur, ''] } }) }),
            h('button', { type: 'button', class: 'btn small', text: '− Remove', disabled: cur.length <= min, onclick: () => set({ brains: { ...S.brains, [role]: cur.slice(0, -1) } }) })));
          if (cur.some((x) => !x)) wrap.append(h('p', { class: 'muted tiny', text: 'Fill every slot to use your own group, or leave all on Auto.' }));
          rows.append(wrap);
        } else rows.append(h('div', { class: 'role-row' }, h('span', { class: 'small', text: label }),
          brainSelect(boot, S.brains[role], (val) => { const b = { ...S.brains }; if (val) b[role] = val; else delete b[role]; Object.assign(S, { brains: b }); onChange(); }, { label })));
      }
      return section(m.auto ? 'Brains for Auto' : `Brains for ${m.name}`, m.auto ? 'Auto picks Fast, Normal or Deep for you. Choose which brain writes the answer, and which does the step-by-step work on bigger tasks. Pick a specific mode (first tab) to choose a brain for every job.' : 'Each job can use a different AI model. 🇨🇳 or 🌐 shows which lab runs it. "Thinks" means it can use scrap paper before answering.',
        h('div', { class: 'team-block' }, h('b', { class: 'small', text: 'Quick pick for every job' }), quick), rows);
    },

    planning: () => section('Planning', null, team.planning),
    research: () => section('Research', null, team.research),
    build: () => section('Build and check', null, team.build),

    limits() {
      const m = mode();
      const seg = h('div', { class: 'seg', role: 'group', 'aria-label': 'Effort' }, boot.efforts.map((e) => h('button', { type: 'button', text: e.label, 'aria-pressed': String(S.effort === e.id), disabled: !e.allowed, title: e.allowed ? '' : 'Needs a higher plan', onclick: () => set({ effort: e.id }) })));
      const slider = (label, min, max, val, key, unit = '') => {
        const out = h('b', { text: val == null ? 'Auto' : val + unit });
        const input = h('input', { type: 'range', min, max, step: 1, value: val ?? min, 'aria-label': label });
        input.addEventListener('input', () => { out.textContent = input.value + unit; S[key] = +input.value; onChange(); });
        return h('div', { class: 'ctl' }, h('label', null, h('span', { text: label }), out), input);
      };
      const sliders = h('div', { class: 'team-block' });
      if (m?.params.max_rounds) sliders.append(slider('Rounds of rewriting', 1, Math.min(m.params.max_rounds, rules.max_rounds || 5), S.rounds ?? Math.min(m.params.default_rounds, rules.max_rounds || 5), 'rounds'));
      if (m?.params.max_tries) sliders.append(slider('Long-thinking tries', 1, Math.min(m.params.max_tries, rules.max_tries || 5), S.tries ?? Math.min(m.params.default_tries, rules.max_tries || 5), 'tries'));
      const capMax = m ? m.max_credits : 160;
      sliders.append(slider('Most credits this message may use', 1, capMax, S.cap ?? Math.min(capMax, Math.max(boot.user.auto_spend, 1)), 'cap'));
      sliders.append(h('div', { class: 'btn-row' }, h('button', { type: 'button', class: 'btn small', text: 'Use defaults', onclick: () => set({ rounds: null, tries: null, cap: null }) })));
      sliders.append(h('p', { class: 'muted tiny', text: 'The run stops at this limit and keeps the best answer so far. Unused credits come back.' }));
      const priv = h('input', { type: 'checkbox', id: 'sw-priv', checked: S.private || null });
      priv.addEventListener('change', () => { S.private = priv.checked; onChange(); });
      return section('Effort and limits', 'Effort is how much scrap paper the AI may use before answering. More effort costs more and takes longer. It only helps on hard questions.',
        h('div', { class: 'team-block' }, h('b', { class: 'small', text: 'Effort' }), seg), sliders,
        h('div', { class: 'team-block' }, h('b', { class: 'small', text: 'Privacy' }), h('label', { class: 'switch', for: 'sw-priv' }, priv, h('span', null, 'Private route: only hosts that do not keep or train on prompts')),
          h('p', { class: 'muted tiny', text: 'Web search sits outside this setting. Private routes may cost more or have fewer brains.' })));
    },

    tools() {
      const toolBox = h('div');
      for (const t of boot.tools) {
        const cb = h('input', { type: 'checkbox', id: `tool-${t.id}`, checked: S.tools.includes(t.id) || null });
        cb.addEventListener('change', () => { S.tools = cb.checked ? [...new Set([...S.tools, t.id])] : S.tools.filter((x) => x !== t.id); onChange(); });
        toolBox.append(h('label', { class: 'switch', for: `tool-${t.id}` }, cb, t.label));
      }
      const skillBox = h('div');
      const active = S.skills ?? boot.skills.map((x) => x.name);
      for (const sk of boot.skills) {
        const cb = h('input', { type: 'checkbox', id: `sk-${sk.name}`, checked: active.includes(sk.name) || null });
        cb.addEventListener('change', () => { const cur = new Set(S.skills ?? boot.skills.map((x) => x.name)); cb.checked ? cur.add(sk.name) : cur.delete(sk.name); S.skills = [...cur]; onChange(); });
        skillBox.append(h('label', { class: 'switch', for: `sk-${sk.name}`, title: sk.description }, cb, h('span', null, h('b', { text: sk.name }), ' ', h('span', { class: 'muted small', text: sk.description.split('. ')[0] }))));
      }
      return section('Tools and skills', 'Tools let the AI make charts, files and searches. Skills are recipe cards it opens only when a task needs them.',
        h('div', { class: 'team-block' }, h('b', { class: 'small', text: 'Tools for this chat' }), toolBox),
        h('div', { class: 'team-block' }, h('b', { class: 'small', text: 'Skills' }), skillBox));
    },

    display() {
      const dset = (k, v) => { display[k] = v; onDisplay(); paint(); };
      const choice = (label, key, opts) => h('div', { class: 'sec-row' }, h('div', { class: 'small', text: label }),
        h('div', { class: 'seg', role: 'group', 'aria-label': label }, opts.map(([v, t]) => h('button', { type: 'button', text: t, 'aria-pressed': String(display[key] === v), onclick: () => dset(key, v) }))));
      const sw = (label, key) => { const cb = h('input', { type: 'checkbox', id: `d-${key}`, checked: display[key] || null }); cb.addEventListener('change', () => dset(key, cb.checked)); return h('label', { class: 'switch', for: `d-${key}` }, cb, label); };
      return section('Display', 'Change how things look and move. Saved on this device.',
        choice('Animations', 'anim', [['on', 'On'], ['off', 'Off']]),
        choice('Steps panel', 'open', [['running', 'Open while running'], ['always', 'Always open'], ['never', 'Always closed']]),
        sw('Show time and token details for every AI call', 'timing'), sw('Show thinking summaries', 'thinking'),
        choice('Text size', 'size', [['s', 'Small'], ['m', 'Medium'], ['l', 'Large']]),
        choice('Spacing', 'density', [['compact', 'Compact'], ['cozy', 'Comfortable']]),
        h('div', { class: 'sec-row' }, h('div', { class: 'small', text: 'Accent color' }), h('div', { class: 'seg' }, Object.entries(ACCENTS).map(([k, c]) =>
          h('button', { type: 'button', class: 'swatch', style: `background:${c}`, 'aria-label': k, 'aria-pressed': String(display.accent === k), onclick: () => dset('accent', k) })))),
        h('button', { type: 'button', class: 'btn small', text: 'Reset display', onclick: () => { Object.assign(display, DISPLAY_DEFAULTS); onDisplay(); paint(); } }));
    },
  };

  function summary(id) {
    const m = mode();
    if (id === 'mode') return modeName(boot, S);
    if (id === 'brains') return Object.keys(S.brains).length ? 'Custom' : 'Auto';
    if (id === 'planning') return teamName(S.team);
    if (id === 'research') { const r = S.team?.researchers; return r?.enabled === false || r?.count === 0 ? 'Off' : r?.count ? `${r.count} on` : 'Auto'; }
    if (id === 'build') return S.teacher_enabled ? 'Teaching on' : 'Direct answers';
    if (id === 'limits') return (boot.efforts.find((e) => e.id === S.effort)?.label || 'Auto');
    if (id === 'tools') return `${S.tools.length} on`;
    return '';
  }

  function paintRail() {
    rail.replaceChildren(...TABS.map((t) => h('button', { type: 'button', role: 'tab', class: 'tab-btn', 'aria-selected': String(t.id === activeTab), id: `tab-${t.id}-btn`, title: t.hint,
      onclick: () => { activeTab = t.id; paint(); pane.scrollTop = 0; } },
    h('span', { class: 'tab-ico', 'aria-hidden': 'true', text: t.icon }), h('span', { class: 'tab-txt' }, h('b', { text: t.label }), h('span', { class: 'tab-sum', text: summary(t.id) })))));
  }
  function paint() {
    paintRail();
    pane.setAttribute('aria-labelledby', `tab-${activeTab}-btn`);
    pane.replaceChildren(views[activeTab]());
  }
  paint();
  return root;
}
