// The settings sheet. Plan section 14: a few groups with plain names, the basic controls first, and an
// Advanced fold for the rest. Money settings (Credits) never sit next to model settings (Models).
// Web and phone read the same lists from the server, so a new mode or model appears here with no new release.
import { h } from './dom.js';
import { buildTeamSettings, teamName } from './team.js';
import { ACCENTS, THEMES, FONTS, LOOKS, CHIP_LABELS, SIDE_LABELS } from './prefs.js';

export const DEFAULTS = {
  mode: 'auto', brains: {}, effort: 'auto', rounds: null, tries: null, cap: null,
  tools: ['chart', 'diagram', 'documents', 'ppt', 'flashcards', 'table', 'web'], skills: null, private: false, length: 'auto', image_model: null,
  team: {}, teacher_enabled: false, teacher_model: null, custom_models: false,
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

function brainSelect(boot, value, onPick, { label, auto = 'Auto (best fit)' }) {
  const sel = h('select', { class: 'select', 'aria-label': label });
  sel.append(h('option', { value: '', text: auto }));
  for (const tier of ['quick', 'smart', 'genius']) {
    const opts = boot.models.filter((m) => m.tier === tier);
    if (!opts.length) continue;
    sel.append(h('optgroup', { label: TIER_LABEL[tier] }, opts.map((m) => h('option', { value: m.id, text: modelLabel(m), disabled: !m.allowed }))));
  }
  sel.value = value || '';
  sel.addEventListener('change', () => onPick(sel.value));
  return sel;
}

// The six groups from the plan, then the user's own look. Each is one clear job.
export const TABS = [
  { id: 'models', icon: '🎛️', label: 'Models', hint: 'How the AI thinks, and which models do the work' },
  { id: 'team', icon: '🗺️', label: 'Team', hint: 'Planning, research and checking for bigger tasks' },
  { id: 'tools', icon: '🧰', label: 'Tools and skills', hint: 'What the AI may use' },
  { id: 'files', icon: '📁', label: 'Files', hint: 'Your workspace and storage' },
  { id: 'credits', icon: '◎', label: 'Credits', hint: 'What a message may cost' },
  { id: 'privacy', icon: '🔒', label: 'Privacy', hint: 'Where your data goes' },
  { id: 'look', icon: '🎨', label: 'Look and layout', hint: 'Make the screen yours' },
];
const FOCUS_TAB = {
  mode: 'models', models: 'models', brain: 'models', brains: 'models', effort: 'models', limits: 'models', length: 'models', build: 'models',
  team: 'team', planning: 'team', research: 'team',
  tools: 'tools', skills: 'tools', files: 'files', credits: 'credits', privacy: 'privacy', display: 'look', look: 'look',
};
const MAIN_ROLES = ['answer', 'worker', 'write', 'writer', 'think'];
let activeTab = 'models';
const openFolds = new Set();   // remembers which Advanced folds the user opened, across repaints

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

// ---- small building blocks, shared by every group -------------------------------------------------
const section = (title, hint, ...kids) => h('div', { class: 'pane-section' }, h('h3', { text: title }), hint ? h('p', { class: 'tab-intro', text: hint }) : null, ...kids);
const block = (title, ...kids) => h('div', { class: 'team-block' }, title ? h('b', { class: 'small', text: title }) : null, ...kids);
const note = (text) => h('p', { class: 'muted tiny', text });

/** A fold that stays open (or closed) while the sheet repaints. */
function advanced(key, label, hint, ...kids) {
  const d = h('details', { class: 'adv' }, h('summary', null, label, hint ? h('span', { class: 'muted', text: hint }) : null), h('div', { class: 'adv-body' }, ...kids));
  d.open = openFolds.has(key);
  d.addEventListener('toggle', () => { d.open ? openFolds.add(key) : openFolds.delete(key); });
  return d;
}

/** Buttons where exactly one is chosen. It updates itself, so the sheet keeps its scroll position. */
function segment(label, options, current, onPick, cls = 'seg') {
  const row = h('div', { class: cls, role: 'group', 'aria-label': label });
  for (const [value, text, disabled, title] of options) {
    const b = h('button', { type: 'button', text, 'aria-pressed': String(value === current), disabled: disabled || null, title: title || null });
    b.addEventListener('click', () => { for (const x of row.children) x.setAttribute('aria-pressed', String(x === b)); onPick(value); });
    row.append(b);
  }
  return row;
}

function toggle(id, label, checked, onChange, hint) {
  const cb = h('input', { type: 'checkbox', id, checked: checked || null });
  cb.addEventListener('change', () => onChange(cb.checked));
  return h('div', null, h('label', { class: 'switch', for: id }, cb, label), hint ? note(hint) : null);
}

function slider(label, min, max, val, onInput, { unit = '', auto = 'Auto' } = {}) {
  const out = h('b', { text: val == null ? auto : val + unit });
  const input = h('input', { type: 'range', min, max, step: 1, value: val ?? min, 'aria-label': label });
  input.addEventListener('input', () => { out.textContent = input.value + unit; onInput(+input.value); });
  return h('div', { class: 'range-row' }, h('span', { class: 'small', text: label }), out, input);
}

export function buildSettings(boot, S, { onChange, focus, prefs, actions = {} }) {
  const root = h('div', { class: 'settings-layout' });
  const rail = h('div', { class: 'tab-rail', role: 'tablist', 'aria-label': 'Settings groups', 'aria-orientation': 'vertical' });
  const pane = h('div', { class: 'tab-pane', role: 'tabpanel' });
  root.append(rail, pane);
  const mode = () => currentMode(boot, S);
  const rules = boot.plans[boot.user.plan]?.rules || {};
  const set = (patch) => { Object.assign(S, patch); onChange(); paint(); };
  const quiet = (patch) => { Object.assign(S, patch); onChange(); paintRail(); };   // saves without redrawing the page
  const team = buildTeamSettings(boot, S, { onChange: () => { onChange(); paintRail(); }, brainSelect });
  if (focus && FOCUS_TAB[focus]) activeTab = FOCUS_TAB[focus];
  const P = () => prefs.get();
  const look = (patch) => { prefs.set(patch); paintRail(); };

  const views = {
    // ---------------------------------------------------------------------------- Models
    models() {
      const modes = h('div', { class: 'mode-list', role: 'radiogroup', 'aria-label': 'Mode', 'data-focus': 'mode' });
      const all = [{ id: 'auto', name: 'Auto', blurb: 'I pick Fast, Normal or Deep for each message', allowed: true }, ...boot.modes];
      for (const m of all) {
        modes.append(h('button', { type: 'button', class: 'mode-opt', role: 'radio', 'aria-checked': String(S.mode === m.id), 'aria-disabled': String(!m.allowed),
          onclick: () => { if (!m.allowed) return; set({ mode: m.id, brains: {}, rounds: null, tries: null, cap: null, custom_models: false }); } },
        h('div', null, h('div', { class: 't', text: m.name }), h('div', { class: 'd', text: m.blurb })), m.allowed ? null : h('span', { class: 'lock', text: '🔒 ' + (m.locked || 'Higher plan') })));
      }

      const style = segment('Answer style', [['direct', 'Direct answers'], ['teach', 'Teach me like a tutor']], S.teacher_enabled ? 'teach' : 'direct',
        (v) => set({ teacher_enabled: v === 'teach' }), 'big-choice');
      style.querySelectorAll('button').forEach((b, i) => { b.replaceChildren(h('b', { text: i ? 'Teach me like a tutor' : 'Direct answers' }), h('span', { text: i ? 'Simple words, an example and a check question' : 'The answer at your own level, nothing extra' })); });

      const lengths = boot.lengths || [{ id: 'auto', label: 'Auto' }, { id: 'short', label: 'Short' }, { id: 'medium', label: 'Normal' }, { id: 'long', label: 'Long' }];
      const length = segment('Response length', lengths.map((l) => [l.id, l.label]), S.length || 'auto', (v) => quiet({ length: v }));

      return section('Models', 'Choose how the AI works. Everything has a good default, so you can leave most of this alone.',
        block('How should I think?', modes),
        block('Answer style', style, S.teacher_enabled ? note('Teaching mode treats you as a learner. Switch back to Direct answers any time.') : note('Direct answers are the default. Teaching is only used when you turn it on.')),
        block('Answer length', h('div', { 'data-focus': 'length' }, length), note('If an answer still hits the limit, it is finished in a second pass and you are told.')),
        modelSlots(),
        advanced('models:advanced', 'Advanced', 'a model for every job, and effort', perRoleBrains(), effortBlock(), teacherModel()));
    },

    // ---------------------------------------------------------------------------- Team
    team() {
      return section('Team', 'For bigger tasks a small team can plan, research and check the work. The defaults work if you never open this.',
        team.basic,
        advanced('team:advanced', 'Advanced', 'planners, specialists, limits, profiles', team.advanced));
    },

    // ---------------------------------------------------------------------------- Tools and skills
    tools() {
      const toolBox = h('div');
      for (const t of boot.tools) {
        toolBox.append(toggle(`tool-${t.id}`, t.label, S.tools.includes(t.id), (on) => quiet({ tools: on ? [...new Set([...S.tools, t.id])] : S.tools.filter((x) => x !== t.id) })));
      }
      const skillBox = h('div');
      const active = S.skills ?? boot.skills.map((x) => x.name);
      for (const sk of boot.skills) {
        const cb = h('input', { type: 'checkbox', id: `sk-${sk.name}`, checked: active.includes(sk.name) || null });
        cb.addEventListener('change', () => { const cur = new Set(S.skills ?? boot.skills.map((x) => x.name)); cb.checked ? cur.add(sk.name) : cur.delete(sk.name); quiet({ skills: [...cur] }); });
        skillBox.append(h('label', { class: 'switch', for: `sk-${sk.name}`, title: sk.description }, cb, h('span', null, h('b', { text: sk.name }), ' ', h('span', { class: 'muted small', text: sk.description.split('. ')[0] }))));
      }
      const imgModels = boot.image_models || [];
      const imgSel = h('select', { class: 'select', 'aria-label': 'Image model' },
        h('option', { value: '', text: imgModels.length ? 'Not chosen: I will ask before drawing' : 'No image model approved yet' }),
        imgModels.map((m) => h('option', { value: m.id, text: `${m.name} (${m.lab}) · $${Number(m.price_out).toFixed(2)} per 1M out` })));
      imgSel.value = S.image_model || boot.image_model || '';
      imgSel.addEventListener('change', async () => {
        S.image_model = imgSel.value || null; onChange();
        try { await fetch('/api/settings', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ image_model: imgSel.value || null }) }); } catch { /* saved on the next message anyway */ }
      });
      const allOn = () => set({ tools: boot.tools.map((t) => t.id) });
      const allOff = () => set({ tools: [] });
      return section('Tools and skills', 'Tools let the AI make charts, documents, pictures and searches. Switch off anything you do not want it to use.',
        block('Tools for this chat', toolBox, h('div', { class: 'pane-actions' }, h('button', { type: 'button', class: 'btn small', text: 'All on', onclick: allOn }), h('button', { type: 'button', class: 'btn small', text: 'All off', onclick: allOff }))),
        block('Picture model', imgSel, note('Generated pictures cost real money per image, so nothing is drawn until you pick a model. Turn on "Generated images" above to let the AI ask for one.')),
        advanced('tools:skills', 'Skills', `${(S.skills ?? boot.skills).length} of ${boot.skills.length} on`, note('Skills are recipe cards the AI opens only when a task needs them.'), skillBox));
    },

    // ---------------------------------------------------------------------------- Files
    files() {
      const days = rules.retention_days, mb = rules.storage_mb;
      return section('Files', 'The AI saves documents, decks and pictures in your own private workspace.',
        block('Workspace',
          toggle('sw-ws-auto', 'Open the workspace when a file is made', P().workspace_auto, (on) => look({ workspace_auto: on })),
          note(`Your plan keeps up to ${mb >= 1000 ? `${mb / 1000} GB` : `${mb} MB`} of files${days ? ` for ${days} days` : ''}. Open the workspace to see what is left.`),
          h('div', { class: 'pane-actions' }, h('button', { type: 'button', class: 'btn', text: '📁 Open my files', onclick: () => actions.openFiles?.() }))),
        advanced('files:advanced', 'Advanced', 'clean up', h('p', { class: 'muted small', text: 'Deleting removes files from the disk and the database together. It cannot be undone.' }),
          h('div', { class: 'pane-actions' }, h('button', { type: 'button', class: 'btn danger', text: 'Delete all my files', onclick: () => actions.deleteFiles?.() }))));
    },

    // ---------------------------------------------------------------------------- Credits
    credits() {
      const m = mode();
      const capMax = m ? m.max_credits : 160;
      const cap = slider('Most credits one message may use', 1, capMax, S.cap ?? Math.min(capMax, Math.max(boot.user.auto_spend, 1)), (v) => quiet({ cap: v }));
      const ask = slider('Ask me first when a message may cost more than', 1, 200, boot.user.auto_spend, (v) => { boot.user.auto_spend = v; clearTimeout(ask._t); ask._t = setTimeout(() => actions.saveAutoSpend?.(v), 400); }, { unit: ' credits' });
      return section('Credits', 'What a message may cost. A run stops at the limit and keeps the best answer so far; unused credits come back.',
        block('Limit for each message', cap, h('div', { class: 'pane-actions' }, h('button', { type: 'button', class: 'btn small', text: 'Use the default', onclick: () => set({ cap: null }) })),
          toggle('sw-estimate', 'Show the cost estimate before I send', P().show_estimate, (on) => look({ show_estimate: on }))),
        block('Your credits', h('p', { class: 'small', text: `You have ${(actions.balance?.() ?? 0).toLocaleString('en')} credits on the ${boot.user.plan} plan.` }),
          h('div', { class: 'pane-actions' }, h('button', { type: 'button', class: 'btn primary', text: '💳 Plans and credits', onclick: () => actions.showPlans?.() }))),
        advanced('credits:advanced', 'Advanced', 'when to ask first', ask, note('Bigger jobs show their plan and cost and wait for your OK. Raise this number to be asked less often.')));
    },

    // ---------------------------------------------------------------------------- Privacy
    privacy() {
      return section('Privacy', 'You decide what is remembered and where your messages are sent.',
        block('Where your messages go', toggle('sw-priv', 'Private route: only hosts that do not keep or train on prompts', S.private, (on) => quiet({ private: on }),
          'Web search sits outside this setting. Private routes may cost more or have fewer models.')),
        block('What I remember about you',
          h('p', { class: 'small muted', text: 'A small profile and some notes help me pick the right level and examples. You can read, edit or delete all of it.' }),
          h('div', { class: 'pane-actions' },
            h('button', { type: 'button', class: 'btn', text: '🧠 See and edit my memory', onclick: () => actions.showMemory?.() }),
            h('button', { type: 'button', class: 'btn', text: '📊 My activity', onclick: () => actions.showActivity?.() }))));
    },

    // ---------------------------------------------------------------------------- Look and layout
    look() {
      const p = P();
      const looks = h('div', { class: 'looks' }, LOOKS.map((l) => h('button', { type: 'button', class: 'look-card', onclick: () => { prefs.look(l.id); paint(); } },
        h('div', { class: 'mini', 'aria-hidden': 'true' }, ...(THEMES.find((t) => t.id === l.set.theme)?.sw || ['#f6f7f4', '#182019']).map((c) => h('i', { style: `background:${c}` })), h('i', { style: `background:${ACCENTS[l.set.accent] || ACCENTS.teal}` })),
        h('b', { text: l.name }), h('span', { text: l.blurb }))));

      const themes = h('div', { class: 'theme-grid', role: 'group', 'aria-label': 'Theme' });
      for (const t of THEMES) {
        const b = h('button', { type: 'button', class: 'theme-opt', 'aria-pressed': String(p.theme === t.id), onclick: () => { look({ theme: t.id }); for (const x of themes.children) x.setAttribute('aria-pressed', String(x === b)); } },
          h('div', { class: 'sw', 'aria-hidden': 'true' }, h('i', { style: `background:${t.sw[0]}` }), h('i', { style: `background:${t.sw[1]}` })), h('span', { text: t.label }));
        themes.append(b);
      }

      const swatches = h('div', { class: 'swatches', role: 'group', 'aria-label': 'Accent color' });
      const custom = h('input', { type: 'color', 'aria-label': 'Pick any color', value: /^#/.test(p.accent) ? p.accent : ACCENTS[p.accent] || ACCENTS.teal });
      const mark = () => { for (const b of swatches.querySelectorAll('.swatch')) b.setAttribute('aria-pressed', String(b.dataset.k === P().accent)); };
      for (const [k, c] of Object.entries(ACCENTS)) swatches.append(h('button', { type: 'button', class: 'swatch', 'data-k': k, style: `background:${c}`, 'aria-label': k, 'aria-pressed': String(p.accent === k), onclick: () => { look({ accent: k }); custom.value = c; mark(); } }));
      custom.addEventListener('input', () => { look({ accent: custom.value }); mark(); });
      swatches.append(custom);

      const size = slider('Text size', 85, 140, p.size, (v) => look({ size: v }), { unit: '%' });

      const chipPick = h('div', { class: 'chip-pick', role: 'group', 'aria-label': 'Buttons above the message box' });
      for (const [id, label] of Object.entries(CHIP_LABELS)) {
        const cb = h('input', { type: 'checkbox', checked: P().chips.includes(id) || null, 'aria-label': `Show ${label}` });
        cb.addEventListener('change', () => { const cur = P().chips.filter((c) => c !== id); look({ chips: cb.checked ? Object.keys(CHIP_LABELS).filter((c) => cur.includes(c) || c === id) : cur }); });
        chipPick.append(h('label', null, cb, label));
      }
      const sidePick = h('div', { class: 'chip-pick', role: 'group', 'aria-label': 'Sidebar shortcuts' });
      for (const [id, label] of Object.entries(SIDE_LABELS)) {
        const cb = h('input', { type: 'checkbox', checked: P().side_items.includes(id) || null, 'aria-label': `Show ${label.replace(/^\S+ /, '')}` });
        cb.addEventListener('change', () => { const cur = P().side_items.filter((c) => c !== id); look({ side_items: cb.checked ? Object.keys(SIDE_LABELS).filter((c) => cur.includes(c) || c === id) : cur }); });
        sidePick.append(h('label', null, cb, label));
      }

      const row = (label, el) => h('div', { class: 'sec-row' }, h('div', { class: 'small', text: label }), el);
      const pick = (label, key, opts) => row(label, segment(label, opts, P()[key], (v) => look({ [key]: v })));
      return section('Look and layout', 'Make the screen yours. Every change shows at once and is saved to your account, so it follows you to any device.',
        block('Start from a look', looks, note('A look only changes colors, size and spacing. It never changes what the AI does.')),
        block('Theme', themes),
        block('Accent color', swatches, P().theme === 'contrast' ? note('High contrast uses its own colors.') : null),
        block('Size', size),
        advanced('look:more', 'More ways to customize', 'font, width, buttons, behavior',
          pick('Font', 'font', FONTS),
          pick('Spacing', 'density', [['compact', 'Tight'], ['cozy', 'Comfortable'], ['spacious', 'Roomy']]),
          pick('Chat width', 'width', [['narrow', 'Narrow'], ['normal', 'Normal'], ['wide', 'Wide'], ['full', 'Full']]),
          pick('Corners', 'round', [['sharp', 'Square'], ['normal', 'Soft'], ['round', 'Round']]),
          pick('Motion', 'anim', [['on', 'Full'], ['reduced', 'Calm'], ['off', 'None']]),
          row('Buttons above the message box', chipPick),
          row('Sidebar shortcuts', sidePick),
          pick('Steps panel while the AI works', 'steps_open', [['running', 'Open while running'], ['always', 'Always open'], ['never', 'Always closed']]),
          toggle('sw-timing', 'Show time and token details for every AI call', p.timing, (on) => look({ timing: on })),
          toggle('sw-thinking', 'Show thinking summaries', p.thinking, (on) => look({ thinking: on })),
          toggle('sw-fold', 'Fold very long answers, with Show more', p.fold_long, (on) => look({ fold_long: on })),
          toggle('sw-enter', 'Press Enter to send (off: Ctrl or Cmd + Enter)', p.send_on_enter, (on) => look({ send_on_enter: on }))),
        h('div', { class: 'pane-actions' }, h('button', { type: 'button', class: 'btn small', text: 'Reset the look', onclick: () => { prefs.reset(); paint(); } })));
    },
  };

  // ---- pieces of the Models group --------------------------------------------------------------------
  function modelSlots() {
    // Plan: 3 optional model slots (understanding, prompt enhancer, main). Defaults are good, so the switch starts on.
    const m = mode() || { slots: { answer: 'tier:smart', worker: 'tier:smart' } };
    const mains = MAIN_ROLES.filter((r) => r in m.slots && !Array.isArray(m.slots[r]));
    const mainNow = mains.map((r) => S.brains[r]).find(Boolean) || S.team?.builder?.model || '';
    const custom = S.custom_models || !!(S.team?.understand?.model || S.team?.enhancer?.model || mainNow);
    const teamPatch = (key, patch) => { S.team = { ...S.team, [key]: { ...(S.team?.[key] || {}), ...patch } }; };
    const defaults = toggle('sw-model-defaults', 'Use the default models (recommended)', !custom, (on) => {
      if (on) {
        const b = { ...S.brains }; mains.forEach((r) => delete b[r]);
        const t = { ...S.team };
        for (const k of ['understand', 'enhancer', 'builder', 'finisher']) if (t[k]) t[k] = { ...t[k], model: null };
        set({ brains: b, team: t, custom_models: false });
      } else set({ custom_models: true });
    });
    const body = h('div', { class: 'brain-rows' });
    if (custom) {
      body.append(
        h('div', { class: 'role-row' }, h('span', { class: 'small', text: 'Understanding' }), brainSelect(boot, S.team?.understand?.model, (v) => { teamPatch('understand', { model: v || null }); onChange(); }, { label: 'Understanding model', auto: 'Default (fast and cheap)' })),
        h('div', { class: 'role-row' }, h('span', { class: 'small', text: 'Prompt enhancer' }), brainSelect(boot, S.team?.enhancer?.model, (v) => { teamPatch('enhancer', { model: v || null }); onChange(); }, { label: 'Prompt enhancer model', auto: 'Default (fast and cheap)' })),
        h('div', { class: 'role-row' }, h('span', { class: 'small', text: 'Main model' }), brainSelect(boot, mainNow, (v) => {
          const b = { ...S.brains }; mains.forEach((r) => { if (v) b[r] = v; else delete b[r]; });
          teamPatch('builder', { model: v || null }); teamPatch('finisher', { model: v || null }); S.brains = b; onChange();
        }, { label: 'Main model', auto: 'Default for this mode' })),
        note('Understanding reads the request. The enhancer writes a clearer prompt. The main model does the work. Same model for the first two means one call, not two.'));
    }
    return block('Which models', defaults, body);
  }

  function perRoleBrains() {
    const m = mode() || { name: 'Auto', slots: { answer: 'tier:smart', worker: 'tier:smart' }, params: {}, auto: true };
    const quick = segment('Quick pick', [['auto', 'Auto'], ['cheapest', 'Cheapest'], ['balanced', 'Balanced'], ['strongest', 'Strongest']], '', (id) => set({ brains: strategyBrains(boot, m, id) }));
    quick.querySelectorAll('button').forEach((b) => b.setAttribute('aria-pressed', 'false'));
    const rows = h('div', { class: 'brain-rows' });
    for (const [role, slot] of Object.entries(m.slots)) {
      const label = m.auto ? (role === 'answer' ? 'Answering brain' : 'Working brain (bigger tasks)') : (boot.roles[role] || role);
      if (Array.isArray(slot)) {
        const min = m.params.min_members || m.params.min_thinkers || 2, max = m.params.max_members || m.params.max_thinkers || 5;
        const cur = Array.isArray(S.brains[role]) ? S.brains[role] : slot.map(() => '');
        const wrap = h('div', { class: 'brain-group' }, h('div', { class: 'small b', text: label }));
        cur.forEach((v, k) => wrap.append(h('div', { class: 'role-row' }, h('span', { class: 'small', text: `${label} ${k + 1}` }),
          brainSelect(boot, v, (val) => { const next = [...cur]; next[k] = val; const b = { ...S.brains }; if (next.every(Boolean)) b[role] = next; else delete b[role]; S.brains = b; onChange(); }, { label: `${label} ${k + 1}` }))));
        wrap.append(h('div', { class: 'btn-row' },
          h('button', { type: 'button', class: 'btn small', text: '＋ Add', disabled: cur.length >= max, onclick: () => set({ brains: { ...S.brains, [role]: [...cur, ''] } }) }),
          h('button', { type: 'button', class: 'btn small', text: '− Remove', disabled: cur.length <= min, onclick: () => set({ brains: { ...S.brains, [role]: cur.slice(0, -1) } }) })));
        if (cur.some((x) => !x)) wrap.append(note('Fill every slot to use your own group, or leave all on Auto.'));
        rows.append(wrap);
      } else rows.append(h('div', { class: 'role-row' }, h('span', { class: 'small', text: label }),
        brainSelect(boot, S.brains[role], (val) => { const b = { ...S.brains }; if (val) b[role] = val; else delete b[role]; S.brains = b; onChange(); }, { label })));
    }
    return block(m.auto ? 'A model for each job (Auto)' : `A model for each job (${m.name})`, block('Quick pick for every job', quick), rows,
      note('🇨🇳 or 🌐 shows which lab runs it. "Thinks" means it can use scrap paper before answering.'));
  }

  function effortBlock() {
    const m = mode();
    const sliders = h('div', { class: 'brain-rows' });
    if (m?.params.max_rounds) sliders.append(slider('Rounds of rewriting', 1, Math.min(m.params.max_rounds, rules.max_rounds || 5), S.rounds ?? Math.min(m.params.default_rounds, rules.max_rounds || 5), (v) => quiet({ rounds: v })));
    if (m?.params.max_tries) sliders.append(slider('Long-thinking tries', 1, Math.min(m.params.max_tries, rules.max_tries || 5), S.tries ?? Math.min(m.params.default_tries, rules.max_tries || 5), (v) => quiet({ tries: v })));
    const seg = segment('Effort', boot.efforts.map((e) => [e.id, e.label, !e.allowed, e.allowed ? '' : 'Needs a higher plan']), S.effort, (v) => quiet({ effort: v }));
    return block('Thinking effort', note('How much scrap paper the AI may use before answering. More effort costs more.'), seg, sliders);
  }

  function teacherModel() {
    if (!S.teacher_enabled) return null;
    return block('Teacher model (optional)', brainSelect(boot, S.teacher_model, (v) => quiet({ teacher_model: v || null }), { label: 'Teacher model' }),
      note('Leave on Auto to apply the teaching style inside the same answer. Choosing a model adds a separate explanation pass, which costs extra and shows in the estimate.'));
  }

  // ---- rail ---------------------------------------------------------------------------------------------
  function summary(id) {
    if (id === 'models') { const c = Object.keys(S.brains).length || S.custom_models ? 'custom' : 'default models'; return `${modeName(boot, S)} · ${c}`; }
    if (id === 'team') return teamName(S.team);
    if (id === 'tools') return `${S.tools.length} on`;
    if (id === 'files') return P().workspace_auto ? 'Opens by itself' : 'Opens when I ask';
    if (id === 'credits') return S.cap ? `Up to ${S.cap} each` : 'Default limit';
    if (id === 'privacy') return S.private ? 'Private route' : 'Standard route';
    if (id === 'look') return THEMES.find((t) => t.id === P().theme)?.label || '';
    return '';
  }
  function paintRail() {
    rail.replaceChildren(...TABS.map((t) => h('button', { type: 'button', role: 'tab', class: 'tab-btn', 'aria-selected': String(t.id === activeTab), id: `tab-${t.id}-btn`, title: t.hint,
      onclick: () => { activeTab = t.id; paint(); pane.scrollTop = 0; } },
    h('span', { class: 'tab-ico', 'aria-hidden': 'true', text: t.icon }), h('span', { class: 'tab-txt' }, h('b', { text: t.label }), h('span', { class: 'tab-sum', text: summary(t.id) })))));
  }
  function paint() {
    const top = pane.scrollTop;
    paintRail();
    pane.setAttribute('aria-labelledby', `tab-${activeTab}-btn`);
    pane.replaceChildren(views[activeTab]());
    pane.scrollTop = top;
  }
  paint();
  if (focus) pane.querySelector(`[data-focus="${focus}"]`)?.scrollIntoView({ block: 'start' });
  return root;
}
