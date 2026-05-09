import { api, toast } from './api.js';

const FIELDS = [
  'fio', 'legal_form', 'legal_name', 'inn',
  'bank_account', 'mfo', 'bank_name', 'address',
  'oked', 'base_contract_no', 'base_contract_date',
];

const form = document.getElementById('profile-form');
const submitBtn = document.getElementById('save-btn');
const status = document.getElementById('status');

function fillForm(data) {
  for (const f of FIELDS) {
    const el = form.elements[f];
    if (!el) continue;
    el.value = data[f] ?? '';
  }
}

function readForm() {
  const out = {};
  for (const f of FIELDS) {
    const el = form.elements[f];
    if (!el) continue;
    const v = el.value.trim();
    out[f] = v === '' ? null : v;
  }
  return out;
}

async function load() {
  status.textContent = 'Загрузка…';
  try {
    const data = await api('/api/profile');
    fillForm(data);
    status.textContent = `Сохранено: ${new Date(data.updated_at).toLocaleString('ru-RU')}`;
  } catch (e) {
    if (e.status === 404) {
      status.textContent = 'Профиль ещё не заполнен. Заполните форму и нажмите «Сохранить».';
    } else if (e.status === 401) {
      status.textContent = 'Не авторизован. Войдите в vendex или сохраните токен в localStorage.vendex_token.';
    } else {
      status.textContent = `Ошибка: ${e.message}`;
    }
  }
}

form.addEventListener('submit', async (ev) => {
  ev.preventDefault();
  submitBtn.disabled = true;
  try {
    const payload = readForm();
    const data = await api('/api/profile', { method: 'PUT', body: payload });
    fillForm(data);
    status.textContent = `Сохранено: ${new Date(data.updated_at).toLocaleString('ru-RU')}`;
    toast('Профиль сохранён', 'success');
  } catch (e) {
    toast(e.message, 'error');
  } finally {
    submitBtn.disabled = false;
  }
});

load();
