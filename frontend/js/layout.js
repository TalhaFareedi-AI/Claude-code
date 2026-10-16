// Side panels: drag the edge with the mouse to resize, click « to minimize the sidebar to icons,
// and open or close the workspace with the Workspace button or its ✕. Sizes are remembered.
import { $, safeStore } from './dom.js';

const store = safeStore();
const LIMITS = { side: [200, 480], files: [260, 720] };
const DEFAULT = { side: 272, files: 336 };

export function setupLayout({ onFilesToggle } = {}) {
  const app = $('#app');
  const st = { side: DEFAULT.side, files: DEFAULT.files, rail: false, ...store.get('sh.layout', {}) };
  const narrow = () => matchMedia('(max-width: 1100px)').matches;
  const clamp = (k, v) => Math.max(LIMITS[k][0], Math.min(LIMITS[k][1], Math.round(v)));
  const save = () => store.set('sh.layout', { side: st.side, files: st.files, rail: st.rail, filesOpen: app.dataset.files === 'open' });

  function apply() {
    app.style.setProperty('--files-w', clamp('files', st.files) + 'px');
    if (st.rail) { app.dataset.rail = '1'; app.style.removeProperty('--side-w'); app.style.setProperty('--side-w', '64px'); }
    else { delete app.dataset.rail; app.style.setProperty('--side-w', clamp('side', st.side) + 'px'); }
    $('#collapse-side').setAttribute('aria-label', st.rail ? 'Expand sidebar' : 'Minimize sidebar');
    $('#collapse-side').title = st.rail ? 'Expand sidebar' : 'Minimize sidebar';
    $('#side-resizer').hidden = st.rail && false;
  }

  function drag(handle, key, fromRight) {
    const move = (clientX) => {
      const x = fromRight ? window.innerWidth - clientX : clientX;
      if (key === 'side') {
        if (x < 150) { st.rail = true; } else { st.rail = false; st.side = clamp('side', x); }
      } else st.files = clamp('files', x);
      apply();
    };
    handle.addEventListener('pointerdown', (e) => {
      if (e.button !== 0) return;
      e.preventDefault(); handle.setPointerCapture(e.pointerId); handle.classList.add('dragging'); document.body.classList.add('resizing');
      const onMove = (ev) => move(ev.clientX);
      const onUp = () => { handle.classList.remove('dragging'); document.body.classList.remove('resizing'); handle.removeEventListener('pointermove', onMove); handle.removeEventListener('pointerup', onUp); handle.removeEventListener('pointercancel', onUp); save(); };
      handle.addEventListener('pointermove', onMove); handle.addEventListener('pointerup', onUp); handle.addEventListener('pointercancel', onUp);
    });
    handle.addEventListener('dblclick', () => { if (key === 'side') { st.rail = false; st.side = DEFAULT.side; } else st.files = DEFAULT.files; apply(); save(); });
    handle.addEventListener('keydown', (e) => {
      const step = e.shiftKey ? 48 : 16;
      const dir = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
      if (!dir) return;
      e.preventDefault();
      if (key === 'side') { st.rail = false; st.side = clamp('side', st.side + dir * step); } else st.files = clamp('files', st.files - dir * step);
      apply(); save();
    });
  }

  drag($('#side-resizer'), 'side', false);
  drag($('#files-resizer'), 'files', true);
  $('#collapse-side').addEventListener('click', () => { st.rail = !st.rail; apply(); save(); });

  function files(open) {
    app.dataset.files = open ? 'open' : 'closed';
    $('#files-toggle').setAttribute('aria-expanded', String(open));
    $('#scrim').hidden = !(open && narrow());
    save(); onFilesToggle?.(open);
  }
  $('#files-toggle').addEventListener('click', () => files(app.dataset.files !== 'open'));
  $('#close-files').addEventListener('click', () => files(false));

  apply();
  if (!narrow() && store.get('sh.layout', {}).filesOpen) files(true);
  return { openFiles: () => files(true), closeFiles: () => files(false), isOpen: () => app.dataset.files === 'open' };
}
