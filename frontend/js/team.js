// Team profiles are browser preferences. The server validates every model, limit and permission.
import { h, safeStore } from './dom.js';

export const TEAM_PRESETS = {
  fast: { name: 'Fast', preset: 'fast', plan_mode: 'off', plan_depth: 'light', understand: { enabled: false }, planners: { count: 0 }, researchers: { count: 0 }, architects: [] },
  balanced: { name: 'Balanced', preset: 'balanced', plan_mode: 'auto', plan_depth: 'normal', planners: { count: 1 }, researchers: { count: 1, engine: 'auto', max_searches_each: 2 }, architects: [] },
  full: { name: 'Full team', preset: 'full', plan_mode: 'auto', plan_depth: 'deep', planners: { count: 3 }, researchers: { count: 3, engine: 'auto', max_searches_each: 2 }, architects: ['ui', 'data', 'document', 'code'] },
};
const clone = (v) => JSON.parse(JSON.stringify(v));
export const teamName = (team = {}) => team.name || TEAM_PRESETS[team.preset]?.name || 'Balanced';

export function sanitizeTeam(team, boot) {
  if (!team || typeof team !== 'object' || Array.isArray(team)) return {};
  const next = clone(team), allowed = new Set(boot.models.filter((m) => m.allowed).map((m) => m.id));
  const clean = (role) => {
    if (!role || typeof role !== 'object') return;
    if (role.model && !allowed.has(role.model)) delete role.model;
    if (Array.isArray(role.models)) role.models = role.models.map((m) => allowed.has(m) ? m : '');
    if (Array.isArray(role.agents)) role.agents.forEach(clean);
    if (role.effort && !boot.efforts.some((e) => e.id === role.effort && e.allowed)) role.effort = 'auto';
  };
  ['understand', 'plan_judge', 'planners', 'researchers', 'builder', 'checker', 'finisher'].forEach((key) => clean(next[key]));
  Object.values(next.architect_settings || {}).forEach(clean);
  return next;
}

