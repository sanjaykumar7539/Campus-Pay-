// State regression checks, independent of a physical scanner or browser driver.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const elements = new Map();
function element(id) {
  if (!elements.has(id)) elements.set(id, {
    hidden: false, disabled: false, open: false, value: '', textContent: '', innerHTML: '',
    addEventListener() {}, showModal() { this.open = true; }, close() { this.open = false; },
    replaceChildren() { this.innerHTML = ''; }
  });
  return elements.get(id);
}
let interval, now = 0, timeoutFn, timeoutMs;
const context = vm.createContext({
  document: { getElementById: element },
  sessionStorage: { getItem() { return null; }, setItem() {}, removeItem() {} },
  setInterval(fn) { interval = fn; }, setTimeout(fn,ms) { timeoutFn=fn;timeoutMs=ms;return 1; }, clearTimeout() {},
  addEventListener() {}, Date: { now() { return now; } },
  location: { replace() {} }, window: { print() {} },
  fetch: async () => ({ ok: false, status: 401, json: async () => ({ error: { message: 'Staff setup required' } }) })
});
vm.runInContext(fs.readFileSync(path.join(__dirname, '../demo/station.js'), 'utf8'), context);
(async () => {
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(vm.runInContext('money(90)',context), '\u20B990');
  // A kiosk awaiting initial setup has no catalog. Idle cleanup must be safe.
  now = 61000;
  assert.doesNotThrow(() => interval());
  // If the initial payment response was lost and the session expires on retry,
  // never turn an unknown financial outcome into a new-order invitation.
  vm.runInContext("ticket={id:'test-checkout',status:'CONSUMED'};uncertain=true;", context);
  await vm.runInContext('completePayment()', context);
  assert.equal(vm.runInContext('uncertain', context), true);
  assert.equal(element('cancelScan').disabled, true);
  assert.equal(element('retryPay').hidden, false);
  assert.match(element('scanStatus').textContent, /do not place another order/);
  // Offline hardware still shows authentication, preserving the cart on return.
  context.fetch = async () => ({ok:false,status:409,json:async()=>({error:{code:'SCANNER_OFFLINE',message:'Scanner offline'}})});
  vm.runInContext("ticket=null;uncertain=false;catalog={scanner_online:false,merchant:{status:'ACTIVE',accepting_orders:true}};cart.set('pen',{id:'pen',name:'Blue Pen',price_cu:10,quantity:1});",context);
  await vm.runInContext('startCheckout()',context);
  assert.equal(element('scanDialog').open,true);
  assert.match(element('scanTitle').textContent,/Scan your enrolled finger/);
  assert.match(element('scanStatus').textContent,/No order has been completed/);
  assert.equal(element('retryScanner').hidden,false);
  assert.equal(vm.runInContext('ticket',context),null);
  await vm.runInContext('cancel()',context);
  assert.equal(element('scanDialog').open,false);
  assert.equal(vm.runInContext('cart.size',context),1);
  assert.equal(element('checkout').disabled,false);
  // Successful payment displays a receipt then automatically clears the completed order.
  context.fetch=async()=>({ok:true,json:async()=>({data:{receipt:{merchant:'Common Canteen',institution:'EGS',receipt_number:'R1',order_reference:'O1',lines:[],amount_cu:10,balance_after_cu:490,paid_at:'now',warning:'Collect your order.'}}})});
  vm.runInContext("ticket={id:'receipt-check',status:'READY'};",context);
  await vm.runInContext('completePayment()',context);
  assert.equal(element('receiptDialog').open,true);
  assert.match(element('receiptPaper').innerHTML,/490/);
  assert.equal(timeoutMs,15000);
  timeoutFn();
  assert.equal(element('receiptDialog').open,false);
  assert.equal(vm.runInContext('cart.size',context),0);
  assert.equal(vm.runInContext('ticket',context),null);
  // Mobile selection uses WebAuthn, waits for a second confirmation and then pays.
  await new Promise(resolve=>setImmediate(resolve));
  context.MobileAuth={isMobile:()=>true,available:async()=>true,run:async()=>({id:'signed-proof'})};
  let verifies=0,pays=0,mobileCreated=false;
  context.fetch=async(url)=>{
    let data;
    if(url.endsWith('/mobile/checkouts')) {mobileCreated=true;data={id:'mobile',status:'FIRST_SCAN',total_cu:10};}
    else if(url.endsWith('/mobile/options'))data={ceremony_id:'fresh',options:{}};
    else if(url.endsWith('/mobile/verify'))data={id:'mobile',status:++verifies===1?'SECOND_SCAN':'READY',total_cu:10};
    else if(url.endsWith('/pay')){pays++;data={receipt:null,order:{reference:'M1'},balance_after_cu:480};}
    else data={};
    return {ok:true,json:async()=>({data})};
  };
  vm.runInContext("catalog={merchant:{status:'ACTIVE',accepting_orders:true}};cart.set('pen',{id:'pen',name:'Pen',price_cu:10,quantity:1});",context);
  await vm.runInContext('startCheckout()',context);
  assert.equal(mobileCreated,true);assert.equal(verifies,1);assert.equal(pays,0);
  assert.equal(element('mobileScan').hidden,false);
  await vm.runInContext('mobileScan()',context);
  assert.equal(verifies,2);assert.equal(pays,1);assert.equal(element('receiptDialog').open,true);
  // Thermal submission uncertainty retains the paid receipt and never makes another payment.
  vm.runInContext("catalog.receipt_mode='THERMAL';",context);
  context.fetch=async()=>({ok:true,json:async()=>({data:{id:'print-job',state:'UNKNOWN'}})});
  await vm.runInContext('thermalPrint()',context);
  assert.equal(element('receiptDialog').open,true);
  assert.match(element('receiptNote').textContent,/Do not pay again/);
  assert.equal(element('finish').disabled,false);
  assert.equal(pays,1);
  // Confirmed spool submission finishes the paid checkout.
  context.fetch=async()=>({ok:true,json:async()=>({data:{id:'print-job',state:'SUBMITTED'}})});
  await vm.runInContext('thermalPrint()',context);
  assert.equal(element('receiptDialog').open,false);
  assert.equal(vm.runInContext('ticket',context),null);
  console.log('7 station state regression checks passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
