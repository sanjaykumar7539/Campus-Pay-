let paidRows = [], merchantNames = {}, ownMerchant=null, inventory=[];

if (requireLogin(['MERCHANT_STAFF', 'ADMIN'])) { load(); setInterval(load, 5000); }
const NEXT = { PAID: ['prepare', 'Start preparing'], PREPARING: ['ready', 'Mark ready'], READY: ['collect', 'Mark collected'] };
async function load() {
  try {
    const merchants = (await api('/merchants')).data;
    ownMerchant=merchants.length===1?merchants[0]:null;
    document.getElementById('toggleCanteen').hidden=S.role!=='MERCHANT_STAFF';
    document.getElementById('canteenStatus').textContent=ownMerchant?ownMerchant.name+' · '+(ownMerchant.status==='ACTIVE'&&ownMerchant.accepting_orders?'Open for orders':'Closed for new orders'):'Select a merchant account to manage availability';
    if(ownMerchant){const menu=(await api('/merchants/'+ownMerchant.id+'/menu')).data;const selected=document.getElementById('merchantCategory').value;document.getElementById('merchantCategory').innerHTML=menu.categories.map(c=>`<option value="${esc(c.id)}">${esc(c.name)}</option>`).join('');if(menu.categories.some(c=>c.id===selected))document.getElementById('merchantCategory').value=selected;}
    merchantNames = Object.fromEntries(merchants.map(m => [m.id, m.name]));
    document.getElementById('merchantName').textContent = merchants.length === 1 ? merchants[0].name : 'Your authorized merchants';
    const rows = (await api('/merchant/orders?limit=100')).data.filter(o => o.fulfillment);
    const stockRows=(await api('/products')).data; inventory=stockRows; const own=stockRows.filter(p=>merchants.some(m=>m.id===p.merchant_id)); document.getElementById('merchantStock').innerHTML=table([['Item',r=>r.name],['Price',r=>cu(r.price_cu)],['Stock',r=>String(r.stock_quantity)],['Status',r=>pill(r.stock_quantity===0?'SOLD_OUT':r.availability),true],['Controls',r=>`<button data-stock="${esc(r.id)}">Update stock / availability</button>`,true]],own);
    const paid = rows.filter(o => o.status === 'PAID');
    paidRows = paid;
    document.getElementById('merchantStats').innerHTML = `<div class="stat"><div class="stat-head"><span class="stat-icon">${icon('report')}</span><span>Recent collections</span></div><b>${cu(paid.reduce((sum,o) => sum+o.total_cu,0))}</b><span class="stat-hint">From the latest 100 orders</span></div><div class="stat"><div class="stat-head"><span class="stat-icon">${icon('history')}</span><span>Paid orders</span></div><b>${paid.length}</b><span class="stat-hint">In the latest 100 orders</span></div><div class="stat"><div class="stat-head"><span class="stat-icon">${icon('store')}</span><span>Ready to collect</span></div><b>${rows.filter(o=>o.fulfillment.status==='READY').length}</b><span class="stat-hint">In the recent queue</span></div>`;
    renderRecentOrders();
    const groups = ['PAID', 'PREPARING', 'READY', 'COLLECTED'];
    document.getElementById('cols').innerHTML = groups.map(g => '<div class="card"><h2>' + g + ' ' + pill(rows.filter(o => o.fulfillment.status === g).length) + '</h2>' +
      rows.filter(o => o.fulfillment.status === g).map(o => `<div class="item" style="margin-bottom:8px"><b>${esc(o.reference)}</b> — ${cu(o.total_cu)}<div class="muted">${o.items.map(i => esc(i.name) + ' ×' + i.quantity).join(', ')}</div>` +
        (NEXT[g] ? `<div class="row" style="margin-top:6px"><button class="primary" onclick="step('${esc(o.id)}','${NEXT[g][0]}')">${NEXT[g][1]}</button></div>` : '') + '</div>').join('') + '</div>').join('');
  } catch (e) { document.getElementById('cols').innerHTML = '<div class="banner err">' + esc(e.message) + '</div>'; }
}
async function step(id, action) { try { await api('/orders/' + id + '/fulfillment/' + action, { method: 'POST' }); } catch (e) { alert(e.message); } load(); }

function renderRecentOrders() {
  const query = document.getElementById('orderSearch').value.trim().toLowerCase();
  const visible = paidRows.filter(o => (o.reference + ' ' + (merchantNames[o.merchant_id] || '')).toLowerCase().includes(query));
  document.getElementById('recentList').innerHTML = visible.slice(0, 5).map(o => `<div class="activity-row"><span class="activity-icon">${icon('user')}</span><div><b>${esc(merchantNames[o.merchant_id] || 'Campus merchant')}</b><small>${esc(o.reference)} · ${esc(o.created_at.replace('T',' ').slice(0,16))}</small></div><strong>+ ${cu(o.total_cu)}</strong>${pill('PAID')}</div>`).join('') || '<div class="empty-state">' + (query ? 'No matching paid orders.' : 'No paid orders yet. Start an order to see activity here.') + '</div>';
}
document.getElementById('orderSearch').addEventListener('input', renderRecentOrders);

document.getElementById('toggleCanteen').onclick=async()=>{if(!ownMerchant)return;try{await api('/merchant/availability',{method:'PATCH',body:{status:ownMerchant.accepting_orders?'INACTIVE':'ACTIVE'}});await load()}catch(e){banner(document.getElementById('merchantMsg'),'err',e.message)}};
document.getElementById('addProduct').onsubmit=async e=>{e.preventDefault();e.submitter.disabled=true;try{const d=Object.fromEntries(new FormData(e.target));await api('/products',{method:'POST',body:{...d,price_cu:Number(d.price_cu),stock_quantity:Number(d.stock_quantity)}});e.target.reset();await load();banner(document.getElementById('merchantMsg'),'good','Menu item added')}catch(err){banner(document.getElementById('merchantMsg'),'err',err.message)}finally{e.submitter.disabled=false}};
document.getElementById('merchantStock').onclick=async e=>{const b=e.target.closest('[data-stock]');if(!b)return;const p=inventory.find(p=>p.id===b.dataset.stock);const stock=prompt('Stock quantity',p.stock_quantity);if(stock===null)return;const availability=prompt('Availability: AVAILABLE, SOLD_OUT or UNAVAILABLE',p.availability);if(availability===null)return;try{await api('/products/'+p.id,{method:'PATCH',body:{stock_quantity:Number(stock),availability}});await load()}catch(err){banner(document.getElementById('merchantMsg'),'err',err.message)}};
