"""Signed virtual platform-authenticator responses exercise the real WebAuthn verifier."""
import base64, hashlib, json, os, struct
import cbor2
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes
from tests.test_fingerprint_kiosk import station, activate, pay
from tests.helpers import balance, ledger_count

ORIGIN='http://localhost:8002'
HEADERS={'Origin':ORIGIN,'X-Kiosk-Request':'1'}
def enc(b): return base64.urlsafe_b64encode(b).decode().rstrip('=')

def client_data(kind, challenge, origin=ORIGIN):
    return json.dumps({'type':kind,'challenge':challenge,'origin':origin,'crossOrigin':False}).encode()

class Authenticator:
    def __init__(self):
        self.key=ec.generate_private_key(ec.SECP256R1());self.id=os.urandom(32);self.count=0
    def register(self, options, uv=True):
        n=self.key.public_key().public_numbers()
        cose=cbor2.dumps({1:2,3:-7,-1:1,-2:n.x.to_bytes(32,'big'),-3:n.y.to_bytes(32,'big')})
        data=hashlib.sha256(b'localhost').digest()+bytes([0x45 if uv else 0x41])+struct.pack('>I',0)+bytes(16)+struct.pack('>H',len(self.id))+self.id+cose
        return {'id':enc(self.id),'rawId':enc(self.id),'type':'public-key','authenticatorAttachment':'platform',
            'response':{'clientDataJSON':enc(client_data('webauthn.create',options['challenge'])),
            'attestationObject':enc(cbor2.dumps({'fmt':'none','attStmt':{},'authData':data}))}}
    def authenticate(self, options, uv=True, origin=ORIGIN):
        self.count+=1
        client=client_data('webauthn.get',options['challenge'],origin)
        data=hashlib.sha256(b'localhost').digest()+bytes([5 if uv else 1])+struct.pack('>I',self.count)
        signature=self.key.sign(data+hashlib.sha256(client).digest(),ec.ECDSA(hashes.SHA256()))
        return {'id':enc(self.id),'rawId':enc(self.id),'type':'public-key','authenticatorAttachment':'platform',
            'response':{'clientDataJSON':enc(client),'authenticatorData':enc(data),'signature':enc(signature),'userHandle':None}}

def enroll_mobile(t,c,device=None):
    a=device or Authenticator();student=next(iter(t.students.values()))
    path='/api/v1/admin/students/'+student.id+'/mobile'
    headers={**t.admin,**HEADERS}
    out=c.post(path+'/options',headers=headers,json={'consent_confirmed':True})
    assert out.status_code==200,out.text
    options=out.json()['data']
    proof={'ceremony_id':options['ceremony_id'],'credential':a.register(options['options'])}
    r=c.post(path+'/verify',headers=headers,json=proof)
    assert r.status_code==200,r.text
    assert c.post(path+'/verify',headers=headers,json=proof).status_code==403
    return a,student

def checkout_mobile(t,c):
    r=c.post('/api/v1/kiosk/mobile/checkouts',headers=HEADERS,json={'items':[{'product_id':t.products['Tea'],'quantity':1}]})
    assert r.status_code==201,r.text
    return r.json()['data']['id']

def assertion(c,cid,a,**kw):
    path='/api/v1/kiosk/checkouts/'+cid+'/mobile'
    r=c.post(path+'/options',headers=HEADERS)
    assert r.status_code==200,r.text
    opts=r.json()['data']
    proof={'ceremony_id':opts['ceremony_id'],'credential':a.authenticate(opts['options'],**kw)}
    return c.post(path+'/verify',headers=HEADERS,json=proof),proof

