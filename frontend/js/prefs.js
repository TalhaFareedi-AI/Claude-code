// The user's look and layout. One object holds every choice; changing it repaints the page at once.
// Saved in this browser (so the page opens in the right look with no flash) and on the server (so the
// same look follows the user to a new device). The server checks every value, see backend/app/uiprefs.py.
import { $, safeStore } from './dom.js';

export const DEFAULTS = {
  theme: 'auto', accent: 'teal', size: 100, font: 'system', density: 'cozy', width: 'normal', round: 'normal', anim: 'on',
  steps_open: 'running', timing: true, thinking: true, fold_long: true, workspace_auto: true, show_estimate: true, send_on_enter: true,
  chips: ['mode', 'team', 'tools'], side_items: ['memory', 'activity', 'files'],
};

export const ACCENTS = { teal: '#2a7f6f', blue: '#2f6fd1', violet: '#7a55c9', orange: '#c4622d', rose: '#c2415d', slate: '#4b5a66' };
export const THEMES = [
  { id: 'auto', label: 'Match my device', sw: ['#f6f7f4', '#182019'] },
  { id: 'light', label: 'Light', sw: ['#f6f7f4', '#ffffff'] },
  { id: 'dark', label: 'Dark', sw: ['#101513', '#182019'] },
  { id: 'sepia', label: 'Paper', sw: ['#f4ecd8', '#fbf5e6'] },
  { id: 'midnight', label: 'Midnight', sw: ['#000000', '#0b0b0d'] },
  { id: 'contrast', label: 'High contrast', sw: ['#ffffff', '#000000'] },
];
export const FONTS = [['system', 'Clean'], ['serif', 'Book'], ['rounded', 'Friendly'], ['mono', 'Code'], ['readable', 'Easy to read']];
export const CHIP_LABELS = { mode: 'Mode', team: 'Team', tools: 'Tools', brains: 'Models', effort: 'Effort', length: 'Length' };
export const SIDE_LABELS = { memory: '🧠 Memory', activity: '📊 My activity', files: '📁 My files' };

// A look is a bundle of choices set with one tap. It only touches how things look, never what the AI does.
export const LOOKS = [
  { id: 'calm', name: 'Calm', blurb: 'The default', set: { theme: 'auto', accent: 'teal', size: 100, font: 'system', density: 'cozy', width: 'normal', round: 'normal', anim: 'on' } },
  { id: 'focus', name: 'Focus', blurb: 'Dark, narrow, quiet', set: { theme: 'midnight', accent: 'slate', size: 100, font: 'system', density: 'cozy', width: 'narrow', round: 'normal', anim: 'reduced', timing: false, thinking: false } },
  { id: 'paper', name: 'Paper', blurb: 'Warm, like a book', set: { theme: 'sepia', accent: 'orange', size: 105, font: 'serif', density: 'spacious', width: 'narrow', round: 'normal', anim: 'reduced' } },
  { id: 'compact', name: 'Compact', blurb: 'More on the screen', set: { theme: 'auto', size: 92, font: 'system', density: 'compact', width: 'wide', round: 'sharp', anim: 'reduced' } },
  { id: 'big', name: 'Big and clear', blurb: 'Large, high contrast', set: { theme: 'contrast', size: 125, font: 'readable', density: 'spacious', width: 'normal', round: 'normal', anim: 'off' } },
];

const KEY = 'sh.ui';
const store = safeStore();

/** Keep only values this page understands. The server applies the same rules again. */
export function sanitize(raw) {
  const out = {};
  if (!raw || typeof raw !== 'object') return out;
  const oneOf = (k, list) => { if (list.includes(raw[k])) out[k] = raw[k]; };
  oneOf('theme', THEMES.map((t) => t.id)); oneOf('font', FONTS.map((f) => f[0]));
  oneOf('density', ['compact', 'cozy', 'spacious']); oneOf('width', ['narrow', 'normal', 'wide', 'full']);
  oneOf('round', ['sharp', 'normal', 'round']); oneOf('anim', ['on', 'reduced', 'off']); oneOf('steps_open', ['running', 'always', 'never']);
  if (raw.accent in ACCENTS || /^#[0-9a-f]{6}$/i.test(String(raw.accent))) out.accent = String(raw.accent).toLowerCase();
  if (typeof raw.size === 'number' && Number.isFinite(raw.size)) out.size = Math.max(85, Math.min(140, Math.round(raw.size)));
  for (const k of ['timing', 'thinking', 'fold_long', 'workspace_auto', 'show_estimate', 'send_on_enter']) if (typeof raw[k] === 'boolean') out[k] = raw[k];
  for (const [k, all] of [['chips', Object.keys(CHIP_LABELS)], ['side_items', Object.keys(SIDE_LABELS)]]) {
    if (Array.isArray(raw[k])) out[k] = [...new Set(raw[k].filter((x) => all.includes(x)))];
  }
  return out;
}

const mix = (hex, to, amount) => {
  const n = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
  const a = n(hex), b = n(to);
  return '#' + a.map((v, i) => Math.round(v + (b[i] - v) * amount).toString(16).padStart(2, '0')).join('');
};
const luminance = (hex) => { const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4)); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
const FONT_STACKS = {
  system: 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif',
  serif: 'Georgia, "Iowan Old Style", "Palatino Linotype", Palatino, serif',
  rounded: 'ui-rounded, "SF Pro Rounded", "Nunito", "Trebuchet MS", system-ui, sans-serif',
  mono: 'ui-monospace, "SF Mono", Menlo, Consolas, monospace',
  readable: 'Verdana, Tahoma, "Segoe UI", system-ui, sans-serif',
};
const WIDTHS = { narrow: '660px', normal: '820px', wide: '1040px', full: 'none' };

