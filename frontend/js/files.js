// The files panel: every file this chat made, with Open and Download. Links are signed and expire.
import { h, $, toast } from './dom.js';
import { api } from './api.js';
import { renderSvg } from './charts.js';
import { renderMarkdown } from './markdown.js';

const ICON = { pptx: '📊', docx: '📝', svg: '🖼️', pdf: '📕', txt: '📄', doc: '📄', slides: '📊', md: '📄', png: '🖼️', jpg: '🖼️' };
const size = (n) => (n > 1073741824 ? `${(n / 1073741824).toFixed(1)} GB` : n > 1048576 ? `${(n / 1048576).toFixed(1)} MB` : n > 1024 ? `${Math.round(n / 1024)} KB` : `${n} B`);

export class FilesPanel {
  constructor() { this.list = $('#file-list'); this.empty = $('#files-empty'); this.preview = $('#preview'); this.count = $('#files-count'); this.refreshSeq = 0; this.previewSeq = 0; }

  async refresh(convId) {
    this.convId = convId;
    const seq = ++this.refreshSeq;
    if (this.convId !== convId) { this.convId = convId; this.previewSeq++; this.preview.hidden = true; }
    try {
      const r = await api(convId ? `/api/files?conversation_id=${encodeURIComponent(convId)}` : '/api/files');
      if (seq !== this.refreshSeq) return;
      $('#ws-name').textContent = r.workspace_name;
      $('#ws-meter').style.width = `${Math.min(100, (r.used_bytes / r.limit_bytes) * 100)}%`;
      $('#ws-usage').textContent = `${size(r.used_bytes)} of ${size(r.limit_bytes)} used`;
      this.render(r.files);
    } catch (e) { if (seq === this.refreshSeq) toast(e.message); }
  }

  render(files) {
    this.count.textContent = String(files.length);
    this.empty.hidden = files.length > 0;
    this.list.replaceChildren(...files.map((f) => h('li', { class: 'file' },
      h('span', { class: 'ico', 'aria-hidden': 'true', text: ICON[f.kind] || '📄' }),
      h('div', null, h('div', { class: 'name', text: f.name }), h('div', { class: 'meta', text: `${f.kind.toUpperCase()} · ${size(f.size)}${f.version > 1 ? ` · version ${f.version}` : ''}` })),
      h('div', { class: 'acts' },
        h('button', { type: 'button', class: 'btn small', text: 'Open', onclick: () => this.open(f) }),
        h('button', { type: 'button', class: 'btn small', text: 'Download', onclick: () => this.download(f) }),
        ['docx', 'doc', 'md', 'txt'].includes(f.kind) ? h('button', { type: 'button', class: 'btn small', title: 'Export as PDF', text: 'PDF', onclick: () => this.exportPdf(f) }) : null,
        h('button', { type: 'button', class: 'btn small danger-ghost', title: 'Delete this file for good', 'aria-label': `Delete ${f.name}`, text: '🗑', onclick: () => this.remove(f) })))));
  }

  async remove(f) {
    if (!confirm(`Delete ${f.name}? This cannot be undone.`)) return;
    try {
      await api(`/api/files/${f.id}`, { method: 'DELETE' });
      this.preview.hidden = true;
      await this.refresh(this.convId);
      toast(`Deleted ${f.name}`);
    } catch (e) { toast(e.message); }
  }

  async open(f) {
    const seq = ++this.previewSeq;
    try {
      const p = await api(`/api/files/${f.id}/preview`);
      if (seq !== this.previewSeq) return;
      this.preview.hidden = false;
      if (p.kind === 'svg') this.preview.replaceChildren(h('h3', { text: f.name }), renderSvg(p.svg));
      else if (p.kind === 'slides') this.preview.replaceChildren(h('h3', { text: p.title || f.name }),
        ...p.markdown.split(/^---[ \t]*$/m).filter((s) => s.trim()).map((s, i) =>
          h('div', { class: 'slide-page' }, h('span', { class: 'muted tiny', text: `Slide ${i + 1}` }), renderMarkdown(s.trim()))));
      else if (p.markdown) this.preview.replaceChildren(h('div', { class: 'doc-read' }, renderMarkdown(p.markdown)));
      else if (p.items) this.preview.replaceChildren(h('h3', { text: p.title || f.name }), ...p.items.map((it, k) => h('div', { class: 'slide' }, h('b', { text: `${k + 1}. ${it.title || ''}` }), it.lines?.length ? h('ul', null, it.lines.map((l) => h('li', { text: String(l) }))) : null)));
      else this.preview.replaceChildren(h('p', { class: 'muted', text: p.note || 'No preview. Use Download.' }));
      this.preview.scrollIntoView({ block: 'nearest' });
    } catch (e) { if (seq === this.previewSeq) toast(e.message); }
  }

  async exportPdf(f) {
    try {
      const res = await api(`/api/files/${f.id}/pdf`, { method: 'POST' });
      await this.refresh(this.convId);
      if (res.url) {
        const a = h('a', { href: res.url, download: res.file?.name || 'document.pdf' });
        document.body.append(a); a.click(); a.remove();
      }
      toast('Exported PDF');
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
