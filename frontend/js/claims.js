import { api } from './api.js';

const status = document.getElementById('status');
const tbody = document.querySelector('#claims-table tbody');
const filter = document.getElementById('filter-status');

const STATUS_BADGE = {
  draft: 'claim-badge--draft',
  generated: 'claim-badge--generated',
  submitted: 'claim-badge--submitted',
  paid: 'claim-badge--paid',
  rejected: 'claim-badge--rejected',
};

function fmtMoney(v) {
  if (v == null) return '—';
  return new Intl.NumberFormat('ru-RU').format(v) + ' сум';
}

function escape(s) {
  return s == null ? '' : String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function render(rows) {
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="7" class="muted-text">Нет претензий по выбранному фильтру.</td></tr>';
    return;
  }
  tbody.innerHTML = rows.map((c) => {
    const badge = STATUS_BADGE[c.status] || '';
    return `<tr>
      <td><a href="/new-claim?id=${c.id}" class="row-link">#${c.id}</a></td>
      <td>${c.shop_id}</td>
      <td>${new Date(c.created_at).toLocaleString('ru-RU')}</td>
      <td class="num">${c.total_qty ?? '—'}</td>
      <td class="num">${fmtMoney(c.total_amount)}</td>
      <td class="num">${fmtMoney(c.paid_amount)}</td>
      <td><span class="claim-badge ${badge}">${escape(c.status)}</span></td>
    </tr>`;
  }).join('');
}

async function load() {
  status.textContent = 'Загрузка…';
  const params = new URLSearchParams();
  if (filter.value) params.set('status', filter.value);
  try {
    const rows = await api(`/api/claims?${params.toString()}`);
    render(rows);
    status.textContent = `Найдено: ${rows.length}`;
  } catch (e) {
    status.textContent = `Ошибка: ${e.message}`;
  }
}

filter.addEventListener('change', load);
load();
