const $=id=>document.getElementById(id);let students=[],merchants=[],devices=[],products=[],enrollId=null,enrollTimer=null;
const button=(action,id,label)=>`<button class="ghost" data-action="${action}" data-id="${esc(id)}">${esc(label)}</button>`;
const options=(rows,label)=>rows.map(r=>`<option value="${esc(r.id)}">${esc(label(r))}</option>`).join('');
function notify(text,error=false){banner($('loadMsg'),error?'err':'good',text)}
async function load(){try{const [d,s,m,k,p,h,orders]=await Promise.all(['/reports/dashboard','/admin/students','/merchants','/devices','/products','/health','/merchant/orders?limit=100'].map(x=>api(x).then(r=>r.data)));students=s;merchants=m;devices=k;products=p;const totals=d.totals;$('stats').innerHTML=[[s.length,'Kiosks'],[m.filter(r=>r.status==='ACTIVE').length,'Open canteens'],[cu(totals.payments_by_status.COMPLETED?.amount_cu||0),'Collections'],[cu(totals.wallet_available_cu),'Wallet balance']].map(([n,l])=>`<div class="stat"><span>${esc(l)}</span><b>${esc(n)}</b></div>`).join('');$('health').textContent='Database revision: '+h.schema_revision+' · Demo funding: '+h.demo_funding;renderStudents();updateStudentPreview("moneyStudent", "moneyStudentInfo");await loadRefunds();updateStudentPreview("enrollStudent", "enrollStudentInfo");updateStudentPreview("withdrawStudent", "withdrawStudentInfo");$('enrollDevice').innerHTML=options(k.filter(r=>r.status==='ACTIVE'),r=>r.name);$('deviceMerchant').innerHTML=options(m,r=>r.name);const selected=$('productMerchant').value;$('productMerchant').innerHTML=options(m,r=>r.name);if(m.some(x=>x.id===selected))$('productMerchant').value=selected;await categories();$('merchants').innerHTML=table([['Canteen',r=>r.name],['Category',r=>r.category],['Status',r=>pill(r.status),true],['Actions',r=>button('merchant-toggle',r.id,r.status==='ACTIVE'?'Close':'Open')+button('merchant-edit',r.id,'Rename'),true]],m);$('kiosks').innerHTML=table([['Station',r=>r.name],['Station ID',r=>r.id],['Status',r=>r.status],['Actions',r=>button('device-toggle',r.id,r.status==='ACTIVE'?'Disable':'Enable')+button('scanner-key',r.id,'Provision / rotate scanner key')+button('printer-key',r.id,'Provision / rotate printer key')+button('hardware-status',r.id,'Device status'),true]],k);$('products').innerHTML=table([['Canteen',r=>r.merchant],['Item',r=>r.name],['Price',r=>cu(r.price_cu)],['Stock',r=>r.stock_quantity],['Status',r=>r.availability],['Actions',r=>button('product-edit',r.id,'Edit stock / price')+button('product-toggle',r.id,r.availability==='AVAILABLE'?'Disable':'Activate'),true]],p);$('payments').innerHTML=table([['Kiosk',r=>r.student],['Canteen',r=>r.merchant],['Amount',r=>cu(r.amount_cu)],['Status',r=>pill(r.status),true]],d.recent_payments);$('transactionList').innerHTML=table([['Order',r=>r.reference],['Items',r=>r.items.map(i=>i.name+' ×'+i.quantity).join(', ')],['Amount',r=>cu(r.total_cu)],['Status',r=>r.status],['Receipt',r=>r.status==='PAID'?button('receipt',r.id,'Retrieve receipt'):'—',true]],orders);$('audit').innerHTML=table([['Time',r=>r.created_at],['Event',r=>r.event_type],['Entity',r=>r.entity_type]],d.recent_audit)}catch(e){notify(e.message,true)}}
function renderStudents(){const q=$('studentSearch').value.toLowerCase();$('wallets').innerHTML=table([['Kiosk ID',r=>r.campus_id],['Name',r=>r.name],['Fingerprint',r=>pill(r.fingerprint_status),true],['Balance',r=>cu(r.available_cu)],['Actions',r=>r.fingerprint_status==='ACTIVE'?button('revoke',r.id,'Revoke fingerprint'):'Enroll using form above',true]],students.filter(s=>(s.name+' '+s.campus_id).toLowerCase().includes(q)))}
async function categories(){const id=$('productMerchant').value;if(!id)return;const menu=(await api('/merchants/'+id+'/menu')).data;$('productCategory').innerHTML=options(menu.categories,r=>r.name)}
function submit(id,fn){$(id).onsubmit=async e=>{e.preventDefault();e.submitter.disabled=true;try{await fn(Object.fromEntries(new FormData(e.target)));notify('Saved successfully.');e.target.reset();await load()}catch(err){notify(err.message,true)}finally{e.submitter.disabled=false}}}
submit('studentForm',d=>api('/admin/students',{method:'POST',body:d}));submit('merchantForm',d=>api('/merchants',{method:'POST',body:d}));submit('deviceForm',d=>api('/devices',{method:'POST',body:d}));submit('productForm',d=>api('/products',{method:'POST',body:{...d,price_cu:Number(d.price_cu),stock_quantity:Number(d.stock_quantity)}}));
$('enrollForm').onsubmit=async e=>{e.preventDefault();if(enrollId)return;const d=Object.fromEntries(new FormData(e.target));e.submitter.disabled=true;try{const student=findStudentByKioskId(d.student);if(!student)throw Error('Invalid Kiosk ID. Student not found.');const r=(await api('/admin/students/'+student.id+'/fingerprint',{method:'POST',body:{device_id:d.device_id,consent_confirmed:d.consent==='on'}})).data;enrollId=r.id;$('cancelEnroll').hidden=false;pollEnroll()}catch(err){notify(err.message,true);e.submitter.disabled=false}};
async function pollEnroll(){try{const r=(await api('/admin/fingerprint/'+enrollId)).data;$('enrollStatus').textContent={FIRST_SCAN:'Place the kiosk user’s finger on the scanner.',SECOND_SCAN:'Lift and scan the same finger again.',ENROLLED:'Fingerprint enrolled successfully.',FAILED:'Scans did not match. No fingerprint enrolled.',EXPIRED:'Enrollment expired. Please start again.',CANCELLED:'Enrollment cancelled.'}[r.status]||r.status;if(['ENROLLED','FAILED','EXPIRED','CANCELLED'].includes(r.status)){stopEnroll();await load();return}enrollTimer=setTimeout(pollEnroll,2000)}catch(e){$('enrollStatus').textContent=e.message;enrollTimer=setTimeout(pollEnroll,4000)}}
function stopEnroll(){clearTimeout(enrollTimer);enrollId=null;$('cancelEnroll').hidden=true;$('enrollForm').querySelector('button').disabled=false}
$('cancelEnroll').onclick=async()=>{try{await api('/admin/fingerprint/'+enrollId+'/cancel',{method:'POST'});stopEnroll();$('enrollStatus').textContent='Enrollment cancelled.'}catch(e){notify(e.message,true)}};
document.addEventListener('click',async e=>{const b=e.target.closest('[data-action]');if(!b)return;b.disabled=true;const id=b.dataset.id;try{switch(b.dataset.action){case 'merchant-toggle':{const m=merchants.find(x=>x.id===id);await api('/merchants/'+id,{method:'PATCH',body:{status:m.status==='ACTIVE'?'INACTIVE':'ACTIVE'}});break}case 'merchant-edit':{const m=merchants.find(x=>x.id===id),name=prompt('Canteen name',m.name);if(name===null)return;await api('/merchants/'+id,{method:'PATCH',body:{name}});break}case 'device-toggle':{const d=devices.find(x=>x.id===id);await api('/devices/'+id,{method:'PATCH',body:{status:d.status==='ACTIVE'?'INACTIVE':'ACTIVE'}});break}case 'printer-key':{if(!confirm('Rotate printer credentials? Queued jobs will be cancelled and the old key stops working.'))return;const r=(await api('/admin/devices/'+id+'/printer-key',{method:'POST'})).data;$('secretValue').value=r.printer_token;$('scannerSecret').hidden=false;return}case 'hardware-status':{const r=(await api('/admin/devices/'+id+'/hardware')).data;notify('Printer: '+(r.printer_online?'online':'offline')+'; scanner: '+(r.scanner_online?'online':'offline')+'. '+r.morpho_matching);return}case 'scanner-key':{if(!confirm('Rotate scanner credentials? The old key stops working and pending scans are cancelled.'))return;const r=(await api('/admin/devices/'+id+'/scanner-key',{method:'POST'})).data;$('secretValue').value=r.agent_token;$('scannerSecret').hidden=false;return}case 'revoke':{if(!confirm('Disable fingerprint payments for this student?'))return;await api('/admin/students/'+id+'/fingerprint',{method:'DELETE'});break}case 'product-toggle':{const p=products.find(x=>x.id===id);await api('/products/'+id,{method:'PATCH',body:{availability:p.availability==='AVAILABLE'?'UNAVAILABLE':'AVAILABLE'}});break}case 'product-edit':{const p=products.find(x=>x.id===id),price=prompt('Price \u20B9',p.price_cu);if(price===null)return;const stock=prompt('Stock quantity',p.stock_quantity);if(stock===null)return;await api('/products/'+id,{method:'PATCH',body:{price_cu:Number(price),stock_quantity:Number(stock)}});break}case 'receipt':{const p=(await api('/orders/'+id+'/payment')).data;const r=(await api('/payments/'+p.id+'/receipt')).data;$('receiptText').textContent='REPRINT / COPY\n'+receiptText(r);$('recoveredReceipt').hidden=false;return}}notify('Updated successfully.');await load()}catch(err){notify(err.message,true)}finally{b.disabled=false}});
$('hideSecret').onclick=()=>{$('secretValue').value='';$('scannerSecret').hidden=true};$('studentSearch').oninput=renderStudents;$('productMerchant').onchange=()=>categories().catch(e=>notify(e.message,true));$('refresh').onclick=load;$('reconcile').onclick=async()=>{try{$('recout').textContent=JSON.stringify((await api('/reports/reconciliation')).data,null,2)}catch(e){notify(e.message,true)}};$('reprint').onclick=()=>window.print();
function show(){const title={overview:'Campus overview',students:'Kiosks & fingerprints','merchants-section':'Canteens, menus & stations',transactions:'Orders & receipts',operations:'Reports & operations'};const key=Object.hasOwn(title,location.hash.slice(1))?location.hash.slice(1):'overview';document.querySelectorAll('.app-section').forEach(s=>s.hidden=s.id!==key);$('pageTitle').textContent=title[key]}addEventListener('hashchange',show);show();if(requireLogin(['ADMIN']))load();

