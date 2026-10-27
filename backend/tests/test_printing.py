from datetime import timedelta
from sqlalchemy import select
from modules.auth.kiosk_models import PrintJob
from shared.clock import utcnow
from tests.test_fingerprint_kiosk import station, enroll, activate, checkout, scan, pay
from tests.helpers import balance

def printer(t,c):
 r=c.post('/api/v1/admin/devices/'+t.kiosk_id+'/printer-key',headers=t.admin)
 assert r.status_code==200,r.text
 h={'X-Printer-Token':r.json()['data']['printer_token']}
 assert c.get('/api/v1/printer/jobs',headers=h).status_code==200
 return h

def paid(station):
 t,c,a=station;s=enroll(t,c,a);activate(t,c);cid=checkout(t,c);scan(c,a,cid);scan(c,a,cid)
 assert pay(c,cid).status_code==200
 return t,c,cid,s

def enqueue(c,cid):return c.post('/api/v1/kiosk/checkouts/'+cid+'/print',headers={'X-Kiosk-Request':'1'})

def test_paid_receipt_print_once_and_station_scope(station):
 t,c,cid,s=paid(station);h=printer(t,c)
 first=enqueue(c,cid);assert first.status_code==200,first.text
 jid=first.json()['data']['id'];assert enqueue(c,cid).json()['data']['id']==jid
 assert c.get('/api/v1/printer/jobs',headers=h).json()['data'][0]['id']==jid
 r=c.post('/api/v1/printer/jobs/'+jid+'/claim',headers=h,json={});assert r.status_code==200,r.text
 receipt=r.json()['data']['receipt'];assert receipt['amount_cu']==10 and receipt['balance_after_cu']==490 and receipt['receipt_number']
 assert c.post('/api/v1/printer/jobs/'+jid+'/claim',headers=h,json={}).status_code==409
 assert c.get('/api/v1/printer/jobs',headers=h).json()['data']==[]
 for _ in range(2):assert c.post('/api/v1/printer/jobs/'+jid+'/result',headers=h,json={'state':'SUBMITTED'}).status_code==200
 assert enqueue(c,cid).json()['data']['state']=='SUBMITTED'
 assert balance(t,s.campus_id)==490


def test_unpaid_cannot_print(station):
 t,c,a=station;activate(t,c);h=printer(t,c);cid=checkout(t,c)
 assert enqueue(c,cid).status_code==403
 with t.session() as db:assert db.execute(select(PrintJob)).first() is None


def test_printer_offline_preserves_paid_receipt(station):
 t,c,cid,s=paid(station)
 assert enqueue(c,cid).status_code==409
 assert balance(t,s.campus_id)==490
 assert pay(c,cid).json()['data']['receipt']


def test_printer_keys_are_separate_capabilities(station):
 t,c,a=station;h=printer(t,c)
 assert c.get('/api/v1/scanner/jobs',headers={'X-Scanner-Token':h['X-Printer-Token']}).status_code==401
 assert c.get('/api/v1/printer/jobs',headers={'X-Printer-Token':a['X-Scanner-Token']}).status_code==401
 assert c.get('/api/v1/admin/devices/'+t.kiosk_id+'/hardware',headers=t.admin).json()['data']['printer_online']
 assert c.post('/api/v1/admin/devices/'+t.kiosk_id+'/printer-key',headers=t.staff).status_code==403


def test_key_rotation_cancels_queued_job(station):
 t,c,cid,s=paid(station);h=printer(t,c);jid=enqueue(c,cid).json()['data']['id']
 fresh=printer(t,c)
 assert c.get('/api/v1/printer/jobs',headers=h).status_code==401
 assert c.post('/api/v1/printer/jobs/'+jid+'/claim',headers=fresh,json={}).status_code==409
 assert enqueue(c,cid).json()['data']['state']=='CANCELLED'


def test_claim_timeout_is_unknown_never_auto_reprinted(station):
 t,c,cid,s=paid(station);h=printer(t,c);jid=enqueue(c,cid).json()['data']['id']
 c.post('/api/v1/printer/jobs/'+jid+'/claim',headers=h,json={})
 with t.session() as db:
  db.get(PrintJob,jid).claimed_at=utcnow()-timedelta(seconds=100);db.commit()
 assert c.get('/api/v1/printer/jobs',headers=h).json()['data']==[]
 assert enqueue(c,cid).json()['data']['state']=='UNKNOWN'
 assert c.post('/api/v1/printer/jobs/'+jid+'/result',headers=h,json={'state':'SUBMITTED'}).status_code==409
 assert balance(t,s.campus_id)==490


def test_station_modes_require_admin_and_are_returned_in_menu(station):
 from tests.helpers import PASSWORD
 t,c,a=station
 r=c.post('/api/v1/kiosk/setup',json={'institution_code':t.code,'username':'admin','password':PASSWORD,'device_id':t.kiosk_id,'authentication_mode':'SCANNER','receipt_mode':'THERMAL'})
 assert r.status_code==200,r.text
 menu=c.get('/api/v1/kiosk/menu').json()['data']
 assert menu['authentication_mode']=='SCANNER' and menu['receipt_mode']=='THERMAL'


def test_expired_queued_job_not_printed(station):
 t,c,cid,s=paid(station);h=printer(t,c);jid=enqueue(c,cid).json()['data']['id']
 with t.session() as db:db.get(PrintJob,jid).created_at=utcnow()-timedelta(seconds=100);db.commit()
 assert c.get('/api/v1/printer/jobs',headers=h).json()['data']==[]
 assert enqueue(c,cid).json()['data']['state']=='CANCELLED'


def test_mobile_sessions_do_not_revoke_physical_kiosk_or_block_scanner(station):
 from tests.helpers import PASSWORD
 t,physical,a=station;activate(t,physical)
 phones=[t.client(),t.client()]
 for c in phones:
  r=c.post('/api/v1/kiosk/setup',json={'institution_code':t.code,'username':'admin','password':PASSWORD,'device_id':t.kiosk_id,'authentication_mode':'MOBILE'})
  assert r.status_code==200,r.text
 assert physical.get('/api/v1/kiosk/menu').status_code==200
 assert all(c.get('/api/v1/kiosk/menu').status_code==200 for c in phones)
 checkout(t,physical)
 for c in phones:
  r=c.post('/api/v1/kiosk/mobile/checkouts',headers={'X-Kiosk-Request':'1'},json={'items':[{'product_id':t.products['Tea'],'quantity':1}]})
  assert r.status_code==201,r.text
  assert c.post('/api/v1/kiosk/checkouts',headers={'X-Kiosk-Request':'1'},json={'items':[{'product_id':t.products['Tea'],'quantity':1}]}).status_code==403
