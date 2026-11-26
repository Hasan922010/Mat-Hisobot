import { acceptInvite, getSettings, getUser, handleAuthCallback, login, logout, requestPasswordRecovery, signup, updateUser } from '@netlify/identity';

const byId = (id) => document.getElementById(id);
const authForm = byId('auth-form');
const reportForm = byId('report-form');
const historyForm = byId('history-filter');
const searchForm = byId('row-search');
const account = byId('account');
const detailId = /^\/batches\/([a-f0-9-]{36})\/?$/i.exec(location.pathname)?.[1];
const apiPath = '/api/reports';
const workerPath = '/.netlify/functions/audit-background';
const displayNumber = new Intl.NumberFormat('uz', { maximumFractionDigits: 3 });
const statuses = {
  DRAFT: 'Qoralama', QUEUED: 'Navbatda', PROCESSING: 'Tahlil qilinmoqda',
  COMPLETED: 'Tayyor', FAILED: 'Xatolik', DELETING: 'O‘chirilmoqda',
};

const itemColumns = [
  ['tovar_id', 'MXIK / ID'], ['tovar_nomi_kirill', 'Tovar nomi'], ['bosh_qoldiq_soni', 'Bosh qoldiq'],
  ['kirim_soni', 'Kirim'], ['chiqim_soni', 'Chiqim'], ['farq_qoldiq_soni', 'Oxirgi qoldiq'],
  ['farq_qoldiq_summa', 'Qoldiq qiymati'],
];
const markingColumns = [
  ['tovar_id', 'MXIK / ID'], ['tovar_nomi_kirill', 'Tovar nomi'], ['bosh_markirovka_soni', 'Bosh kodlar'],
  ['kirim_tovar_soni', 'Kirim miqdori'], ['kirim_markirovka_soni', 'Kirim kodlari'],
  ['chiqim_tovar_soni', 'Chiqim miqdori'], ['chiqim_markirovka_soni', 'Chiqim kodlari'],
  ['qoldiq_markirovka_soni', 'Qoldiq kodlari'],
];
const groups = {
  items: ['Svod', itemColumns],
  shortages: ['Kirimsiz sotuv', [...itemColumns.slice(0, 5), ['farq_ortiqcha_soni', 'Kirimsiz miqdor'], ['farq_ortiqcha_summa', 'Kirimsiz qiymat']]],
  marking: ['Markirovka', markingColumns],
  discrepancies: ['Kamchiliklar', [...markingColumns, ['kamchilik_sababi', 'Tafovut sababi']]],
};

let authMode = 'login';
let inviteToken;
let registrationOpen = false;
let currentGroup = 'items';
let page = 1;
let search = '';
let requestNumber = 0;
let currentDetail;

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function notice(message, error = false) {
  const target = byId('notice');
  target.textContent = message;
  target.classList.toggle('error', error);
  target.hidden = !message;
}

function show(id) {
  for (const screen of ['loading', 'auth', 'dashboard', 'detail']) byId(screen).hidden = screen !== id;
  account.hidden = !['dashboard', 'detail'].includes(id);
}

function populateAuth(mode) {
  authMode = mode;
  const copy = {
    login: ['Tizimga kirish', 'Hisobotlaringizga kirish uchun davom eting.', 'Kirish'],
    signup: ['Hisob yaratish', 'Elektron pochtangizni tasdiqlab, auditni boshlang.', 'Ro‘yxatdan o‘tish'],
    forgot: ['Parolni tiklash', 'Parolni tiklash havolasi pochtangizga yuboriladi.', 'Havolani yuborish'],
    recovery: ['Yangi parol', 'Hisobingiz uchun yangi parol belgilang.', 'Parolni saqlash'],
    invite: ['Taklifni qabul qilish', 'Hisobingizga kirish uchun parol belgilang.', 'Hisobni faollashtirish'],
  };
  const [title, subtitle, button] = copy[mode];
  byId('auth-title').textContent = title;
  byId('auth-copy').textContent = subtitle;
  byId('auth-submit').textContent = button;
  const email = authForm.elements.email;
  const password = authForm.elements.password;
  email.disabled = byId('email-label').hidden = ['recovery', 'invite'].includes(mode);
  password.disabled = byId('password-label').hidden = mode === 'forgot';
  password.autocomplete = mode === 'login' ? 'current-password' : 'new-password';
  password.minLength = mode === 'login' ? 0 : 8;
  password.value = '';
  byId('auth-switch').hidden = mode === 'login' && !registrationOpen;
  byId('auth-switch').textContent = mode === 'login' ? 'Hisob yaratish' : 'Kirish sahifasiga qaytish';
  byId('auth-forgot').hidden = mode !== 'login';
}

