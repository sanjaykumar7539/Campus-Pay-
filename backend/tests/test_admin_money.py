import pytest
from tests.helpers import balance, ledger_count, place_order, pay, build_world, audit_types, sql

ID='EGS-STD-0001'
def payload(**kw):
    return {'amount_cu':100,'reference':'COLLECTION-001','reason':'Cash received','funds_received':True,**kw}
def path(t):return '/api/v1/admin/wallets/'+t.students[ID].id+'/add-money'

def test_topup_once_conflicting_reference_rejected(world):
    t=world;c=t.client()
    r=c.post(path(t),headers=t.admin,json=payload());assert r.status_code==200,r.text
    assert balance(t,ID)==600
    assert c.post(path(t),headers=t.admin,json=payload()).json()['data']['replayed'] is True
    assert balance(t,ID)==600
    assert c.post(path(t),headers=t.admin,json=payload(amount_cu=101)).status_code==409
    assert 'ADMIN_MONEY_ADDED' in audit_types(t)
    assert c.get('/api/v1/wallets/'+t.students[ID].id+'/reconciliation',headers=t.admin).json()['data']['consistent'] is True

@pytest.mark.parametrize('changes',[{'amount_cu':0},{'amount_cu':-5},{'amount_cu':1.5},{'amount_cu':True},{'amount_cu':1000001},{'reason':'   '},{'reference':'   '},{'funds_received':False}])
def test_topup_invalid_input_no_credit(world,changes):
    t=world;r=t.client().post(path(t),headers=t.admin,json=payload(**changes));assert r.status_code in (403,422),r.text
    assert balance(t,ID)==500

def test_admin_money_scope(world):
    t=world;c=t.client()
    assert c.post(path(t),json=payload()).status_code==401
    assert c.post(path(t),headers=t.staff,json=payload()).status_code==403
    other=build_world(t.app)
    assert c.post('/api/v1/admin/wallets/'+other.students[ID].id+'/add-money',headers=t.admin,json=payload()).status_code==404


def payment(t):
    r=place_order(t,ID,{'Tea':1});assert r.status_code==201,r.text
    r=pay(t,r.json()['data']['id'],ID,'4826');assert r.status_code==200,r.text
    return r.json()['data']['payment']['id']

def test_full_refund_once_preserves_original_payment(world):
    t=world;pid=payment(t);c=t.client();assert balance(t,ID)==490
    url='/api/v1/admin/payments/'+pid+'/refund'
    r=c.post(url,headers=t.admin,json={'reason':'Order cancelled'});assert r.status_code==200,r.text
    assert balance(t,ID)==500 and ledger_count(t,'REFUND')==1
    assert c.post(url,headers=t.admin,json={'reason':'Retry'}).json()['data']['replayed'] is True
    assert balance(t,ID)==500 and ledger_count(t,'REFUND')==1
    assert sql(t,'SELECT status FROM payments WHERE id=:p',p=pid)[0][0]=='COMPLETED'
    assert 'ADMIN_REFUND_ISSUED' in audit_types(t)
    rows=c.get('/api/v1/admin/refund-payments',headers=t.admin).json()['data']
    assert next(r for r in rows if r['id']==pid)['refunded'] is True


def test_refund_scope_and_failed_payment(world):
    t=world;pid=payment(t);c=t.client();url='/api/v1/admin/payments/'+pid+'/refund'
    assert c.post(url,headers=t.staff,json={'reason':'Wrong role'}).status_code==403
    assert c.post(url,json={'reason':'No login'}).status_code==401
    other=build_world(t.app)
    assert c.post(url,headers=other.admin,json={'reason':'Other college'}).status_code==404
    sql(t,"UPDATE payments SET status='FAILED' WHERE id=:p",p=pid)
    assert c.post(url,headers=t.admin,json={'reason':'Failed payment'}).status_code==409
    assert balance(t,ID)==490


def test_credit_failure_rolls_back_ledger(world,monkeypatch):
    from modules.wallets import service
    t=world;before=ledger_count(t)
    def fail(*args,**kwargs):raise RuntimeError('Injected failure')
    monkeypatch.setattr(service,'_apply',fail)
    with pytest.raises(RuntimeError):t.client().post(path(t),headers=t.admin,json=payload())
    assert balance(t,ID)==500 and ledger_count(t)==before


@pytest.mark.parametrize('operation',['topup','refund'])
def test_simultaneous_retries_credit_once(world,operation):
    from concurrent.futures import ThreadPoolExecutor
    t=world
    if operation=='refund':
        url='/api/v1/admin/payments/'+payment(t)+'/refund';body={'reason':'Concurrent retry'};expected=500
    else: url=path(t);body=payload();expected=600
    def submit(_):return t.client().post(url,headers=t.admin,json=body)
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(submit,range(2)))
    assert all(r.status_code==200 for r in results),[r.text for r in results]
    assert sum(not r.json()['data']['replayed'] for r in results)==1
    assert balance(t,ID)==expected
