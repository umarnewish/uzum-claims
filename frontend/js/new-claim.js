import { api, toast, getToken } from './api.js';

const params = new URLSearchParams(location.search);
const claimId = params.get('id');

const status = document.getElementById('status');
const title = document.getElementById('title');
const summary = document.getElementById('summary');
const sumShop = document.getElementById('sum-shop');
const sumQty = document.getElementById('sum-qty');
const sumAmount = document.getElementById('sum-amount');
const sumStatus = document.getElementById('sum-status');
const itemsTbody = document.querySelector('#items-table tbody');
const genBtn = document.getElementById('generate-btn');
const dlClaim = document.getElementById('dl-claim');
const dlAgreement = document.getElementById('dl-agreement');
const statusSelect = document.getElementById('status-select');
const paidAmount = document.getElementById('paid-amount');
const notesEl = document.getElementById('notes');
const saveStatusBtn = document.getElementById('save-status-btn');

function fmtMoney(v) {
  if (v == null) return '—';
  return new Intl.NumberFormat('ru-RU').format(v) + ' сум';
}

function escape(s) {
  return s == null ? '' : String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function outstanding(item) {
  return item.received_qty == null ? item.expected_qty : Math.max(item.expected_qty - item.received_qty, 0);
}

function render(claim) {
  title.textContent = `Претензия #${claim.id}`;
  status.textContent = `Создана: ${new Date(claim.created_at).toLocaleString('ru-RU')}`;
  summary.hidden = false;
  sumShop.textContent = claim.shop_id;
  sumQty.textContent = claim.total_qty ?? '—';
  sumAmount.textContent = fmtMoney(claim.total_amount);
  sumStatus.textContent = claim.status;

  const items = claim.items || [];
  itemsTbody.innerHTML = items.map((it) => {
    const qty = outstanding(it);
    const total = (it.unit_compensation ?? 0) * qty;
    return `<tr>
      <td>
        <div class="primary-text">${escape(it.product_title) || '—'}</div>
        <div class="muted-text">${escape(it.barcode) || ''} · ${escape(it.loss_type)}</div>
      </td>
      <td class="num">${qty}</td>
      <td class="num">${fmtMoney(it.unit_compensation)}</td>
      <td class="num">${fmtMoney(total)}</td>
    </tr>`;
  }).join('');

  statusSelect.value = claim.status;
  paidAmount.value = claim.paid_amount ?? '';
  notesEl.value = claim.notes ?? '';

  const generated = !!claim.generated_docx_path;
  genBtn.disabled = false;
  genBtn.textContent = generated ? 'Сгенерировать заново' : 'Сгенерировать docx';
  for (const [el, kind] of [[dlClaim, 'claim'], [dlAgreement, 'agreement']]) {
    if (generated) {
      el.hidden = false;
      el.href = `/api/claims/${claim.id}/download/${kind}?t=${getToken()}`;
      // FileResponse needs Authorization. Use a click handler instead.
      el.dataset.kind = kind;
    } else {
      el.hidden = true;
    }
  }
}

async function load() {
  if (!claimId) {
    status.textContent = 'Откройте через /losses → выберите строки → «Создать претензию».';
    return;
  }
  try {
    const claim = await api(`/api/claims/${claimId}`);
    render(claim);
  } catch (e) {
    status.textContent = `Ошибка: ${e.message}`;
  }
}

genBtn.addEventListener('click', async () => {
  genBtn.disabled = true;
  const prev = genBtn.textContent;
  genBtn.textContent = 'Генерируем…';
  try {
    await api(`/api/claims/${claimId}/generate`, { method: 'POST' });
    toast('Сгенерировано', 'success');
    await load();
  } catch (e) {
    toast(e.message, 'error');
    genBtn.disabled = false;
    genBtn.textContent = prev;
  }
});

// Authenticated download — fetch as blob then trigger save dialog.
for (const el of [dlClaim, dlAgreement]) {
  el.addEventListener('click', async (ev) => {
    ev.preventDefault();
    const kind = el.dataset.kind;
    try {
      const res = await fetch(`/api/claims/${claimId}/download/${kind}`, {
        headers: { Authorization: `Bearer ${getToken()}` },
        credentials: 'include',
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${kind}_${claimId}.docx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      toast(`Не удалось скачать: ${e.message}`, 'error');
    }
  });
}

saveStatusBtn.addEventListener('click', async () => {
  saveStatusBtn.disabled = true;
  try {
    const body = {
      status: statusSelect.value,
      paid_amount: paidAmount.value === '' ? null : Number(paidAmount.value),
      notes: notesEl.value || null,
    };
    await api(`/api/claims/${claimId}`, { method: 'PATCH', body });
    toast('Сохранено', 'success');
    await load();
  } catch (e) {
    toast(e.message, 'error');
  } finally {
    saveStatusBtn.disabled = false;
  }
});

load();
