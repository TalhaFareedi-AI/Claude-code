// Talks to the server. The chat answer arrives as a stream of small events (Server-Sent Events).
export class ApiError extends Error {
  constructor(message, status) { super(message); this.status = status; }
}

export async function api(path, { method = 'GET', body } = {}) {
  let res;
  try {
    res = await fetch(path, { method, headers: body ? { 'Content-Type': 'application/json' } : {}, body: body ? JSON.stringify(body) : undefined });
  } catch {
    throw new ApiError('Cannot reach the server. Check your connection and try again.', 0);
  }
  if (!res.ok) {
    let msg = `Something went wrong (${res.status}).`;
    try { const j = await res.json(); if (typeof j.detail === 'string') msg = j.detail; else if (Array.isArray(j.detail)) msg = 'Please check your settings and try again.'; } catch { /* keep default */ }
    throw new ApiError(msg, res.status);
  }
  return res.status === 204 ? null : res.json();
}

export async function uploadFile(file) {
  let res;
  try { res = await fetch(`/api/upload?name=${encodeURIComponent(file.name)}`, { method: 'PUT', body: file }); }
  catch { throw new ApiError('Upload failed. Check your connection.', 0); }
  if (!res.ok) { let m = 'Upload failed.'; try { m = (await res.json()).detail || m; } catch { /* default */ } throw new ApiError(m, res.status); }
  return res.json();
}

// POST and read the event stream. Calls onEvent(event) for each. Stops when `signal` aborts.
export async function streamChat(body, onEvent, signal) {
  let res;
  try {
    res = await fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal });
  } catch (e) {
    if (e.name === 'AbortError') return;
    throw new ApiError('Cannot reach the server. Check your connection and try again.', 0);
  }
  if (!res.ok) {
    let msg = `Something went wrong (${res.status}).`;
    try { const j = await res.json(); if (typeof j.detail === 'string') msg = j.detail; } catch { /* default */ }
    throw new ApiError(msg, res.status);
  }
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = '';
  for (;;) {
    let chunk;
    try { chunk = await reader.read(); } catch (e) { if (e.name === 'AbortError') return; throw new ApiError('The connection dropped. Your run keeps going on the server; reload to see it.', 0); }
    if (chunk.done) break;
    buf += dec.decode(chunk.value, { stream: true });
    let idx;
    while ((idx = buf.indexOf('\n\n')) >= 0) {
      const block = buf.slice(0, idx); buf = buf.slice(idx + 2);
      for (const line of block.split('\n')) {
        if (!line.startsWith('data:')) continue;
        try { onEvent(JSON.parse(line.slice(5))); } catch (e) { console.error('bad event', e); }
      }
    }
  }
}
