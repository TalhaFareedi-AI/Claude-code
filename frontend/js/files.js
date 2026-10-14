// The files panel: every file this chat made, with Open and Download. Links are signed and expire.
import { h, $, toast } from './dom.js';
import { api } from './api.js';
import { renderSvg } from './charts.js';

const ICON = { pptx: '📊', docx: '📝', svg: '🖼️', pdf: '📕', txt: '📄' };
const size = (n) => (n > 1048576 ? `${(n / 1048576).toFixed(1)} MB` : n > 1024 ? `${Math.round(n / 1024)} KB` : `${n} B`);

export class FilesPanel {
  constructor() { this.list = $('#file-list'); this.empty = $('#files-empty'); this.preview = $('#preview'); this.count = $('#files-count'); }

  async refresh(convId) {
    try {
      const r = await api(convId ? `/api/files?conversation_id=${encodeURIComponent(convId)}` : '/api/files');
      $('#ws-name').textContent = r.workspace_name;
      $('#ws-meter').style.width = `${Math.min(100, (r.used_bytes / r.limit_bytes) * 100)}%`;
      $('#ws-usage').textContent = `${size(r.used_bytes)} of ${size(r.limit_bytes)} used`;
      this.render(r.files);
    } catch (e) { toast(e.message); }
  }

  render(files) {
    this.count.textContent = String(files.length);
    this.empty.hidden = files.length > 0;
    this.list.replaceChildren(...files.map((f) => h('li', { class: 'file' },
      h('span', { class: 'ico', 'aria-hidden': 'true', text: ICON[f.kind] || '📄' }),
      h('div', null, h('div', { class: 'name', text: f.name }), h('div', { class: 'meta', text: `${f.kind.toUpperCase()} · ${size(f.size)}${f.version > 1 ? ` · version ${f.version}` : ''}` })),
      h('div', { class: 'acts' },
        h('button', { type: 'button', class: 'btn small', text: 'Open', onclick: () => this.open(f) }),
        h('button', { type: 'button', class: 'btn small', text: 'Download', onclick: () => this.download(f) })))));
  }

  async open(f) {
    try {
      const p = await api(`/api/files/${f.id}/preview`);
      this.preview.hidden = false;
      if (p.kind === 'svg') this.preview.replaceChildren(h('h3', { text: f.name }), renderSvg(p.svg));
      else if (p.items) this.preview.replaceChildren(h('h3', { text: p.title || f.name }), ...p.items.map((it, k) => h('div', { class: 'slide' }, h('b', { text: `${k + 1}. ${it.title || ''}` }), it.lines?.length ? h('ul', null, it.lines.map((l) => h('li', { text: String(l) }))) : null)));
      else this.preview.replaceChildren(h('p', { class: 'muted', text: p.note || 'No preview. Use Download.' }));
      this.preview.scrollIntoView({ block: 'nearest' });
    } catch (e) { toast(e.message); }
  }

  async download(f) {
    try {
      const { url } = await api(`/api/files/${f.id}/link`);
      const a = h('a', { href: url, download: f.name });
      document.body.append(a); a.click(); a.remove();
    } catch (e) { toast(e.message); }
  }
}
