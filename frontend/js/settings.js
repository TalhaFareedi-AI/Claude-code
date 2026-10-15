// The picker: mode, brain, effort, rounds, cost cap, tools, skills, privacy. Web and phone read the same lists
// from the server, so a new mode or model appears here without a new release.
import { h, $ } from './dom.js';
import { buildTeamSettings } from './team.js';

export const DISPLAY_DEFAULTS = { anim: 'on', open: 'running', timing: true, thinking: true, size: 'm', density: 'cozy', accent: 'teal' };
export const ACCENTS = { teal: '#2a7f6f', blue: '#2f6fd1', violet: '#7a55c9', orange: '#c4622d', rose: '#c2415d' };

export const DEFAULTS = {
  mode: 'auto', brains: {}, effort: 'auto', rounds: null, tries: null, cap: null,
  tools: ['chart', 'diagram', 'documents', 'ppt', 'web'], skills: null, private: false,
  team: {}, teacher_enabled: true, teacher_model: null,
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

export function buildSettings(boot, S, { onChange, focus, display, onDisplay }) {
  const body = h('div');
  const mode = currentMode(boot, S);
  const rules = boot.plans[boot.user.plan].rules;
  const set = (patch) => { Object.assign(S, patch); onChange(); render(); };

  function render() {
    body.replaceChildren();
    // --- Mode
    const modeList = h('div', { class: 'mode-list', role: 'radiogroup', 'aria-label': 'Mode' });
    const all = [{ id: 'auto', name: 'Auto', blurb: 'I pick Fast, Normal or Deep for each message', allowed: true }, ...boot.modes];
    for (const m of all) {
      modeList.append(h('button', { type: 'button', class: 'mode-opt', role: 'radio', 'aria-checked': String(S.mode === m.id), 'aria-disabled': String(!m.allowed),
        onclick: () => { if (!m.allowed) return; set({ mode: m.id, brains: {}, rounds: null, tries: null, cap: null }); } },
      h('div', null, h('div', { class: 't', text: m.name }), h('div', { class: 'd', text: m.blurb })), m.allowed ? null : h('span', { class: 'lock', text: '🔒 ' + (m.locked || 'Higher plan') })));
    }
    body.append(h('section', { class: 'sec', id: 'sec-mode' }, h('h3', { text: 'Mode: how the AI works' }), modeList));

    // --- Brains
    const brainSec = h('section', { class: 'sec', id: 'sec-brain' }, h('h3', { text: 'Brain: who does the work' }));
    if (!mode) brainSec.append(h('p', { class: 'muted small', text: 'Auto picks a cheap brain for easy work and a stronger one for hard work. Choose a mode to pick brains yourself.' }));
    else {
      brainSec.append(h('p', { class: 'muted small', text: 'Each role can use a different brain. Leave "Auto" if unsure. 🇨🇳 or 🌐 shows which lab runs it, and "thinks" means it can use scrap paper.' }));
      for (const [role, slot] of Object.entries(mode.slots)) {
        const label = boot.roles[role] || role;
        if (Array.isArray(slot)) {
          const min = mode.params.min_members || mode.params.min_thinkers || 2, max = mode.params.max_members || mode.params.max_thinkers || 5;
          const cur = Array.isArray(S.brains[role]) ? S.brains[role] : slot.map(() => '');
          const wrap = h('div');
          cur.forEach((v, k) => wrap.append(h('div', { class: 'role-row' }, h('span', { class: 'small', text: `${label} ${k + 1}` }),
            brainSelect(boot, v, (val) => { const next = [...cur]; next[k] = val; const full = next.every(Boolean); const b = { ...S.brains }; if (full) b[role] = next; else delete b[role]; Object.assign(S, { brains: b }); onChange(); }, { label: `${label} ${k + 1}` }))));
          wrap.append(h('div', { class: 'btn-row' },
            h('button', { type: 'button', class: 'btn small', text: '＋ Add', disabled: cur.length >= max, onclick: () => set({ brains: { ...S.brains, [role]: [...cur, ''] } }) }),
            h('button', { type: 'button', class: 'btn small', text: '− Remove', disabled: cur.length <= min, onclick: () => set({ brains: { ...S.brains, [role]: cur.slice(0, -1) } }) })));
          if (cur.some((x) => !x)) wrap.append(h('p', { class: 'muted tiny', text: 'Fill every slot to use your own team, or leave all on Auto.' }));
          brainSec.append(wrap);
        } else {
          brainSec.append(h('div', { class: 'role-row' }, h('span', { class: 'small', text: label }),
            brainSelect(boot, S.brains[role], (val) => { const b = { ...S.brains }; if (val) b[role] = val; else delete b[role]; Object.assign(S, { brains: b }); onChange(); }, { label })));
        }
      }
    }
    body.append(brainSec);
    body.append(buildTeamSettings(boot, S, { onChange, brainSelect }));

    // --- Effort
    const seg = h('div', { class: 'seg', role: 'group', 'aria-label': 'Effort' }, boot.efforts.map((e) => h('button', { type: 'button', text: e.label, 'aria-pressed': String(S.effort === e.id), disabled: !e.allowed, title: e.allowed ? '' : 'Needs a higher plan', onclick: () => set({ effort: e.id }) })));
    body.append(h('section', { class: 'sec', id: 'sec-effort' }, h('h3', { text: 'Effort: how hard to think' }), seg,
      h('p', { class: 'muted tiny', text: 'More effort costs more and takes longer. It only helps on hard questions. Auto chooses for you.' })));

    // --- Rounds / tries / cap
    const sliders = h('section', { class: 'sec', id: 'sec-limits' }, h('h3', { text: 'Limits' }));
    const slider = (label, min, max, val, key, unit = '') => {
      const out = h('b', { text: val == null ? 'Auto' : val + unit });
      const input = h('input', { type: 'range', min, max, step: 1, value: val ?? min, 'aria-label': label });
      input.addEventListener('input', () => { out.textContent = input.value + unit; S[key] = +input.value; onChange(); });
      return h('div', { class: 'ctl' }, h('label', null, h('span', { text: label }), out), input);
    };
    if (mode?.params.max_rounds) sliders.append(slider('Rounds of rewriting', 1, Math.min(mode.params.max_rounds, rules.max_rounds), S.rounds ?? Math.min(mode.params.default_rounds, rules.max_rounds), 'rounds'));
    if (mode?.params.max_tries) sliders.append(slider('Long-thinking tries', 1, Math.min(mode.params.max_tries, rules.max_tries), S.tries ?? Math.min(mode.params.default_tries, rules.max_tries), 'tries'));
    const capMax = mode ? mode.max_credits : 160;
    sliders.append(slider('Cost cap (credits)', 1, capMax, S.cap ?? Math.min(capMax, Math.max(boot.user.auto_spend, 1)), 'cap'));
    sliders.append(h('div', { class: 'btn-row' }, h('button', { type: 'button', class: 'btn small', text: 'Use defaults', onclick: () => set({ rounds: null, tries: null, cap: null }) })));
    sliders.append(h('p', { class: 'muted tiny', text: 'The run stops at the cap and keeps the best answer so far. Unused credits come back.' }));
    body.append(sliders);

    // --- Privacy
    const priv = h('input', { type: 'checkbox', id: 'sw-priv', checked: S.private || null });
    priv.addEventListener('change', () => { S.private = priv.checked; onChange(); });
    body.append(h('section', { class: 'sec', id: 'sec-privacy' }, h('h3', { text: 'Privacy' }),
      h('label', { class: 'switch', for: 'sw-priv' }, priv, h('span', null, 'Private route: only hosts that do not keep or train on prompts')),
      h('p', { class: 'muted tiny', text: 'Web search sits outside this setting. Private routes may cost more or have fewer brains.' })));

    // --- Tools
    const toolBox = h('div');
    for (const t of boot.tools) {
      const cb = h('input', { type: 'checkbox', id: `tool-${t.id}`, checked: S.tools.includes(t.id) || null });
      cb.addEventListener('change', () => { S.tools = cb.checked ? [...new Set([...S.tools, t.id])] : S.tools.filter((x) => x !== t.id); onChange(); });
      toolBox.append(h('label', { class: 'switch', for: `tool-${t.id}` }, cb, t.label));
    }
    body.append(h('section', { class: 'sec', id: 'sec-tools' }, h('h3', { text: 'Tools for this chat' }), toolBox));

    // --- Skills
    const skillBox = h('div');
    const active = S.skills ?? boot.skills.map((s) => s.name);
    for (const s of boot.skills) {
      const cb = h('input', { type: 'checkbox', id: `sk-${s.name}`, checked: active.includes(s.name) || null });
      cb.addEventListener('change', () => { const cur = new Set(S.skills ?? boot.skills.map((x) => x.name)); cb.checked ? cur.add(s.name) : cur.delete(s.name); S.skills = [...cur]; onChange(); });
      skillBox.append(h('label', { class: 'switch', for: `sk-${s.name}`, title: s.description }, cb, h('span', null, h('b', { text: s.name }), ' ', h('span', { class: 'muted small', text: s.description.split('. ')[0] }))));
    }
    // --- Display (how it looks and moves)
    const dset = (k, v) => { display[k] = v; onDisplay(); render(); };
    const choice = (label, key, opts) => h('div', { class: 'sec-row' }, h('div', { class: 'small', text: label }),
      h('div', { class: 'seg', role: 'group', 'aria-label': label }, opts.map(([v, t]) => h('button', { type: 'button', text: t, 'aria-pressed': String(display[key] === v), onclick: () => dset(key, v) }))));
    const sw = (label, key) => { const cb = h('input', { type: 'checkbox', id: `d-${key}`, checked: display[key] || null }); cb.addEventListener('change', () => dset(key, cb.checked)); return h('label', { class: 'switch', for: `d-${key}` }, cb, label); };
    body.append(h('section', { class: 'sec', id: 'sec-display' }, h('h3', { text: 'Display: how it looks and moves' }),
      choice('Animations', 'anim', [['on', 'On'], ['off', 'Off']]),
      choice('Steps panel', 'open', [['running', 'Open while running'], ['always', 'Always open'], ['never', 'Always closed']]),
      sw('Show time and token details for every AI call', 'timing'), sw('Show thinking summaries', 'thinking'),
      choice('Text size', 'size', [['s', 'Small'], ['m', 'Medium'], ['l', 'Large']]),
      choice('Spacing', 'density', [['compact', 'Compact'], ['cozy', 'Comfortable']]),
      h('div', { class: 'sec-row' }, h('div', { class: 'small', text: 'Accent color' }), h('div', { class: 'seg' }, Object.entries(ACCENTS).map(([k, c]) =>
        h('button', { type: 'button', class: 'swatch', style: `background:${c}`, 'aria-label': k, 'aria-pressed': String(display.accent === k), onclick: () => dset('accent', k) })))),
      h('button', { type: 'button', class: 'btn small', text: 'Reset display', onclick: () => { Object.assign(display, DISPLAY_DEFAULTS); onDisplay(); render(); } })));

    body.append(h('section', { class: 'sec', id: 'sec-skills' }, h('h3', { text: 'Skills (recipe cards, opened only when needed)' }), skillBox));
  }
  render();
  if (focus) queueMicrotask(() => $('#sec-' + focus, body)?.scrollIntoView({ block: 'start' }));
  return body;
}
