// CampusPay P1 demo client. All money decisions are made by the server; this file never computes a payable amount.
const API = '/api/v1';
const S = { get token() { return sessionStorage.getItem('cp_token'); }, get role() { return sessionStorage.getItem('cp_role'); },
  get user() { return sessionStorage.getItem('cp_user'); } };
function esc(v) { return String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); }
function cu(n) { return '\u20B9' + Number(n).toLocaleString('en-IN'); }
function uuid() { return (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random().toString(16).slice(2)); }
async function api(path, { method = 'GET', body, headers = {} } = {}) {
  const h = { 'Content-Type': 'application/json', ...headers };
  if (S.token) h.Authorization = 'Bearer ' + S.token;
  const res = await fetch(API + path, { method, headers: h, body: body ? JSON.stringify(body) : undefined });
  let json = {}; try { json = await res.json(); } catch (e) { /* non-JSON */ }
  if (!res.ok || json.success === false) {
    if (res.status === 401 && S.token) { clearSession(); location.href = 'login.html'; }
    const err = new Error((json.error && json.error.message) || res.statusText); err.code = json.error && json.error.code;
    err.details = json.error && json.error.details; err.status = res.status; throw err;
  }
  return json;
}
function requireLogin(roles) {
  if (!S.token || (roles && !roles.includes(S.role))) { location.href = 'login.html'; return false; }
  const bar = document.getElementById('who');
  if (bar) bar.innerHTML = `<a class="account-link" href="account.html" aria-label="Account settings for ${esc(S.user)}"><span class="avatar">${esc((S.user || 'CP').slice(0,2).toUpperCase())}</span><span><b>${esc(S.user)}</b><small>${S.role === 'ADMIN' ? 'Administrator' : 'Merchant staff'}</small></span></a>`;
  return true;
}
function clearSession() { ['cp_token','cp_role','cp_user'].forEach(key => sessionStorage.removeItem(key)); }
function logout() { clearSession(); location.href = 'login.html'; }
function banner(el, kind, text) { el.innerHTML = '<div class="banner ' + kind + '">' + esc(text) + '</div>'; }
function pill(s) { return '<span class="pill ' + esc(s) + '">' + esc(s) + '</span>'; }
function table(cols, rows) {
  return '<table><tr>' + cols.map(c => '<th>' + esc(c[0]) + '</th>').join('') + '</tr>' +
    rows.map(r => '<tr>' + cols.map(c => '<td>' + (c[2] ? c[1](r) : esc(c[1](r))) + '</td>').join('') + '</tr>').join('') + '</table>';
}
function receiptText(r) {
  const lines = (r.lines || []).map(l => `  ${l.name} x${l.quantity} @ ${l.unit_price_cu} = ${l.line_total_cu} CU`).join('\n');
  return `${r.institution}\n${r.merchant}\n--------------------------------\nReceipt : ${r.receipt_number}\nOrder   : ${r.order_reference || '-'}\n` +
    `Payment : ${r.payment_reference}\nCustomer: ${r.customer.name} (${r.customer.campus_id})\n${lines}\n--------------------------------\n` +
    `TOTAL   : \u20B9${r.amount_cu}\nBalance : ${r.balance_after_cu == null ? 'See wallet history' : '\u20B9'+r.balance_after_cu}\nPaid at : ${r.paid_at}\n${r.warning || 'Keep this receipt until collection. Do not pay again if printing fails.'}`;
}

document.querySelectorAll('[data-password-toggle]').forEach(button => {
  button.addEventListener('click', () => {
    const input = document.getElementById(button.dataset.passwordToggle);
    const show = input.type === 'password';
    input.type = show ? 'text' : 'password';
    button.textContent = show ? 'Hide' : 'Show';
    button.setAttribute('aria-pressed', String(show));
    button.setAttribute('aria-label', (show ? 'Hide' : 'Show') + ' password');
  });
});