def test_mobile_two_verified_assertions_debit_once_without_scanner(station):
    t,c,agent=station;a,s=enroll_mobile(t,c);activate(t,c)
    # Remove reader heartbeat: mobile must still work; physical route remains offline.
    from modules.auth.kiosk_models import ScannerAgent
    from sqlalchemy import select
    with t.session() as db:
        db.execute(select(ScannerAgent)).scalar_one().last_seen_at=None;db.commit()
    assert c.post('/api/v1/kiosk/checkouts',headers=HEADERS,json={'items':[{'product_id':t.products['Tea'],'quantity':1}]}).status_code==409
    cid=checkout_mobile(t,c)
    assert pay(c,cid).status_code==403
    r,proof=assertion(c,cid,a);assert r.json()['data']['status']=='SECOND_SCAN',r.text
    assert pay(c,cid).status_code==403
    assert c.post('/api/v1/kiosk/checkouts/'+cid+'/mobile/verify',headers=HEADERS,json=proof).status_code==403
    r,_=assertion(c,cid,a);assert r.json()['data']['status']=='READY',r.text
    r=pay(c,cid);assert r.status_code==200,r.text
    assert r.json()['data']['receipt']['balance_after_cu']==490
    assert pay(c,cid).json()['data']['replayed'] is True
    assert balance(t,s.campus_id)==490 and ledger_count(t,'PURCHASE')==1

@pytest.mark.parametrize('failure',['no_uv','wrong_origin','different_key','bad_signature'])
def test_mobile_invalid_assertion_never_charges(station,failure):
    t,c,agent=station;a,s=enroll_mobile(t,c);activate(t,c);cid=checkout_mobile(t,c)
    kw={'uv':False} if failure=='no_uv' else {'origin':'https://evil.example'} if failure=='wrong_origin' else {}
    if failure=='different_key': a=Authenticator()
    if failure=='bad_signature':
        path='/api/v1/kiosk/checkouts/'+cid+'/mobile'
        opts=c.post(path+'/options',headers=HEADERS).json()['data'];credential=a.authenticate(opts['options'])
        credential['response']['signature']=enc(b'invalid')
        r=c.post(path+'/verify',headers=HEADERS,json={'ceremony_id':opts['ceremony_id'],'credential':credential})
    else: r,_=assertion(c,cid,a,**kw)
    assert r.status_code==403,r.text
    assert pay(c,cid).status_code==403
    assert balance(t,s.campus_id)==500


def test_mobile_revocation_blocks_ready_payment(station):
    t,c,agent=station;a,s=enroll_mobile(t,c);activate(t,c);cid=checkout_mobile(t,c)
    assertion(c,cid,a);assertion(c,cid,a)
    assert c.delete('/api/v1/admin/students/'+s.id+'/fingerprint',headers=t.admin).status_code==200
    assert pay(c,cid).status_code==403
    assert balance(t,s.campus_id)==500


def test_mobile_enrollment_needs_admin_consent_and_valid_uv(station):
    t,c,agent=station;s=next(iter(t.students.values()));path='/api/v1/admin/students/'+s.id+'/mobile'
    assert c.post(path+'/options',headers=HEADERS,json={'consent_confirmed':True}).status_code==401
    h={**t.admin,**HEADERS}
    assert c.post(path+'/options',headers=h,json={'consent_confirmed':False}).status_code==403
    opts=c.post(path+'/options',headers=h,json={'consent_confirmed':True}).json()['data']
    assert c.post(path+'/verify',headers=h,json={'ceremony_id':opts['ceremony_id'],'credential':Authenticator().register(opts['options'],False)}).status_code==403


def test_mobile_second_confirmation_cannot_switch_accounts(station):
    t,c,agent=station;a,s=enroll_mobile(t,c);activate(t,c);cid=checkout_mobile(t,c)
    assertion(c,cid,a)
    assert assertion(c,cid,Authenticator())[0].status_code==403
    assert pay(c,cid).status_code==403
    assert balance(t,s.campus_id)==500


def test_expired_mobile_prompt_and_wrong_session_rejected(station):
    from modules.auth.kiosk_models import MobileCeremony
    from datetime import timedelta
    from shared.clock import utcnow
    t,c,agent=station;a,s=enroll_mobile(t,c);activate(t,c);cid=checkout_mobile(t,c)
    path='/api/v1/kiosk/checkouts/'+cid+'/mobile'
    opts=c.post(path+'/options',headers=HEADERS).json()['data']
    with t.session() as db:
        db.get(MobileCeremony,opts['ceremony_id']).expires_at=utcnow()-timedelta(seconds=1);db.commit()
    proof={'ceremony_id':opts['ceremony_id'],'credential':a.authenticate(opts['options'])}
    assert c.post(path+'/verify',headers=HEADERS,json=proof).status_code==403
    assert t.client().post(path+'/options',headers=HEADERS).status_code==401
    assert balance(t,s.campus_id)==500
