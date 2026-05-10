// Thin fetch wrapper. Auth via Authorization: Bearer <jwt> from localStorage
// (key `vendex_token`), with cookie `vendex_token` as fallback (browser sends
// it automatically when present — that's the prod path via shared domain).
const TOKEN_KEY = 'vendex_token';

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || '';
}

export function setToken(t) {
  if (t) localStorage.setItem(TOKEN_KEY, t);
  else localStorage.removeItem(TOKEN_KEY);
}

export async function api(path, { method = 'GET', body, headers = {} } = {}) {
  const token = getToken();
  const opts = {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers,
    },
    credentials: 'include',
  };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const res = await fetch(path, opts);
  if (res.status === 204) return null;
  let data = null;
  try { data = await res.json(); } catch { /* non-json */ }
  if (!res.ok) {
    const err = new Error(data?.detail || `HTTP ${res.status}`);
    err.status = res.status;
    err.data = data;
    throw err;
  }
  return data;
}

export function toast(msg, kind = '') {
  let el = document.querySelector('.toast');
  if (!el) {
    el = document.createElement('div');
    el.className = 'toast';
    document.body.appendChild(el);
  }
  // Map shorthand to vendex toast classes
  const cls = kind === 'success' ? 'toast-success'
            : kind === 'error'   ? 'toast-error'
            : kind === 'info'    ? 'toast-info'
            : '';
  el.textContent = msg;
  el.className = `toast show ${cls}`;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.remove('show'), 2200);
}
