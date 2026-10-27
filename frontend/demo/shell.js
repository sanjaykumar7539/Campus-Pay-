// Shared EGS navigation. Only links to implemented screens appear here.
function icon(name) { return `<svg class="icon" aria-hidden="true"><use href="assets/icons.svg#${name}"/></svg>`; }
const shellRole = S.role === 'ADMIN' ? 'Admin' : 'Merchant';
const shellPage = document.body.dataset.page;
const shellHome = S.role === 'ADMIN' ? 'admin.html' : 'merchant.html';
const shellLinks = S.role === 'ADMIN' ? [
  ['overview','Overview','admin.html#overview'], ['user','Kiosks','admin.html#students'],
  ['store','Merchants','admin.html#merchants-section'], ['history','Transactions','admin.html#transactions'],
  ['report','Reports & ledger','admin.html#operations'], ['store','Merchant workspace','merchant.html'],
  ['settings','Account settings','account.html']
] : [
  ['overview','Overview','merchant.html#overview'], ['store','Ordering station','kiosk.html'],
  ['history','Recent orders','merchant.html#recent'], ['report','Fulfillment queue','merchant.html#queue'],
  ['settings','Account settings','account.html']
];
const shellSidebar = document.getElementById('shellSidebar');
if (shellSidebar) {
  shellSidebar.innerHTML = `<a class="sidebar-brand" href="${shellHome}">CampusPay<small>${shellRole.toUpperCase()} PORTAL</small></a><nav aria-label="Main navigation">${shellLinks.map(([i,l,h])=>`<a href="${h}">${icon(i)}<span>${l}</span></a>`).join('')}</nav><div class="sidebar-bottom"><div class="sidebar-support">${icon('help')}<strong>Need a hand?</strong><p>Your institution office can help with account and payment queries.</p></div><button type="button" onclick="logout()">${icon('logout')}<span>Sign out</span></button></div>`;
}
const shellHeader = document.getElementById('shellHeader');
if (shellHeader) shellHeader.innerHTML = `<a class="brand-link" href="${shellHome}" aria-label="CampusPay home"><img class="college-logo" src="assets/egs-logo.svg" alt="EGS Pillay Engineering College" width="414" height="48"></a><div class="workspace-label">${shellRole} workspace<small>EGSPEC · Nagapattinam</small></div><div class="topbar-account" id="who"></div>`;
function highlightNavigation() {
  if (!shellSidebar) return;
  const current = location.pathname.split('/').pop() + (location.hash || (shellPage === 'admin' || shellPage === 'merchant' ? '#overview' : ''));
  shellSidebar.querySelectorAll('nav a').forEach(a => {
    const active = a.getAttribute('href') === current;
    a.classList.toggle('active', active);
    if (active) a.setAttribute('aria-current','page'); else a.removeAttribute('aria-current');
  });
}
highlightNavigation();
window.addEventListener('hashchange', highlightNavigation);