function authMessage(error) {
  if (error?.status === 401) return 'Elektron pochta yoki parol noto‘g‘ri.';
  if (error?.status === 403) return 'Bu amal uchun ruxsat berilmadi. Taklif yoki tasdiqlash xatini tekshiring.';
  if (error?.status === 429) return 'Juda ko‘p urinish. Birozdan so‘ng qayta urinib ko‘ring.';
  return 'Kirishda xatolik yuz berdi. Ma’lumotlaringizni tekshirib, qayta urinib ko‘ring.';
}

async function api(path, options = {}) {
  const response = await fetch(path, { cache: 'no-store', ...options });
  if (response.status === 204) return null;
  const data = await response.json().catch(() => null);
  if (response.ok) return data;
  if (response.status === 401) {
    show('auth');
    populateAuth('login');
  }
  throw new Error(data?.error || 'Xizmat javob bermadi. Keyinroq qayta urinib ko‘ring.');
}

function post(path, data) {
  return api(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
}

async function startAudit(id) {
  const response = await fetch(workerPath, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id }),
  });
  if (!response.ok) throw new Error('Tahlilni boshlash imkoni bo‘lmadi. Qayta urinib ko‘ring.');
}

async function openWorkspace(user) {
  byId('account-email').textContent = user.email;
  notice('');
  if (detailId) {
    show('detail');
    await loadDetail();
  } else {
    show('dashboard');
    await loadHistory();
  }
}

byId('auth-switch').addEventListener('click', () => { notice(''); populateAuth(authMode === 'login' ? 'signup' : 'login'); });
byId('auth-forgot').addEventListener('click', () => { notice(''); populateAuth('forgot'); });
byId('logout').addEventListener('click', async () => {
  try { await logout(); location.assign('/'); } catch (error) { notice(authMessage(error), true); }
});

authForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const { email, password } = authForm.elements;
  const submit = byId('auth-submit');
  submit.disabled = true;
  notice('');
  let user;
  try {
    if (authMode === 'login') user = await login(email.value, password.value);
    if (authMode === 'signup') {
      user = await signup(email.value, password.value);
      if (!user.emailVerified) {
        populateAuth('login');
        notice('Hisobni faollashtirish uchun elektron pochtangizni tekshiring.');
        return;
      }
    }
    if (authMode === 'forgot') {
      await requestPasswordRecovery(email.value);
      populateAuth('login');
      notice('Agar hisob mavjud bo‘lsa, parolni tiklash havolasi pochta orqali yuborildi.');
      return;
    }
    if (authMode === 'invite') user = await acceptInvite(inviteToken, password.value);
    if (authMode === 'recovery') user = await updateUser({ password: password.value });
  } catch (error) {
    notice(authMessage(error), true);
    return;
  } finally {
    password.value = '';
    submit.disabled = false;
  }
  if (user) openWorkspace(user).catch((error) => notice(error.message, true));
});

function addColumnOptions() {
  for (const [role, title] of [['kirim', 'Kirim'], ['chiqim', 'Chiqim']]) {
    const fieldset = element('fieldset');
    fieldset.append(element('legend', title));
    for (const [name, label] of [
      ['sheet', 'Excel varag‘i'], ['tovar_id', 'MXIK / ID ustuni'], ['tovar_nomi', 'Tovar nomi ustuni'],
      [`${role}_soni`, 'Miqdor ustuni'], ['summa', 'Summa ustuni'], [`${role}_markirovka`, 'Markirovka ustuni'],
    ]) {
      const wrapper = element('label', label);
      const input = element('input');
      input.name = `${role}_${name}`;
      input.maxLength = name === 'sheet' ? 31 : 200;
      input.placeholder = 'Avtomatik';
      wrapper.append(input);
      fieldset.append(wrapper);
    }
    byId('column-options').append(fieldset);
  }
}

function toggleFiles() {
  const combined = reportForm.elements.mode.value === 'combined';
  byId('files-combined').hidden = !combined;
  byId('files-separate').hidden = combined;
  for (const role of ['combined', 'kirim', 'chiqim']) {
    const input = reportForm.elements[role];
    input.required = role === 'combined' ? combined : !combined;
    input.disabled = !input.required;
  }
}

reportForm.elements.year.value = new Date().getFullYear();
reportForm.elements.mode.addEventListener('change', toggleFiles);
addColumnOptions();
toggleFiles();

reportForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const submit = event.submitter || reportForm.querySelector('button[type=submit]');
  const data = new FormData(reportForm);
  const mode = data.get('mode');
  const roles = mode === 'combined' ? ['combined'] : ['kirim', 'chiqim'];
  const files = Object.fromEntries(roles.map((role) => [role, data.get(role)]));
  if (Object.values(files).some((file) => !file?.size || file.size > 10 * 1024 * 1024)) {
    notice('Bo‘sh fayl yuklab bo‘lmaydi. Har bir fayl 10 MB dan oshmasligi kerak.', true);
    return;
  }
  const options = {};
  if (mode === 'separate') {
    for (const role of roles) {
      options[role] = {
        sheet: data.get(`${role}_sheet`),
        columns: Object.fromEntries(['tovar_id', 'tovar_nomi', `${role}_soni`, 'summa', `${role}_markirovka`].map((name) => [name, data.get(`${role}_${name}`)])),
      };
    }
  }
  submit.disabled = true;
  notice('Fayllar yuklanmoqda…');
  let id;
  let queued = false;
  try {
    ({ id } = await post(apiPath, {
      company: data.get('company'), stir: data.get('stir'), year: data.get('year'), period: data.get('period'),
      mode, files: Object.fromEntries(roles.map((role) => [role, files[role].name])), options,
    }));
    for (const role of roles) await api(`${apiPath}/${id}/files/${role}`, { method: 'PUT', body: files[role] });
    await post(`${apiPath}/${id}/queue`, {});
    queued = true;
    await startAudit(id);
    location.assign(`/batches/${id}/`);
  } catch (error) {
    if (queued) location.assign(`/batches/${id}/`);
    else {
      if (id) await api(`${apiPath}/${id}`, { method: 'DELETE' }).catch(() => {});
      notice(error.message, true);
    }
  } finally { submit.disabled = false; }
});

async function loadHistory() {
  const stir = new FormData(historyForm).get('stir').trim();
  const records = await api(`${apiPath}${stir ? `?stir=${encodeURIComponent(stir)}` : ''}`);
  const list = byId('history-list');
  const count = byId('history-count');
  count.hidden = !records.length;
  count.textContent = records.length === 50 ? 'So‘nggi 50 ta' : `${records.length} ta`;
  if (!records.length) {
    list.replaceChildren(element('p', stir ? 'Ushbu STIR bo‘yicha hisobot topilmadi.' : 'Hali hisobot yo‘q. Birinchi tahlilni fayl yuklash orqali boshlang.', 'empty'));
    return;
  }
  list.replaceChildren(...records.map((record) => {
    const link = element('a', undefined, 'history-row');
    link.href = `/batches/${record.id}/`;
    const heading = element('span');
    heading.append(element('strong', record.company), element('small', `${record.year} · ${record.period} · STIR ${record.stir}`));
    link.append(heading, element('span', statuses[record.status] || record.status, `badge ${record.status.toLowerCase()}`));
    return link;
  }));
}

historyForm.addEventListener('submit', (event) => {
  event.preventDefault();
  notice('');
  loadHistory().catch((error) => notice(error.message, true));
});

function renderRows(items, columns) {
  const target = byId('report-rows');
  if (!items.length) {
    target.replaceChildren(element('p', 'Bu bo‘limda mos yozuvlar yo‘q.', 'empty'));
    return;
  }
  const table = element('table');
  const head = table.createTHead().insertRow();
  for (const [, label] of columns) {
    const cell = element('th', label);
    cell.scope = 'col';
    head.append(cell);
  }
  const body = table.createTBody();
  for (const item of items) {
    const row = body.insertRow();
    for (const [key] of columns) row.insertCell().textContent = item[key] || (item[key] === 0 ? '0' : '—');
  }
  target.replaceChildren(table);
}

async function loadRows() {
  const number = ++requestNumber;
  const query = new URLSearchParams({ group: currentGroup, q: search, page: String(page) });
  const { items, more } = await api(`${apiPath}/${detailId}/rows?${query}`);
  if (number !== requestNumber) return;
  renderRows(items, groups[currentGroup][1]);
  byId('page-number').textContent = `${page}-sahifa`;
  byId('prev-page').disabled = page <= 1;
  byId('next-page').disabled = !more;
  for (const button of byId('report-tabs').children) {
    const active = button.dataset.group === currentGroup;
    button.classList.toggle('active', active);
    button.setAttribute('aria-pressed', String(active));
  }
}

function refreshRows() {
  loadRows().catch((error) => notice(error.message, true));
}

