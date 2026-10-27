if(!requireLogin(['STUDENT'])) throw new Error('login required');
const q=id=>document.getElementById(id);
let profile,wallet,merchants=[],catalog=[],cart={},pendingOrders=[],pinDigits='',checkoutSnapshot=[];
const money=n=>'\u20B9'+Number(n).toLocaleString('en-IN');
const slotOrder=['food','snacks','stationery'];
const slotLabel={food:'Food',snacks:'Snacks',stationery:'Stationery'};

init();
setInterval(refreshLive,5000);

async function init(){
  profile=(await api('/student/me')).data;
  wallet=(await api('/wallet/me')).data;
  q('studentName').textContent=profile.name;
  q('studentId').textContent=profile.campus_id;
  q('balance').textContent=money(wallet.available_cu);
  await loadCatalog();
  renderMenu();
  bindCategoryRail();
}

function classify(categoryName,merchantCategory){
  const c=(categoryName||'').toLowerCase();
  const m=(merchantCategory||'').toLowerCase();
  if(m.includes('stationery')||c.includes('notebook')||c.includes('writing')||c.includes('stationery')) return 'stationery';
  if(c.includes('snack')) return 'snacks';
  return 'food';
}

async function loadCatalog(){
  merchants=(await api('/merchants')).data;
  const active=merchants.filter(m=>m.status==='ACTIVE');
  const menus=await Promise.all(active.map(async m=>{
    try{return {merchant:m,menu:(await api('/merchants/'+m.id+'/menu')).data};}
    catch(_e){return {merchant:m,menu:{categories:[]}};}
  }));
  catalog=[];
  for(const row of menus){
    for(const cat of (row.menu.categories||[])){
      for(const p of (cat.products||[])){
        catalog.push({...p,merchant_id:row.merchant.id,merchant_name:row.merchant.name,merchant_category:row.merchant.category,source_category:cat.name,slot:classify(cat.name,row.merchant.category)});
      }
    }
  }
}

async function refreshLive(){
  try{
    wallet=(await api('/wallet/me')).data;
    q('balance').textContent=money(wallet.available_cu);
    if(!q('shop').hidden){
      await loadCatalog();
      const live=Object.fromEntries(catalog.map(p=>[p.id,p]));
      for(const id of Object.keys(cart)){
        const p=live[id];
        if(!p||p.availability!=='AVAILABLE'||p.stock_quantity<=0) delete cart[id];
        else cart[id]=Math.min(cart[id],p.stock_quantity);
      }
      renderMenu();
    }
  }catch(_e){}
}

function products(){return catalog;}
function total(){return Object.entries(cart).reduce((s,[id,n])=>s+(products().find(p=>p.id===id)?.price_cu||0)*n,0);}
function count(){return Object.values(cart).reduce((a,b)=>a+b,0);}
function selectedItems(){return Object.entries(cart).map(([id,quantity])=>{const p=products().find(x=>x.id===id);return p?{...p,quantity,line_total_cu:p.price_cu*quantity}:null}).filter(Boolean);}

function renderMenu(){
  q('menu').innerHTML=slotOrder.map(slot=>{
    const items=catalog.filter(p=>p.slot===slot);
    return `<section class="menu-category unified-section" id="slot-${slot}" data-slot="${slot}"><h2>${slotLabel[slot]}</h2><div class="product-grid">${items.length?items.map(p=>{
      const off=p.availability!=='AVAILABLE'||p.stock_quantity<=0;
      const n=cart[p.id]||0;
      return `<article class="product-card ${off?'off':''}"><h3>${esc(p.name)}</h3><div class="price">${money(p.price_cu)}</div><div class="stock ${off?'bad':''}">${off?'Unavailable':p.stock_quantity+' available'}</div>${off?'':`<div class="qty"><button type="button" data-sub="${p.id}" aria-label="Remove one">−</button><b>${n}</b><button type="button" data-add="${p.id}" ${n>=p.stock_quantity?'disabled':''} aria-label="Add one">+</button></div>`}</article>`;
    }).join(''):'<div class="empty-slot">No items available</div>'}</div></section>`;
  }).join('');
  q('menu').querySelectorAll('[data-add]').forEach(b=>b.onclick=()=>change(b.dataset.add,1));
  q('menu').querySelectorAll('[data-sub]').forEach(b=>b.onclick=()=>change(b.dataset.sub,-1));
  const n=count(),t=total();
  q('cartCount').textContent=n+' item'+(n===1?'':'s');
  q('cartTotal').textContent=money(t);
  const available=Number(wallet?.available_cu||0);
  const enoughBalance=n>0 && available>=t;
  q('payNow').textContent=!n?'Pay '+money(0):(enoughBalance?'Pay '+money(t):'Available '+money(available)+' • Need '+money(t));
  q('payNow').disabled=!n || !enoughBalance;
}

