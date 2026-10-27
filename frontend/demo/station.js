'use strict';
const el=id=>document.getElementById(id), money=n=>'\u20B9'+Number(n).toLocaleString('en-IN');
const safe=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let catalog=null, cart=new Map(), category='', ticket=null, processing=false, pollTimer=null, lastActivity=Date.now(), receiptTimer=null, uncertain=false, receipt=null, printing=false;
// Staff bearer credentials must never survive kiosk activation.
['cp_token','cp_role','cp_user'].forEach(k=>sessionStorage.removeItem(k));
async function request(path,method='GET',body){const r=await fetch('/api/v1'+path,{method,credentials:'same-origin',headers:{'Content-Type':'application/json','X-Kiosk-Request':'1'},body:body?JSON.stringify(body):undefined});let j;try{j=await r.json()}catch{throw Error('Server unavailable. Please ask staff for help.')}if(!r.ok){const e=Error(j.error?.message||'Request failed');e.status=r.status;e.code=j.error?.code;throw e}return j.data}
async function load(){try{catalog=await request('/kiosk/menu');el('setup').hidden=true;el('shop').hidden=false;el('canteenName').textContent=catalog.merchant.name;render()}catch(e){if(e.status===401){el('setup').hidden=false;el('shop').hidden=true}else el('notice').textContent=e.message}}

function productImage(p){
const photo=typeof MENU_IMAGES!=='undefined'?MENU_IMAGES[p.name]:null;
return `<div class="product-picture"><img src="${safe(photo?.url||'assets/menu-fallback.svg')}" alt="${safe(p.name)}" loading="lazy" decoding="async" referrerpolicy="no-referrer">${photo?`<a class="photo-credit" href="${safe(photo.source)}" target="_blank" rel="noopener noreferrer">${safe(photo.author)} - ${safe(photo.license)}</a>`:''}</div>`;
}
el('products').addEventListener('error',e=>{if(e.target.tagName==='IMG'&&!e.target.dataset.fallback){e.target.dataset.fallback='1';e.target.src='assets/menu-fallback.svg';}},true);