function showResults(summary) {
  byId('results').hidden = false;
  byId('export').hidden = false;
  byId('export').href = `${apiPath}/${detailId}/export`;
  const metrics = [
    ['Tovarlar', summary.items], ['Qoldiq qiymati, so‘m', summary.endingValue],
    ['Kirimsiz sotuv, so‘m', summary.shortageValue], ['Markirovka tafovutlari', summary.discrepancies],
  ];
  byId('metrics').replaceChildren(...metrics.map(([label, value]) => {
    const box = element('div', undefined, 'metric');
    box.append(element('span', label), element('strong', displayNumber.format(value)));
    return box;
  }));
  const warnings = byId('report-warnings');
  warnings.hidden = !summary.warnings?.length;
  warnings.textContent = (summary.warnings || []).join(' ');
  byId('report-tabs').replaceChildren(...Object.entries(groups).map(([group, [label]]) => {
    const button = element('button', `${label} · ${summary[group]}`, 'button secondary');
    button.type = 'button';
    button.dataset.group = group;
    button.addEventListener('click', () => { currentGroup = group; page = 1; refreshRows(); });
    return button;
  }));
  refreshRows();
}

let pollTimer;
async function loadDetail() {
  clearTimeout(pollTimer);
  const record = await api(`${apiPath}/${detailId}`);
  currentDetail = record;
  byId('detail-company').textContent = record.company;
  byId('detail-meta').textContent = `STIR ${record.stir} · ${record.year} · ${record.period}`;
  const badge = byId('detail-status');
  badge.textContent = statuses[record.status] || record.status;
  badge.className = `badge ${record.status.toLowerCase()}`;
  const complete = record.status === 'COMPLETED';
  byId('job-panel').hidden = complete;
  byId('delete').hidden = record.status === 'PROCESSING';
  if (complete) { showResults(record.summary); return; }

  const stale = record.status === 'PROCESSING' && Date.now() - Date.parse(record.startedAt) >= 16 * 60 * 1000;
  const messages = {
    DRAFT: 'Hujjatlar to‘liq yuklanmagan. Qoralamani o‘chirib, qayta yuklang.',
    QUEUED: 'Tahlil navbatda. Agar boshlanmasa, quyidagi tugma orqali qayta urinib ko‘ring.',
    PROCESSING: stale ? 'Tahlil tugallanmagan. Uni qayta boshlash mumkin.' : 'Hujjatlar tekshirilmoqda. Natija tayyor bo‘lganda sahifada ko‘rinadi.',
    FAILED: record.summary?.error || 'Tahlil muvaffaqiyatsiz yakunlandi.',
    DELETING: 'O‘chirish tugallanmagan bo‘lsa, qayta urinib ko‘ring.',
  };
  byId('job-heading').textContent = statuses[record.status] || record.status;
  byId('job-copy').textContent = messages[record.status] || '';
  byId('retry').hidden = !stale && !['FAILED', 'QUEUED'].includes(record.status);
  if (['QUEUED', 'PROCESSING'].includes(record.status)) {
    pollTimer = setTimeout(() => loadDetail().catch((error) => notice(error.message, true)), 3500);
  }
}

byId('retry').addEventListener('click', async (event) => {
  event.currentTarget.disabled = true;
  const button = event.currentTarget;
  try {
    await startAudit(currentDetail.id);
    notice('Tahlil navbatga yuborildi.');
    await loadDetail();
  } catch (error) { notice(error.message, true); } finally { button.disabled = false; }
});

searchForm.addEventListener('submit', (event) => {
  event.preventDefault();
  search = new FormData(searchForm).get('q').trim();
  page = 1;
  refreshRows();
});
byId('prev-page').addEventListener('click', () => { if (page > 1) { page -= 1; refreshRows(); } });
byId('next-page').addEventListener('click', () => { page += 1; refreshRows(); });
const deleteDialog = byId('delete-dialog');
byId('delete').addEventListener('click', () => { deleteDialog.returnValue = ''; deleteDialog.showModal(); });
deleteDialog.addEventListener('close', async () => {
  if (deleteDialog.returnValue !== 'delete') return;
  try { await api(`${apiPath}/${detailId}`, { method: 'DELETE' }); location.assign('/'); }
  catch (error) { notice(error.message, true); }
});

async function init() {
  let callback;
  try { callback = await handleAuthCallback(); } catch (error) { notice(authMessage(error), true); }
  const user = callback?.user || await getUser();
  if (user && callback?.type !== 'recovery') { await openWorkspace(user); return; }

  show('auth');
  if (callback?.type === 'invite') { inviteToken = callback.token; populateAuth('invite'); }
  else if (callback?.type === 'recovery') populateAuth('recovery');
  else {
    populateAuth('login');
    const settings = await getSettings().catch(() => null);
    registrationOpen = settings?.disableSignup === false;
    if (authMode === 'login') populateAuth('login');
  }
}

init().catch((error) => notice(error.message, true));