function change(id,d){
  const p=products().find(x=>x.id===id);if(!p)return;
  cart[id]=Math.max(0,Math.min(p.stock_quantity,(cart[id]||0)+d));
  if(!cart[id]) delete cart[id];
  renderMenu();
}

function bindCategoryRail(){
  document.querySelectorAll('.category-slot').forEach(b=>b.onclick=()=>{
    document.querySelectorAll('.category-slot').forEach(x=>x.classList.toggle('active',x===b));
    document.getElementById('slot-'+b.dataset.jump)?.scrollIntoView({behavior:'smooth',block:'start'});
  });
}

q('payNow').onclick=async()=>{
  if(!count())return;
  try{
    wallet=(await api('/wallet/me')).data;
    q('balance').textContent=money(wallet.available_cu);
  }catch(_e){}
  const amount=total();
  if(Number(wallet?.available_cu||0)<amount){
    renderMenu();
    return;
  }
  checkoutSnapshot=selectedItems();
  pendingOrders=[];
  pinDigits='';
  renderPay();
};

function renderPinDots(){
  const dots=q('pinDots');if(!dots)return;
  dots.innerHTML=[0,1,2,3].map(i=>`<span class="pin-dot ${i<pinDigits.length?'filled':''}">${i<pinDigits.length?'•':''}</span>`).join('');
  const btn=q('finalPay');if(btn)btn.disabled=pinDigits.length!==4;
}

function renderPay(msg=''){
  q('shop').hidden=true;q('pay').hidden=false;
  const amount=checkoutSnapshot.reduce((s,i)=>s+i.line_total_cu,0);
  q('pay').innerHTML=`<div class="pay-card touch-pay"><button class="button ghost template-back" id="backShop">← Back</button><h1>Enter 4-digit PIN</h1><div class="pin-dots" id="pinDots"></div><div id="pmsg">${msg?`<div class="pin-error">${esc(msg)}</div>`:''}</div><div class="pin-keypad" aria-label="Payment PIN keypad">${[1,2,3,4,5,6,7,8,9].map(n=>`<button type="button" data-key="${n}">${n}</button>`).join('')}<button type="button" class="pin-action-key" data-action="clear" aria-label="Clear PIN">C</button><button type="button" data-key="0">0</button><button type="button" class="pin-action-key pin-backspace" data-action="back" aria-label="Delete last digit">⌫</button></div><button class="button primary final-touch-pay" id="finalPay" disabled>Pay ${money(amount)}</button></div>`;
  q('backShop').onclick=()=>{pendingOrders=[];pinDigits='';q('pay').hidden=true;q('shop').hidden=false;};
  q('pay').querySelectorAll('[data-key]').forEach(b=>b.onclick=()=>{if(pinDigits.length<4){pinDigits+=b.dataset.key;renderPinDots();}});
  q('pay').querySelector('[data-action="clear"]').onclick=()=>{pinDigits='';renderPinDots();};
  q('pay').querySelector('[data-action="back"]').onclick=()=>{pinDigits=pinDigits.slice(0,-1);renderPinDots();};
  q('finalPay').onclick=submitPay;
  renderPinDots();
}

