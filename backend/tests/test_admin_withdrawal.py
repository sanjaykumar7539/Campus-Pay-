"""Wallet cash-out tests (requires project backend requirements and pytest)."""
from tests.helpers import balance, ledger_count, audit_types

ID = 'EGS-STD-0001'

def path(t):
    return '/api/v1/admin/wallets/' + t.students[ID].id + '/withdraw'

def payload(**changes):
    return {'amount_cu': 200, 'reference': 'CASHOUT-REF-001',
            'reason': 'Student cash returned', 'funds_returned': True, **changes}

def test_withdrawal_idempotent_and_reconciled(world):
    t=world; c=t.client()
    r=c.post(path(t),headers=t.admin,json=payload())
    assert r.status_code==200,r.text
    assert balance(t,ID)==300
    r=c.post(path(t),headers=t.admin,json=payload())
    assert r.status_code==200 and r.json()['data']['replayed'] is True
    assert balance(t,ID)==300
    assert c.post(path(t),headers=t.admin,json=payload(amount_cu=201)).status_code==409
    assert ledger_count(t,'WALLET_WITHDRAWAL')==1
    assert 'ADMIN_WALLET_WITHDRAWAL' in audit_types(t)
    r=c.get('/api/v1/wallets/'+t.students[ID].id+'/reconciliation',headers=t.admin)
    assert r.json()['data']['consistent'] is True

def test_withdrawal_rejections(world):
    t=world; c=t.client()
    assert c.post(path(t),headers=t.admin,json=payload(amount_cu=600)).status_code in (402,409)
    assert c.post(path(t),headers=t.admin,json=payload(funds_returned=False)).status_code==403
    assert c.post(path(t),headers=t.admin,json=payload(amount_cu=0)).status_code==422
    assert c.post(path(t),headers=t.staff,json=payload()).status_code==403
    assert c.post(path(t),json=payload()).status_code==401
    assert balance(t,ID)==500