function render(){const cats=catalog.categories;el('categories').innerHTML=[['','All items'],...cats.map(c=>[c.id,c.name])].map(([id,name])=>`<button class="chip ${id===category?'active':''}" data-category="${safe(id)}">${safe(name)}</button>`).join('');const search=el('search').value.toLowerCase();const products=cats.filter(c=>!category||c.id===category).flatMap(c=>c.products).filter(p=>p.name.toLowerCase().includes(search));el('products').innerHTML=products.map(p=>`<article class="product">${productImage(p)}<h3>${safe(p.name)}</h3><p>${safe(p.description||'Fresh from your campus canteen')}</p><div class="product-bottom"><strong>${money(p.price_cu)}</strong><button class="add" data-add="${safe(p.id)}" ${p.availability!=='AVAILABLE'||p.stock_quantity<1||(catalog.merchant.status!=='ACTIVE'||!catalog.merchant.accepting_orders)?'disabled':''}>${p.availability==='AVAILABLE'&&p.stock_quantity>0?'Add +':'Sold out'}</button></div></article>`).join('')||'<p class="empty">No items available.</p>';renderCart()}
function renderCart(){el('cart').innerHTML=[...cart.values()].map(p=>`<div class="cart-line"><b>${safe(p.name)}</b><div><span>${money(p.price_cu*p.quantity)}</span><span class="quantity"><button aria-label="Remove one ${safe(p.name)}" data-qty="${safe(p.id)}" data-delta="-1">âˆ’</button>${p.quantity}<button aria-label="Add one ${safe(p.name)}" data-qty="${safe(p.id)}" data-delta="1">+</button></span></div></div>`).join('')||'<p class="empty">Your order starts here.<br>Add something delicious.</p>';el('total').textContent=money([...cart.values()].reduce((s,p)=>s+p.quantity*p.price_cu,0));el('checkout').disabled=!cart.size||(catalog.merchant.status!=='ACTIVE'||!catalog.merchant.accepting_orders)||processing}
el('products').addEventListener('click',e=>{const b=e.target.closest('[data-add]');if(!b)return;const p=catalog.categories.flatMap(c=>c.products).find(p=>p.id===b.dataset.add);const qty=(cart.get(p.id)?.quantity||0)+1;if(qty<=Math.min(p.stock_quantity,100))cart.set(p.id,{...p,quantity:qty});renderCart()});
el('categories').addEventListener('click',e=>{const b=e.target.closest('[data-category]');if(b){category=b.dataset.category;render()}});
el('cart').addEventListener('click',e=>{const b=e.target.closest('[data-qty]');if(!b)return;const p=cart.get(b.dataset.qty);p.quantity=Math.min(p.quantity+Number(b.dataset.delta),p.stock_quantity,100);if(!p.quantity)cart.delete(p.id);renderCart()});el('search').oninput=render;el('clearCart').onclick=()=>{cart.clear();renderCart()};
el('setupForm').onsubmit=async e=>{e.preventDefault();const b=e.submitter;b.disabled=true;try{const data=Object.fromEntries(new FormData(e.target));data.device_id='DEMO-KIOSK-01';data.authentication_mode='SCANNER';data.receipt_mode='THERMAL';if(data.authentication_mode==='AUTO'&&typeof MobileAuth!=='undefined'&&MobileAuth.isMobile())data.authentication_mode='MOBILE';await request('/kiosk/setup','POST',{...data,institution_code:'EGS-ENGG'});e.target.reset();await load()}catch(err){el('setupMsg').textContent=err.message}finally{b.disabled=false}};
async function startCheckout(){
if(!cart.size||ticket)return;
processing=true;el('mobileScan').hidden=true;renderCart();el('retryScanner').disabled=true;el('notice').textContent='';
el('scanTitle').textContent='Scan your enrolled finger';
el('scanHelp').textContent='Place your enrolled finger on the reader. One enrolled fingerprint scan identifies and authorizes payment.';
el('scanAmount').textContent='Order total: '+money([...cart.values()].reduce((sum,p)=>sum+p.quantity*p.price_cu,0));
el('scanStatus').textContent='Connecting to fingerprint reader…';el('step1').className=el('step2').className='';
el('retryPay').hidden=true;el('retryScanner').hidden=true;el('cancelScan').disabled=false;el('cancelScan').textContent='Return to menu';
if(!el('scanDialog').open)el('scanDialog').showModal();
try{
const mobile=catalog.authentication_mode==='MOBILE'||(catalog.authentication_mode!=='SCANNER'&&typeof MobileAuth!=='undefined'&&MobileAuth.isMobile());
if(mobile&&!await MobileAuth.available())throw Error('Mobile authentication requires HTTPS and a device screen lock/passkey.');
ticket=await request(mobile?'/kiosk/mobile/checkouts':'/kiosk/checkouts','POST',{items:[...cart.values()].map(p=>({product_id:p.id,quantity:p.quantity}))});
sessionStorage.setItem('cp_checkout',ticket.id);uncertain=false;el('scanAmount').textContent='Order total: '+money(ticket.total_cu);
el('scanStatus').textContent='Waiting for your fingerprint scan.';el('cancelScan').textContent='Cancel order';if(mobile){await mobileScan()}else poll();
}catch(e){
el('scanStatus').textContent=e.code==='SCANNER_OFFLINE'?'Fingerprint reader is offline or unavailable in this test environment. Connect the integrated reader and retry. No order has been completed and no money has been deducted.':e.message;
el('retryScanner').hidden=e.code!=='SCANNER_OFFLINE';
}finally{el('retryScanner').disabled=false;}}
el('checkout').onclick=startCheckout;el('retryScanner').onclick=startCheckout;
async function mobileScan(){
el('mobileScan').hidden=true;el('mobileScan').disabled=true;el('cancelScan').disabled=true;
try{const opts=await request('/kiosk/checkouts/'+ticket.id+'/mobile/options','POST');
el('scanTitle').textContent=ticket.status==='SECOND_SCAN'?'Continue phone confirmation':'Verify with your phone';
el('scanHelp').textContent='Use this phone enrolled passkey. The phone chooses fingerprint, face or screen lock.';
const credential=await MobileAuth.run(opts.options);
ticket=await request('/kiosk/checkouts/'+ticket.id+'/mobile/verify','POST',{ceremony_id:opts.ceremony_id,credential});
if(ticket.status==='READY'){el('step2').className='done';await completePayment()}else{el('step1').className='done';el('scanStatus').textContent='First verification successful. Continue mobile confirmation to pay '+money(ticket.total_cu);el('mobileScan').textContent='Confirm payment with mobile sensor';el('mobileScan').hidden=false;}
}catch(e){if(e.name!=='NotAllowedError'){try{const recovered=await request('/kiosk/checkouts/'+ticket.id);ticket=recovered;if(['READY','CONSUMED'].includes(ticket.status)){await completePayment();return;}}catch{}}el('scanStatus').textContent=e.name==='NotAllowedError'?'Authentication cancelled or timed out. No payment was taken.':e.message;el('mobileScan').hidden=false;}finally{el('mobileScan').disabled=false;if(!uncertain)el('cancelScan').disabled=false;}
}
el('mobileScan').onclick=mobileScan;
async function poll(){clearTimeout(pollTimer);if(!ticket)return;try{ticket=await request('/kiosk/checkouts/'+ticket.id);if(ticket.auth_method==='MOBILE'&&['FIRST_SCAN','SECOND_SCAN'].includes(ticket.status)){el('mobileScan').hidden=false;el('scanStatus').textContent='Continue mobile authentication to authorize payment.';return;}if(ticket.status==='SECOND_SCAN'){el('step1').className='done';el('scanTitle').textContent='Additional fingerprint requested';el('scanHelp').textContent='Additional verification requested for '+money(ticket.total_cu)+'.'}if(ticket.status==='READY'||ticket.status==='CONSUMED'){el('step2').className='done';await completePayment();return}if(['FAILED','EXPIRED','CANCELLED','FINISHED'].includes(ticket.status)){el('scanStatus').textContent=ticket.status==='FAILED'?'Fingerprint did not match. No payment was taken. Please ask staff if needed.':'This scan session ended. Start a new order.';el('cancelScan').textContent='Return to menu';return}pollTimer=setTimeout(poll,1500)}catch(e){el('scanStatus').textContent=e.message;pollTimer=setTimeout(poll,4000)}}
async function completePayment(){const recovering=uncertain||ticket.status==='CONSUMED';uncertain=true;el('cancelScan').disabled=true;el('retryPay').hidden=true;el('scanTitle').textContent='Checking paymentâ€¦';try{const out=await request('/kiosk/checkouts/'+ticket.id+'/pay','POST');uncertain=false;receipt=out.receipt;el('scanDialog').close();el('receiptPaper').innerHTML=receipt?`<p class="eyebrow">PAYMENT SUCCESSFUL</p><h2>${safe(receipt.merchant)}</h2><p>${safe(receipt.institution)}</p><p>${safe(receipt.receipt_number)}<br>Order: ${safe(receipt.order_reference)}</p><table>${receipt.lines.map(i=>`<tr><td>${safe(i.name)} Ã— ${i.quantity}</td><td>${money(i.line_total_cu)}</td></tr>`).join('')}</table><h2>Paid ${money(receipt.amount_cu)}</h2><p class="balance">Balance: ${money(receipt.balance_after_cu)}</p><p>${safe(receipt.paid_at)}</p><p class="fine">${safe(receipt.warning)}</p>`:`<h2>Payment completed</h2><p>Order: ${safe(out.order?.reference)}</p><p>Balance: ${money(out.balance_after_cu)}</p><p>Receipt is temporarily unavailable. Ask staff to retrieve it. Do not pay again.</p>`;el('printReceipt').disabled=!receipt;el('receiptNote').textContent='Print now, or this station returns to the menu in 15 seconds. Staff can retrieve your receipt if printing fails.';el('receiptDialog').showModal();receiptTimer=setTimeout(finish,15000)}catch(e){el('scanStatus').textContent=e.status&&e.status<500&&!(recovering&&[401,403].includes(e.status))?'Payment refused: '+e.message:'Connection interrupted. Check the payment result; do not place another order.';if(e.status&&e.status<500&&e.status!==429&&!(recovering&&[401,403].includes(e.status))){uncertain=false;el('cancelScan').disabled=false;el('cancelScan').textContent='Return to menu'}else el('retryPay').hidden=false}}
el('retryPay').onclick=completePayment;
async function cancel(){if(uncertain)return;if(!ticket){processing=false;el('scanDialog').close();renderCart();return;}clearTimeout(pollTimer);if(ticket){try{await request('/kiosk/checkouts/'+ticket.id+'/cancel','POST')}catch(e){el('scanStatus').textContent=e.message;return}}finish()}
function finish(){if(ticket)request('/kiosk/checkouts/'+ticket.id+'/finish','POST').catch(()=>{});clearTimeout(pollTimer);clearTimeout(receiptTimer);ticket=null;receipt=null;processing=false;uncertain=false;sessionStorage.removeItem('cp_checkout');cart.clear();for(const id of ['scanDialog','receiptDialog'])if(el(id).open)el(id).close();el('receiptPaper').replaceChildren();el('search').value='';category='';el('cancelScan').textContent='Cancel order';lastActivity=Date.now();load()}
el('cancelScan').onclick=cancel;el('finish').onclick=finish;
async function thermalPrint(){
clearTimeout(receiptTimer);printing=true;el('printReceipt').disabled=true;el('finish').disabled=true;
try{
 let job=await request('/kiosk/checkouts/'+ticket.id+'/print','POST');
 const deadline=Date.now()+95000;
 while(['QUEUED','CLAIMED'].includes(job.state)&&Date.now()<deadline){
  el('receiptNote').textContent='Sending receipt to thermal printer. Payment is already complete.';
  await new Promise(resolve=>setTimeout(resolve,1500));job=await request('/kiosk/checkouts/'+ticket.id+'/print');
 }
 if(job.state==='SUBMITTED'){el('receiptNote').textContent='Receipt sent to printer. Collect the paper; ask staff if it did not print.';printing=false;finish();}
 else throw Error('Print delivery is '+job.state+'. Do not pay again. Ask staff for a receipt copy; automatic reprinting is blocked to avoid duplicates.');
}catch(e){el('receiptNote').textContent=e.message+' Your paid receipt is retained.';}
finally{printing=false;el('printReceipt').disabled=!receipt;el('finish').disabled=false;}
}
el('printReceipt').onclick=()=>{if(catalog?.receipt_mode==='THERMAL'){thermalPrint();return;}clearTimeout(receiptTimer);printing=true;window.print();if(printing){printing=false;finish()}};addEventListener('afterprint',()=>{if(printing){printing=false;finish()}});
el('unlockButton').onclick=()=>{el('unlockForm').reset();el('unlockMsg').textContent='';el('unlockDialog').showModal()};el('closeUnlock').onclick=()=>{el('unlockForm').reset();el('unlockDialog').close()};
el('unlockForm').onsubmit=async e=>{e.preventDefault();try{await request('/kiosk/logout','POST',Object.fromEntries(new FormData(e.target)));sessionStorage.removeItem('cp_checkout');e.target.reset();location.replace('login.html')}catch(err){el('unlockMsg').textContent=err.message;e.target.elements.password.value=''}};
for(const id of ['scanDialog','receiptDialog'])el(id).addEventListener('cancel',e=>e.preventDefault());
for(const type of ['pointerdown','keydown'])addEventListener(type,()=>lastActivity=Date.now());
setInterval(()=>{if(catalog&&!el('shop').hidden&&!ticket&&!el('unlockDialog').open&&Date.now()-lastActivity>60000){cart.clear();el('search').value='';renderCart();lastActivity=Date.now()}if(!processing&&el('setup').hidden)load()},15000);
async function boot(){await load();const saved=sessionStorage.getItem('cp_checkout');if(saved&&!el('shop').hidden){ticket={id:saved};processing=true;el('scanDialog').showModal();poll()}}
boot();

