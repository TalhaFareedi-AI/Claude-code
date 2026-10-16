// Plan section 14: a long answer folds after about 30 lines, with Show more. The full text is always in the page,
// so copying, searching and reading with a screen reader all work. Folding only limits how much is on screen.
import { h } from './dom.js';

const LINES = 30;

export function foldLong(el, enabled = true) {
  if (!el) return;
  unfold(el);
  if (!enabled) return;
  const line = parseFloat(getComputedStyle(el).lineHeight) || 24;
  const limit = Math.round(line * LINES);
  if (el.scrollHeight <= limit * 1.25) return;           // only fold when there is a real amount to hide
  el.style.setProperty('--fold-h', `${limit}px`);
  el.classList.add('folded');
  const btn = h('button', { type: 'button', class: 'btn small fold-toggle', text: 'Show more', 'aria-expanded': 'false' });
  btn.addEventListener('click', () => {
    const open = el.classList.toggle('folded') === false;
    btn.textContent = open ? 'Show less' : 'Show more';
    btn.setAttribute('aria-expanded', String(open));
  });
  el.after(btn);
}

function unfold(el) {
  el.classList.remove('folded');
  if (el.nextElementSibling?.classList.contains('fold-toggle')) el.nextElementSibling.remove();
}

/** Re-check every answer in the chat, for example after the user changes the fold setting. */
export function refoldAll(root, enabled) {
  requestAnimationFrame(() => root.querySelectorAll('.msg.assistant .answer').forEach((el) => foldLong(el, enabled)));
}