/** Paint the page from a full set of choices. Safe to call as often as you like. */
export function applyPrefs(p) {
  const r = document.documentElement;
  const dark = p.theme === 'dark' || p.theme === 'midnight' || (p.theme === 'auto' && matchMedia('(prefers-color-scheme: dark)').matches);
  if (p.theme === 'auto') delete r.dataset.theme; else r.dataset.theme = p.theme;
  r.dataset.dark = dark ? '1' : '0';
  r.dataset.anim = p.anim; r.dataset.density = p.density; r.dataset.round = p.round; r.dataset.font = p.font;
  r.style.setProperty('--scale', String(p.size / 100));
  r.style.setProperty('--font', FONT_STACKS[p.font] || FONT_STACKS.system);
  r.style.setProperty('--thread-w', WIDTHS[p.width] || WIDTHS.normal);
  r.classList.toggle('no-timing', !p.timing); r.classList.toggle('no-thinking', !p.thinking);
  r.classList.toggle('no-estimate', !p.show_estimate);
  // The accent is the user's pick, lightened on a dark page so it stays readable. High contrast keeps its own colors.
  if (p.theme === 'contrast') { r.style.removeProperty('--accent-user'); r.style.removeProperty('--accent-ink-user'); }
  else {
    const base = ACCENTS[p.accent] || (/^#[0-9a-f]{6}$/i.test(p.accent) ? p.accent : ACCENTS.teal);
    const use = dark ? mix(base, '#ffffff', 0.3) : base;
    r.style.setProperty('--accent-user', use);
    r.style.setProperty('--accent-ink-user', luminance(use) > 0.5 ? '#10201a' : '#ffffff');
  }
  const side = { memory: '#open-profile', activity: '#open-activity', files: '#open-files-btn' };
  for (const [k, sel] of Object.entries(side)) { const el = $(sel); if (el) el.hidden = !p.side_items.includes(k); }
}

/** The live preferences. `get()` always returns a complete set; `set()` repaints and saves. */
export function createPrefs({ api }) {
  let P = { ...DEFAULTS, ...sanitize(store.get(KEY, {})) };
  const listeners = new Set();
  let timer = null, remote = false;

  const save = () => {
    store.set(KEY, P);
    if (!remote) return;
    clearTimeout(timer);
    timer = setTimeout(() => api('/api/settings', { method: 'PUT', body: { ui_prefs: P } }).catch(() => { /* the local copy still works */ }), 500);
  };
  const paint = () => { applyPrefs(P); listeners.forEach((fn) => fn(P)); };
  matchMedia('(prefers-color-scheme: dark)').addEventListener?.('change', () => { if (P.theme === 'auto') paint(); });

  return {
    get: () => P,
    /** Show the saved look before the server answers, so the page never flashes the wrong colors. */
    paintNow: paint,
    /** After sign-in: the server's copy wins. A brand-new account takes this device's look and saves it. */
    adopt(serverPrefs) {
      const s = sanitize(serverPrefs);
      remote = true;
      if (Object.keys(s).length) { P = { ...DEFAULTS, ...s }; store.set(KEY, P); paint(); }
      else if (Object.keys(sanitize(store.get(KEY, {}))).length) save();
    },
    set(patch) { P = { ...P, ...sanitize({ ...P, ...patch }) }; paint(); save(); },
    look(id) { const l = LOOKS.find((x) => x.id === id); if (l) this.set({ ...DEFAULTS, ...l.set, chips: P.chips, side_items: P.side_items, send_on_enter: P.send_on_enter, workspace_auto: P.workspace_auto, fold_long: P.fold_long, show_estimate: P.show_estimate, steps_open: P.steps_open }); },
    reset() { P = { ...DEFAULTS, chips: [...DEFAULTS.chips], side_items: [...DEFAULTS.side_items] }; paint(); save(); },
    onChange(fn) { listeners.add(fn); return () => listeners.delete(fn); },
    /** The small view the run card reads. Live, so a change shows on the next step. */
    display: {
      get open() { return P.steps_open; },
      get anim() { return P.anim === 'off' ? 'off' : 'on'; },
      get timing() { return P.timing; },
      get thinking() { return P.thinking; },
    },
  };
}