async function ensureOrders(){
  if(pendingOrders.length)return pendingOrders;
  const byMerchant={};
  for(const item of checkoutSnapshot){
    (byMerchant[item.merchant_id]??=[]).push({product_id:item.id,quantity:item.quantity});
  }
  const made=[];
  for(const [merchant_id,items] of Object.entries(byMerchant)){
    const o=(await api('/orders',{method:'POST',body:{merchant_id,identity:{kind:'CAMPUS_ID',value:profile.campus_id},items,client_request_key:uuid()}})).data;
    made.push({order:o,paid:false});
  }
  pendingOrders=made;
  return pendingOrders;
}

async function submitPay(){
  if(pinDigits.length!==4)return;
  const btn=q('finalPay');btn.disabled=true;
  const amount=checkoutSnapshot.reduce((s,i)=>s+i.line_total_cu,0);
  try{
    wallet=(await api('/wallet/me')).data;
    q('balance').textContent=money(wallet.available_cu);
  }catch(_e){}
  const balanceBefore=Number(wallet.available_cu);
  if(balanceBefore<amount){
    pinDigits='';
    q('pay').hidden=true;
    q('shop').hidden=false;
    renderMenu();
    return;
  }
  const results=[];
  try{
    const rows=await ensureOrders();
    for(const row of rows){
      if(row.paid)continue;
      const r=await api('/orders/'+row.order.id+'/pay',{method:'POST',headers:{'Idempotency-Key':uuid()},body:{identity:{kind:'CAMPUS_ID',value:profile.campus_id},pin:pinDigits}});
      row.paid=true;row.result=r.data;results.push(r.data);
      wallet.available_cu=r.data.balance_after_cu;
      q('balance').textContent=money(wallet.available_cu);
    }
    const allResults=rows.map(r=>r.result).filter(Boolean);
    renderSuccess(allResults,balanceBefore);
  }catch(e){
    if(e.code==='PIN_INVALID'||e.code==='INVALID_PIN_FORMAT'){
      pinDigits='';
      renderPay('Invalid PIN');
      return;
    }
    const pmsg=q('pmsg');if(pmsg)pmsg.innerHTML=`<div class="pin-error">${esc(e.message||'Payment failed')}</div>`;
    btn.disabled=false;
  }
}

function nextStudent(){
  clearSession();
  location.href='login.html?role=student';
}

function printReceipt(){window.print();}

function renderSuccess(results,balanceBefore){
  const paid=checkoutSnapshot.reduce((s,i)=>s+i.line_total_cu,0);
  const balance=Number(wallet.available_cu);
  const merchantNames=[...new Set(checkoutSnapshot.map(i=>i.merchant_name))].join(', ');
  const refs=results.map(d=>d.payment?.id).filter(Boolean).join(', ');
  q('pay').innerHTML=`<div class="pay-card success receipt-print" id="successReceipt"><div class="receipt-head"><img src="assets/egs-logo.svg" alt="EGS Pillay Engineering College"><div><h1>Payment successful</h1><p>CampusPay receipt</p></div></div><div class="receipt-meta"><div><span>College</span><strong>EGS Pillay Engineering College</strong></div><div><span>Canteen / Store</span><strong>${esc(merchantNames||'Campus Store')}</strong></div><div><span>Kiosk name</span><strong>${esc(profile.name)}</strong></div><div><span>Kiosk ID</span><strong>${esc(profile.campus_id)}</strong></div>${refs?`<div><span>Reference</span><strong>${esc(refs)}</strong></div>`:''}</div><div class="receipt-lines">${checkoutSnapshot.map(i=>`<div class="receipt-line"><span>${esc(i.name)} ×${i.quantity}</span><strong>${money(i.line_total_cu)}</strong></div>`).join('')}</div><div class="receipt-totals"><div><span>Balance before payment</span><strong>${money(balanceBefore)}</strong></div><div><span>Order amount</span><strong>− ${money(paid)}</strong></div><div class="available"><span>Available balance</span><strong>${money(balance)}</strong></div></div><div class="receipt-actions no-print"><button class="button ghost" id="printReceipt">Print receipt</button><button class="button primary" id="nextStudent">Next Kiosk</button></div></div>`;
  q('printReceipt').onclick=printReceipt;
  q('nextStudent').onclick=nextStudent;
}