$('mobileEnroll').onclick=async()=>{
 const b=$('mobileEnroll');b.disabled=true;
 try{
  if(!MobileAuth.isMobile())throw Error('Open the Admin Portal on the account holder mobile phone to enroll its sensor.');
  if(!await MobileAuth.available())throw Error('Mobile enrollment requires HTTPS and a configured device screen lock/passkey.');
  const d=Object.fromEntries(new FormData($('enrollForm')));
  if(!d.student || d.consent!=='on')throw Error('Select the kiosk user and confirm their informed consent.');
  const student=findStudentByKioskId(d.student);if(!student)throw Error('Invalid Kiosk ID. Student not found.');const path='/admin/students/'+student.id+'/mobile';
  const opts=(await api(path+'/options',{method:'POST',body:{consent_confirmed:true}})).data;
  const credential=await MobileAuth.run(opts.options,true);
  await api(path+'/verify',{method:'POST',body:{ceremony_id:opts.ceremony_id,credential}});
  $('enrollStatus').textContent='Mobile passkey enrolled successfully.';await load();
 }catch(e){$('enrollStatus').textContent=e.name==='NotAllowedError'?'Enrollment cancelled or timed out.':e.message;}finally{b.disabled=false;}
};

async function loadRefunds(){
 const rows=(await api('/admin/refund-payments')).data;
 $('refundPayment').innerHTML='<option value="">Select a completed transaction</option>'+options(rows.filter(r=>r.status==='COMPLETED'&&!r.refunded),r=>r.reference+' - '+r.campus_id+' - '+cu(r.amount_cu));
 $('refundHistory').innerHTML=table([['Transaction',r=>r.reference],['Kiosk user',r=>r.campus_id],['Paid',r=>cu(r.amount_cu)],['Refund',r=>r.refunded?'Refunded to wallet':r.status==='COMPLETED'?'Available':'Not eligible']],rows);
}
$('addMoneyForm').onsubmit=async e=>{
 e.preventDefault();const b=e.submitter,d=Object.fromEntries(new FormData(e.target));b.disabled=true;
 try{const student=findStudentByKioskId(d.student);if(!student)throw Error('Invalid Kiosk ID. Student not found.');const r=(await api('/admin/wallets/'+student.id+'/add-money',{method:'POST',body:{amount_cu:Number(d.amount_cu),reference:d.reference,reason:d.reason,funds_received:d.funds_received==='on'}})).data;
 $('moneyStatus').textContent=(r.replayed?'Already recorded. ':'Money added. ')+ 'Balance after this credit: '+cu(r.balance_after_cu);e.target.reset();await load();
 }catch(err){$('moneyStatus').textContent=err.message;}finally{b.disabled=false;}
};
$('refundForm').onsubmit=async e=>{
 e.preventDefault();const b=e.submitter,d=Object.fromEntries(new FormData(e.target));
 if(!confirm('Refund the full amount of this transaction to its original wallet?'))return;
 b.disabled=true;try{const r=(await api('/admin/payments/'+d.payment_id+'/refund',{method:'POST',body:{reason:d.reason}})).data;
 $('refundStatus').textContent=(r.replayed?'Already refunded. ':'Refund issued. ')+cu(r.amount_cu)+' credited to the original wallet.';e.target.reset();await load();
 }catch(err){$('refundStatus').textContent=err.message;}finally{b.disabled=false;}
};


