const accountForm = document.getElementById('accountForm');
const accountMsg = document.getElementById('accountMsg');
const saveAccount = document.getElementById('saveAccount');
const loginId = document.getElementById('loginId');
const currentPassword = document.getElementById('currentPassword');
const newPassword = document.getElementById('newPassword');
const confirmPassword = document.getElementById('confirmPassword');
if (requireLogin(['ADMIN', 'MERCHANT_STAFF'])) {
  document.getElementById('backLink').href = S.role === 'ADMIN' ? 'admin.html' : 'merchant.html';
  api('/auth/me').then(r => {
    loginId.value = r.data.username;
    document.getElementById('currentId').textContent = r.data.username;
    document.getElementById('currentRole').textContent = r.data.role === 'ADMIN' ? 'Administrator' : 'Merchant staff';
    saveAccount.disabled = false;
  }).catch(e => banner(accountMsg, 'err', e.message));
}
newPassword.addEventListener('input', () => { confirmPassword.required = newPassword.value.length > 0; });
accountForm.addEventListener('submit', async event => {
  event.preventDefault();
  if (saveAccount.disabled) return;
  accountMsg.innerHTML = '';
  if (newPassword.value !== confirmPassword.value) {
    banner(accountMsg, 'err', 'The new passwords do not match.'); confirmPassword.focus(); return;
  }
  if (new TextEncoder().encode(newPassword.value).length > 72) {
    banner(accountMsg, 'err', 'New password is too long. Use at most 72 UTF-8 bytes.'); return;
  }
  const body = { username: loginId.value.trim(), current_password: currentPassword.value };
  if (newPassword.value) body.new_password = newPassword.value;
  saveAccount.disabled = true; saveAccount.textContent = 'Saving changes…';
  try {
    await api('/auth/credentials', { method:'PATCH', body });
    clearSession();
    sessionStorage.setItem('cp_account_updated', '1');
    accountForm.reset();
    location.replace('login.html');
  } catch (e) {
    banner(accountMsg, 'err', e.message);
    saveAccount.disabled = false; saveAccount.textContent = 'Save changes & sign out →';
  }
});
