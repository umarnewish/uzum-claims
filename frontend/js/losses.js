import { api, toast } from './api.js';

const status = document.getElementById('status');
const groups = document.getElementById('groups');
const refreshBtn = document.getElementById('refresh-btn');
const createBtn = document.getElementById('create-claim-btn');
const filterType = document.getElementById('filter-type');
const filterClaim = document.getElementById('filter-claim');

const TYPE_LABELS = {
  return_uzum_short: 'Недогруз от Uzum (return)',
  return_transit: 'Утеря в транзите (return)',
  fbo_supply_reject: 'Брак при приёмке поставки',
  fbo_warehouse: 'Недостача на складе FBO',
  order_lost_delivery: 'Потерянные заказы',
};

function fmtMoney(v) {
  if (v == null) return '—';
  return new Intl.NumberFormat('ru-RU').format(v) + ' сум';
}

function group(rows) {
  const out = new Map();
  for (const r of rows) {
    const key = `${r.shop_id}::${r.loss_type}`;
    if (!out.has(key)) out.set(key, { shop_id: r.shop_id, loss_type: r.loss_type, rows: [] });
    out.get(key).rows.push(r);
  }
  return [...out.values()];
}

function render(items) {
  if (!items.length) {
    groups.innerHTML = '<p class="lead">Пока ничего не найдено. Нажмите «Обновить из Uzum».</p>';
    return;
  }
  const groupsHtml = group(items).map((g) => {
    const lines = g.rows.map((r) => {
      const outstanding = r.received_qty == null ? r.expected_qty : (r.expected_qty - r.received_qty);
      const total = (r.unit_compensation ?? 0) * outstanding;
      const claimed = r.claim_id ? `<span class="pill">в претензии #${r.claim_id}</span>` : '';
      const editable = !r.claim_id && r.loss_type !== 'return_transit';
      const recvCell = editable
        ? `<input type="number" class="recv" data-id="${r.id}" min="0" max="${r.expected_qty}" value="${r.received_qty ?? ''}" placeholder="—"/>`
        : (r.received_qty ?? '—');
      return `
        <tr>
          <td><input type="checkbox" data-id="${r.id}" ${r.claim_id ? 'disabled' : ''}/></td>
          <td>
            <div class="primary-text">${escape(r.product_title) || '—'}</div>
            <div class="muted-text">${escape(r.barcode) || ''}</div>
          </td>
          <td class="num">${r.expected_qty}</td>
          <td class="num">${recvCell}</td>
          <td class="num">${fmtMoney(r.unit_compensation)}</td>
          <td class="num">${fmtMoney(total)}</td>
          <td>${claimed}</td>
        </tr>`;
    }).join('');
    return `
      <div class="group">
        <h2>Магазин ${g.shop_id} · ${TYPE_LABELS[g.loss_type] || g.loss_type}
          <span class="badge">${g.rows.length}</span>
        </h2>
        <table class="data">
          <thead>
            <tr>
              <th></th><th>Товар</th><th class="num">Ожид.</th><th class="num">Получ.</th>
              <th class="num">Комп./шт</th><th class="num">Итого</th><th></th>
            </tr>
          </thead>
          <tbody>${lines}</tbody>
        </table>
      </div>`;
  }).join('');
  groups.innerHTML = groupsHtml;
}

function escape(s) {
  if (s == null) return '';
  return String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

async function load() {
  status.textContent = 'Загрузка…';
  const params = new URLSearchParams();
  if (filterType.value) params.set('type', filterType.value);
  if (filterClaim.value) params.set('claim_status', filterClaim.value);
  try {
    const items = await api(`/api/losses?${params.toString()}`);
    render(items);
    status.textContent = `Найдено: ${items.length}`;
  } catch (e) {
    status.textContent = `Ошибка: ${e.message}`;
  }
}

refreshBtn.addEventListener('click', async () => {
  refreshBtn.disabled = true;
  refreshBtn.textContent = 'Обновляем…';
  try {
    const sum = await api('/api/losses/refresh', { method: 'POST' });
    toast(`Обновлено: ${sum.return_uzum_short} новых из ${sum.shops} магазинов`, 'success');
    if (sum.errors?.length) toast(`Ошибок: ${sum.errors.length}`, 'error');
    await load();
  } catch (e) {
    toast(e.message, 'error');
  } finally {
    refreshBtn.disabled = false;
    refreshBtn.textContent = 'Обновить из Uzum';
  }
});

filterType.addEventListener('change', load);
filterClaim.addEventListener('change', load);

function selectedIds() {
  return [...groups.querySelectorAll('input[type=checkbox][data-id]:checked')]
    .map((el) => Number(el.dataset.id));
}

function syncCreateBtn() {
  const ids = selectedIds();
  createBtn.disabled = ids.length === 0;
  createBtn.textContent = `Создать претензию (${ids.length})`;
}

groups.addEventListener('change', (ev) => {
  if (ev.target.matches('input[type=checkbox][data-id]')) syncCreateBtn();
});

createBtn.addEventListener('click', async () => {
  const ids = selectedIds();
  if (!ids.length) return;
  createBtn.disabled = true;
  try {
    const claim = await api('/api/claims', { method: 'POST', body: { lost_item_ids: ids } });
    window.location.href = `/new-claim?id=${claim.id}`;
  } catch (e) {
    toast(e.message, 'error');
    createBtn.disabled = false;
  }
});

groups.addEventListener('change', async (ev) => {
  const el = ev.target;
  if (!el.matches('input.recv')) return;
  const id = el.dataset.id;
  const v = el.value.trim();
  if (v === '') return;
  const received_qty = Number(v);
  if (!Number.isFinite(received_qty) || received_qty < 0) {
    toast('Некорректное число', 'error');
    return;
  }
  el.disabled = true;
  try {
    await api(`/api/losses/${id}/confirm`, { method: 'POST', body: { received_qty } });
    toast('Получение зафиксировано', 'success');
    await load();
  } catch (e) {
    toast(e.message, 'error');
    el.disabled = false;
  }
});

load();