export function buildTeamSettings(boot, S, { onChange, brainSelect }) {
  const store = safeStore(), profileKey = `sh.team.profiles.${boot.user.id}`;
  const profiles = store.get(profileKey, {});
  const planning = h('div', { class: 'team-settings', id: 'tab-planning' }), research = h('div', { class: 'team-settings', id: 'tab-research' }), build = h('div', { class: 'team-settings', id: 'tab-build' });
  const roots = [planning, research, build], inside = (el) => roots.some((r) => r.contains(el));
  const update = (mutate, repaint = false) => {
    S.team = clone(S.team || {}); mutate(S.team); onChange(); if (repaint) render();
  };
  const field = (label, control) => h('label', { class: 'team-field' }, h('span', { class: 'small', text: label }), control);
  const select = (label, options, value, pick) => {
    const el = h('select', { class: 'select', 'aria-label': label }, options.map(([v, t]) => h('option', { value: v, text: t })));
    el.value = String(value); el.addEventListener('change', () => pick(el.value)); return el;
  };
  const number = (label, value, min, max, pick, placeholder = 'Auto') => {
    const el = h('input', { class: 'input', type: 'number', min, max, step: 1, value: value ?? '', placeholder, 'aria-label': label });
    el.addEventListener('change', () => {
      if (!el.value) { pick(null); return; }
      const n = Math.max(min, Math.min(max, Math.round(Number(el.value) || min))); el.value = n; pick(n);
    }); return el;
  };
  const toggle = (label, checked, change) => {
    const cb = h('input', { type: 'checkbox', checked: checked || null, 'aria-label': label });
    cb.addEventListener('change', () => change(cb.checked)); return h('label', { class: 'switch' }, cb, label);
  };
  const effort = (label, value, pick, inherit = false) => {
    const el = h('select', { class: 'select', 'aria-label': label }, inherit ? h('option', { value: '', text: 'Group default' }) : null,
      boot.efforts.map((e) => h('option', { value: e.id, text: e.label, disabled: !e.allowed })));
    el.value = value || (inherit ? '' : 'auto'); el.addEventListener('change', () => pick(el.value)); return el;
  };
  function roleCard(key, title, role = {}, { multiple = false, count = 1, architect = false } = {}) {
    const patch = (p) => update((team) => {
      if (architect) { team.architect_settings ||= {}; team.architect_settings[key] = { ...team.architect_settings[key], ...p }; }
      else team[key] = { ...team[key], ...p };
    });
    const card = h('details', { class: 'team-agent' }, h('summary', { text: title }));
    const controls = h('div', { class: 'team-agent-controls' });
    if (!architect && !multiple) controls.append(toggle(`Enable ${title.toLowerCase()}`, role.enabled !== false, (enabled) => patch({ enabled })));
    for (let i = 0; i < (multiple ? count : 1); i++) {
      const label = multiple ? `${title} ${i + 1} model` : `${title} model`;
      controls.append(field(label, brainSelect(boot, multiple ? role.agents?.[i]?.model || role.models?.[i] : role.model, (model) => {
        if (multiple) update((team) => {
          const group = team[key] || {}, models = [...(group.models || role.models || [])]; models[i] = model;
          const agents = group.agents?.map((a) => ({ ...(a || {}) }));
          if (agents?.[i]?.model !== undefined) agents[i].model = model || null;
          team[key] = { ...group, models, ...(agents ? { agents } : {}) };
        });
        else patch({ model: model || null });
      }, { label })));
      if (multiple) {
        const instance = role.agents?.[i] || {};
        const labelBase = `${title} ${i + 1}`;
        const perAgent = (p) => update((team) => {
          const group = team[key] || {};
          const agents = Array.from({ length: Math.max(count, group.agents?.length || 0) }, (_, n) => ({ ...(group.agents?.[n] || {}) }));
          for (const [key, value] of Object.entries(p)) { if (value === undefined) delete agents[i][key]; else agents[i][key] = value; }
          team[key] = { ...group, agents };
        });
        controls.append(h('details', { class: 'team-instance' }, h('summary', { class: 'small', text: `${labelBase} limits and effort` }),
          toggle(`Enable ${labelBase.toLowerCase()}`, instance.enabled !== false, (v) => perAgent({ enabled: v })),
          h('div', { class: 'team-grid' },
            field(`${labelBase} effort`, effort(`${labelBase} effort`, instance.effort, (v) => perAgent({ effort: v || undefined }), true)),
            field(`${labelBase} credit cap`, number(`${labelBase} credit cap`, instance.max_credits, 1, 2000, (v) => perAgent({ max_credits: v ?? undefined }), 'Group default')),
            field(`${labelBase} time limit (seconds)`, number(`${labelBase} time limit`, instance.timeout_s, 1, 180, (v) => perAgent({ timeout_s: v ?? undefined }), 'Group default')),
            ...(key === 'researchers' ? [
              field(`${labelBase} search engine`, select(`${labelBase} search engine`, [['', 'Group default'], ['auto', 'Auto'], ['native', 'Native'], ['exa', 'Exa'], ['parallel', 'Parallel'], ['perplexity', 'Perplexity']], instance.engine || '', (v) => perAgent({ engine: v || undefined }))),
              field(`${labelBase} search limit`, number(`${labelBase} search limit`, instance.max_searches_each, 1, 10, (v) => perAgent({ max_searches_each: v ?? undefined }), 'Group default')),
            ] : []))));
      }
    }
    const defaultEffort = ['builder', 'finisher'].includes(key) ? 'auto' : multiple || architect ? 'low' : 'off';
    controls.append(h('div', { class: 'team-grid' },
      field(`${title} effort`, effort(`${title} effort`, role.effort || defaultEffort, (v) => patch({ effort: v }))),
      field(`${title} credit cap`, number(`${title} credit cap`, role.max_credits, 1, 2000, (v) => patch({ max_credits: v }))),
      field(`${title} time limit (seconds)`, number(`${title} time limit`, role.timeout_s, 1, 180, (v) => patch({ timeout_s: v ?? 60 }), '60'))));
    card.append(controls); return card;
  }
  function render() {
    const focused = inside(document.activeElement) ? document.activeElement?.getAttribute('aria-label') : null;
    const expanded = new Set(roots.flatMap((r) => [...r.querySelectorAll('details[open] > summary')].map((s) => s.textContent)));
    const team = S.team || {}, preset = TEAM_PRESETS[team.preset] || TEAM_PRESETS.balanced;
    const planners = team.planners || preset.planners, researchers = team.researchers || preset.researchers;
    const pc = planners.enabled === false ? 0 : (planners.count ?? preset.planners.count);
    const rc = researchers.enabled === false ? 0 : (researchers.count ?? preset.researchers.count);
    const architects = team.architects || preset.architects;
    const presets = h('div', { class: 'seg', role: 'group', 'aria-label': 'Team preset' }, Object.entries(TEAM_PRESETS).map(([id, p]) => h('button', {
      type: 'button', text: p.name, 'aria-pressed': String((team.preset || 'balanced') === id),
      onclick: () => { S.team = clone(p); onChange(); render(); },
    })));
    const profileSelect = select('Saved team profile', [['', 'Choose a saved profile'], ...Object.keys(profiles).map((name) => [name, name])], '', (name) => {
      if (!profiles[name]) return;
      S.team = sanitizeTeam(profiles[name].team || {}, boot); S.teacher_enabled = profiles[name].teacher_enabled !== false;
      S.teacher_model = boot.models.some((m) => m.allowed && m.id === profiles[name].teacher_model) ? profiles[name].teacher_model : null; onChange(); render();
    });
    const profileName = h('input', { class: 'input', 'aria-label': 'Team profile name', placeholder: 'My research team', maxLength: 60, value: team.name || '' });
    const save = h('button', { type: 'button', class: 'btn small', text: 'Save profile', onclick: () => {
      const name = profileName.value.trim().slice(0, 60); if (!name) { profileName.focus(); return; }
      S.team = { ...S.team, name }; profiles[name] = clone({ team: S.team, teacher_enabled: S.teacher_enabled, teacher_model: S.teacher_model });
      store.set(profileKey, profiles); onChange(); render();
    } });
    planning.replaceChildren(
      h('p', { class: 'tab-intro', text: 'For bigger tasks the team can write a plan first, so the answer is built step by step. Pick a ready-made team, then adjust.' }),
      h('div', { class: 'team-block' }, h('b', { class: 'small', text: 'Ready-made team' }), presets,
        h('p', { class: 'muted small', text: 'Fast skips planning. Balanced uses one planner for bigger tasks. Full team compares three plans and adds specialists.' })),
      h('div', { class: 'team-block' }, h('b', { class: 'small', text: 'How planning works' }), h('div', { class: 'team-grid' },
        field('Plan mode', select('Plan mode', [['off', 'Off: just answer'], ['auto', 'Auto: plan bigger tasks'], ['ask', 'Ask me: I approve the plan']], team.plan_mode || preset.plan_mode, (v) => update((t) => { t.plan_mode = v; }))),
        field('Planning depth', select('Planning depth', [['light', 'Light: one plan'], ['normal', 'Normal: revise if it fails'], ['deep', 'Deep: review every step']], team.plan_depth || preset.plan_depth, (v) => update((t) => { t.plan_depth = v; }))),
        field('Planners (more = more ideas)', number('Number of planners', pc, 0, 3, (v) => update((t) => { t.planners = { ...planners, ...t.planners, count: v ?? 0, enabled: (v ?? 0) > 0 }; }, true))))),
      h('div', { class: 'team-block' }, h('b', { class: 'small', text: 'Specialists (optional)' }),
        h('div', { class: 'team-architects' }, ...[['ui', 'UI designer'], ['data', 'Data expert'], ['document', 'Slides and documents'], ['code', 'Code expert']].map(([id, label]) => toggle(label.replace(' expert', '').replace(' designer', '').replace('Slides and documents', 'Slides / document') + ' architect', architects.includes(id), (enabled) => update((t) => { t.architects = enabled ? [...new Set([...architects, id])] : architects.filter((a) => a !== id); }, true))))),
      h('div', { class: 'team-block' }, h('b', { class: 'small', text: 'Who does each planning job (brain, effort, limits)' }), h('div', { class: 'team-roles' },
        roleCard('understand', 'Understand and enhance', team.understand),
        roleCard('enhancer', 'Prompt enhancer', team.enhancer),
        ...(pc ? [roleCard('planners', 'Planner', planners, { multiple: true, count: pc })] : []),
        ...(pc > 1 ? [roleCard('plan_judge', 'Plan judge', team.plan_judge)] : []),
        ...architects.map((id) => roleCard(id, `${id === 'document' ? 'Document' : id[0].toUpperCase() + id.slice(1)} architect`, team.architect_settings?.[id], { architect: true })))),
      h('div', { class: 'team-block team-profiles' }, h('b', { class: 'small', text: 'Save this team for later' }), profileSelect,
        h('div', { class: 'team-profile-save' }, profileName, save), h('p', { class: 'muted tiny', text: 'Saved in this browser. Your team and teacher choices are remembered separately for each chat.' })));
    research.replaceChildren(
      h('p', { class: 'tab-intro', text: 'Researchers search the web at the same time and bring back sources, so the answer can use fresh facts and links.' }),
      h('div', { class: 'team-block' }, h('div', { class: 'team-grid' },
        field('Researchers (0 = no web research)', number('Number of researchers', rc, 0, 5, (v) => update((t) => { t.researchers = { ...researchers, ...t.researchers, count: v ?? 0, enabled: (v ?? 0) > 0 }; }, true))),
        field('Search engine', select('Research engine', [['auto', 'Auto'], ['exa', 'Exa'], ['parallel', 'Parallel'], ['perplexity', 'Perplexity']], researchers.engine || 'auto', (v) => update((t) => { t.researchers = { ...researchers, ...t.researchers, engine: v }; }))),
        field('Searches per researcher', number('Searches per researcher', researchers.max_searches_each ?? 2, 1, 10, (v) => update((t) => { t.researchers = { ...researchers, ...t.researchers, max_searches_each: v ?? 2 }; }))))),
      rc ? h('div', { class: 'team-block' }, h('b', { class: 'small', text: 'Who researches (brain, effort, limits)' }), h('div', { class: 'team-roles' }, roleCard('researchers', 'Researcher', researchers, { multiple: true, count: rc })))
        : h('p', { class: 'muted small', text: 'Research is off. Set the number of researchers above 0 to turn it on.' }));
    build.replaceChildren(
      h('p', { class: 'tab-intro', text: 'After planning and research, a builder writes the work, a checker reviews it, and a finisher polishes it.' }),
      h('div', { class: 'team-block' }, h('div', { class: 'team-grid' },
        field('Most credits the whole team may use', number('Team credit cap', team.max_credits, 1, 2000, (v) => update((t) => { t.max_credits = v; }))))),
      h('div', { class: 'team-block' }, h('b', { class: 'small', text: 'Builder, checker and finisher' }), h('div', { class: 'team-roles' },
        roleCard('builder', 'Builder', team.builder), roleCard('checker', 'Checker', team.checker), roleCard('finisher', 'Finisher', team.finisher))),
      h('div', { class: 'team-block' }, h('b', { class: 'small', text: 'Critical thinking sub-agents & Recursive self-improve' }), h('div', { class: 'team-grid' },
        field('Critical thinking (5 sub-agents)', select('Critical thinking', [['off', 'Off'], ['auto', 'Auto: math, facts & code'], ['always', 'Always: all 5 critics']], team.critics?.mode || 'off', (v) => update((t) => { t.critics = { ...(t.critics || {}), mode: v }; }))),
        field('Self-improve (Section 18 Harness²)', select('Self-improve', [['off', 'Off: plain harness'], ['learned', 'Learned: apply EXPERIENCE.md'], ['recursive', 'Recursive: Propose, Probe, Compose']], team.self_improve?.mode || 'off', (v) => update((t) => { t.self_improve = { ...(t.self_improve || { k: 1 }), mode: v }; }))),
        field('Architecture agent (D3 diagram)', select('Architecture agent', [['off', 'Off'], ['auto', 'Auto: when design requested'], ['on', 'Always draw D3 diagram']], team.architecture_agent || 'off', (v) => update((t) => { t.architecture_agent = v; }))))),
      h('div', { class: 'team-block team-teacher' }, h('b', { class: 'small', text: 'Teaching mode' }),
        h('p', { class: 'muted small', text: 'Off (default): you get a direct answer at your own level, with no lesson, analogy or check question. On: the answer is explained like a tutor would, for a beginner.' }),
        toggle('Explain answers like a tutor (treat me as a learner)', S.teacher_enabled === true, (enabled) => { S.teacher_enabled = enabled; onChange(); render(); }),
        S.teacher_enabled === true ? field('Teacher model (optional: a separate explaining pass)', brainSelect(boot, S.teacher_model, (model) => { S.teacher_model = model || null; onChange(); }, { label: 'Teacher model' })) : null,
        S.teacher_enabled === true ? h('p', { class: 'muted tiny', text: 'Leave the model on Auto to apply the teaching style inside the same answer. Choosing a model adds a separate explanation pass, which costs extra and shows in the estimate.' }) : null));
    for (const r of roots) for (const summary of r.querySelectorAll('details > summary')) if (expanded.has(summary.textContent)) summary.parentElement.open = true;
    if (focused) roots.flatMap((r) => [...r.querySelectorAll('[aria-label]')]).find((el) => el.getAttribute('aria-label') === focused)?.focus();
  }
  render(); return { planning, research, build };
}