// Kiosk ID lookup: UI convenience only; all financial checks are repeated server-side.
function findStudentByKioskId(value){
 const id=String(value||'').trim().toUpperCase();
 return students.find(s=>String(s.campus_id||'').trim().toUpperCase()===id);
}
function updateStudentPreview(inputId, infoId){
 const input=$(inputId),info=$(infoId);if(!input||!info)return;
 const id=input.value.trim(),student=findStudentByKioskId(id);
 info.textContent=student ? student.name+' | Balance: '+cu(student.available_cu)+' | Fingerprint: '+student.fingerprint_status
   : id ? 'Student not found' : 'Enter a registered Kiosk ID';
}
[['moneyStudent','moneyStudentInfo'],['enrollStudent','enrollStudentInfo'],['withdrawStudent','withdrawStudentInfo']].forEach(([id,info])=>{
 $(id).addEventListener('input',()=>updateStudentPreview(id,info));
});
$('walletWithdrawForm').onsubmit=async e=>{
 e.preventDefault();const button=e.submitter,d=Object.fromEntries(new FormData(e.target));
 const student=findStudentByKioskId(d.student);
 if(!student){$('withdrawStatus').textContent='Invalid Kiosk ID. Student not found.';return;}
 if(d.funds_returned!=='on'){$('withdrawStatus').textContent='Confirm the money has been returned.';return;}
 const amount=Number(d.amount_cu);
 if(!Number.isSafeInteger(amount)||amount<=0||amount>student.available_cu){
  $('withdrawStatus').textContent='Invalid amount or insufficient balance.';return;
 }
 if(!confirm('Confirm ₹'+amount+' has already been returned to '+student.name+' ('+student.campus_id+')? Wallet balance will be reduced.'))return;
 button.disabled=true;
 try{
  const r=(await api('/admin/wallets/'+encodeURIComponent(student.id)+'/withdraw',{method:'POST',body:{
    amount_cu:amount,reference:d.reference.trim(),reason:d.reason.trim(),funds_returned:true
  }})).data;
  $('withdrawStatus').textContent=(r.replayed?'Already recorded. ':'Money returned and wallet debited. ')+
   'Remaining balance: '+cu(r.balance_after_cu);
  e.target.reset();await load();
 }catch(err){$('withdrawStatus').textContent=err.message;}finally{button.disabled=false;}
};
