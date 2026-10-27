"""API tests use an explicit test scanner, never a production biometric bypass."""
from uuid import uuid4
from datetime import timedelta
import pytest
from tests.helpers import PASSWORD, balance, build_world, ledger_count
from shared.clock import utcnow
from modules.auth.kiosk_models import FingerprintChallenge
from tests.test_concurrency import cworld  # both SQLite and PostgreSQL when configured


@pytest.fixture
def station(world, monkeypatch):
    monkeypatch.setenv("CAMPUSPAY_PAYMENT_AUTH", "fingerprint")
    c = world.client()
    r = c.post(f"/api/v1/admin/devices/{world.kiosk_id}/scanner-key", headers=world.admin)
    assert r.status_code == 200, r.text
    agent = {"X-Scanner-Token": r.json()["data"]["agent_token"]}
    assert c.get("/api/v1/scanner/jobs", headers=agent).status_code == 200
    return world, c, agent


def scan(c, agent, cid, finger="test-finger-1", *, capture_id=None, matched=True):
    jobs = c.get("/api/v1/scanner/jobs", headers=agent).json()["data"]
    job = next(j for j in jobs if j["id"] == cid)
    return c.post(f"/api/v1/scanner/jobs/{cid}/capture", headers=agent,
        json={"nonce": job["nonce"], "capture_id": capture_id or str(uuid4()), "finger_ref": finger, "matched": matched})


def enroll(t, c, agent, finger="test-finger-1", student=None):
    student = student or next(iter(t.students.values()))
    r = c.post(f"/api/v1/admin/students/{student.id}/fingerprint", headers=t.admin,
        json={"device_id": t.kiosk_id, "consent_confirmed": True})
    assert r.status_code == 200, r.text
    cid = r.json()["data"]["id"]
    assert scan(c, agent, cid, finger).json()["data"]["status"] == "SECOND_SCAN"
    r = scan(c, agent, cid, finger)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "ENROLLED"
    return student


def activate(t, c):
    r = c.post("/api/v1/kiosk/setup", json={"institution_code": t.code, "username": "admin",
        "password": PASSWORD, "device_id": t.kiosk_id})
    assert r.status_code == 200, r.text
    assert "HttpOnly" in r.headers["set-cookie"] and "SameSite=strict" in r.headers["set-cookie"]


def checkout(t, c, qty=1):
    r = c.post("/api/v1/kiosk/checkouts", headers={"X-Kiosk-Request": "1"},
        json={"items": [{"product_id": t.products["Tea"], "quantity": qty}]})
    assert r.status_code == 201, r.text
    return r.json()["data"]["id"]


def pay(c, cid):
    return c.post(f"/api/v1/kiosk/checkouts/{cid}/pay", headers={"X-Kiosk-Request": "1"})


def test_two_same_finger_scans_debit_once_and_receipt_balance(station):
    t,c,a = station
    s=enroll(t,c,a)
    activate(t,c)
    cid=checkout(t,c)
    assert pay(c,cid).status_code==403
    assert scan(c,a,cid).json()["data"]["status"]=="SECOND_SCAN"
    assert pay(c,cid).status_code==403
    assert balance(t,s.campus_id)==500
    assert scan(c,a,cid).json()["data"]["status"]=="READY"
    r=pay(c,cid)
    assert r.status_code==200, r.text
    data=r.json()["data"]
    assert data["receipt"]["balance_after_cu"]==490
    assert "do not pay again" in data["receipt"]["warning"].lower()
    assert pay(c,cid).json()["data"]["replayed"] is True
    assert balance(t,s.campus_id)==490
    assert ledger_count(t,"PURCHASE")==1


def test_different_finger_cannot_pay(station):
    t,c,a=station;s=enroll(t,c,a);activate(t,c);cid=checkout(t,c)
    scan(c,a,cid)
    assert scan(c,a,cid,"different-finger").json()["data"]["status"]=="FAILED"
    assert pay(c,cid).status_code==403
    assert balance(t,s.campus_id)==500


def test_capture_replay_and_browser_spoofing_rejected(station):
    t,c,a=station;enroll(t,c,a);activate(t,c);cid=checkout(t,c)
    capture=str(uuid4())
    scan(c,a,cid,capture_id=capture)
    assert scan(c,a,cid,capture_id=capture).status_code==409
    jobs=c.get('/api/v1/scanner/jobs',headers=a).json()['data']
    payload={"nonce":jobs[0]['nonce'],"capture_id":str(uuid4()),"matched":True,"finger_ref":"test-finger-1"}
    assert c.post(f'/api/v1/scanner/jobs/{cid}/capture',json=payload,headers=t.admin).status_code==401
    assert pay(c,cid).status_code==403


def test_expired_authorization_does_not_charge(station):
    t,c,a=station;s=enroll(t,c,a);activate(t,c);cid=checkout(t,c)
    scan(c,a,cid);scan(c,a,cid)
    with t.session() as db:
        row=db.get(FingerprintChallenge,cid);row.expires_at=utcnow()-timedelta(seconds=1);db.commit()
    assert pay(c,cid).status_code==403
    assert balance(t,s.campus_id)==500


def test_revoked_fingerprint_cannot_use_ready_grant(station):
    t,c,a=station;s=enroll(t,c,a);activate(t,c);cid=checkout(t,c)
    scan(c,a,cid);scan(c,a,cid)
    assert c.delete(f'/api/v1/admin/students/{s.id}/fingerprint',headers=t.admin).status_code==200
    assert pay(c,cid).status_code==403
    assert balance(t,s.campus_id)==500


def test_low_balance_never_debits(station):
    t,c,a=station;s=enroll(t,c,a);activate(t,c)
    # 25 meals at 60 = 1500, greater than the seeded 500 balance.
    r=c.post('/api/v1/kiosk/checkouts',headers={'X-Kiosk-Request':'1'},json={'items':[{'product_id':t.products['Veg Meal'],'quantity':25}]})
    cid=r.json()['data']['id'];scan(c,a,cid);scan(c,a,cid)
    assert pay(c,cid).status_code==402
    assert balance(t,s.campus_id)==500
    assert ledger_count(t,'PURCHASE')==0


def test_kiosk_is_not_admin_and_logout_needs_admin_password(station):
    t,c,a=station;activate(t,c)
    assert c.get('/api/v1/admin/students').status_code==401
    assert c.get('/login.html',follow_redirects=False).status_code==303
    for user,pwd in [('admin','wrong'),('staff',PASSWORD)]:
        r=c.post('/api/v1/kiosk/logout',headers={'X-Kiosk-Request':'1'},json={'username':user,'password':pwd})
        assert r.status_code in (401,403)
        assert c.get('/api/v1/kiosk/menu').status_code==200
    assert c.post('/api/v1/kiosk/logout',headers={'X-Kiosk-Request':'1'},json={'username':'admin','password':PASSWORD}).status_code==200
    assert c.get('/api/v1/kiosk/menu').status_code==401


def test_cross_tenant_station_and_student_enrollment_rejected(station):
    t,c,a=station;other=build_world(t.app)
    r=c.post('/api/v1/kiosk/setup',json={'institution_code':other.code,'username':'admin','password':PASSWORD,'device_id':t.kiosk_id})
    assert r.status_code==403
    r=c.post(f'/api/v1/admin/students/{next(iter(other.students.values())).id}/fingerprint',headers=t.admin,
        json={'device_id':t.kiosk_id,'consent_confirmed':True})
    assert r.status_code==404
    assert c.post('/api/v1/devices',headers=t.admin,json={'name':'wrong tenant','merchant_id':other.merchant_id}).status_code==404


def test_no_pin_fallback_and_missing_scanner_blocks(station):
    t,c,a=station;activate(t,c)
    assert c.post('/api/v1/auth/student-login',json={'institution_code':t.code,'campus_id':next(iter(t.students))}).status_code==403
    assert c.post('/api/v1/kiosk/checkouts',json={'items':[{'product_id':t.products['Tea'],'quantity':1}]}).status_code==403
    from modules.auth.kiosk_models import ScannerAgent
    with t.session() as db:
        row=db.query(ScannerAgent).filter_by(device_id=t.kiosk_id).one();row.last_seen_at=None;db.commit()
    assert c.post('/api/v1/kiosk/checkouts',headers={'X-Kiosk-Request':'1'},json={'items':[{'product_id':t.products['Tea'],'quantity':1}]}).status_code==409


def test_registration_without_pin_and_merchant_scoping(station):
    t,c,a=station
    r=c.post('/api/v1/admin/students',headers=t.admin,json={'name':'New student','unique_identifier':'NEW-STUDENT'})
    assert r.status_code==201,r.text
    assert r.json()['data']['fingerprint_status']=='NOT_ENROLLED'
    r=c.post('/api/v1/merchants',headers=t.admin,json={'name':'New Canteen','staff_name':'New Staff',
        'staff_identifier':'STAFF-NEW','username':'new.staff','password':'Long-Password-123'})
    assert r.status_code==201,r.text
    mid=r.json()['data']['id']
    assert c.patch('/api/v1/merchants/'+mid,headers=t.staff,json={'status':'INACTIVE'}).status_code==403
    assert c.patch('/api/v1/merchant/availability',headers=t.staff,json={'status':'INACTIVE'}).status_code==200
    m=c.get('/api/v1/merchants',headers=t.staff).json()['data'][0]
    assert m['status']=='ACTIVE' and not m['accepting_orders']
    c.patch('/api/v1/merchants/'+t.merchant_id,headers=t.admin,json={'status':'INACTIVE'})
    assert c.patch('/api/v1/merchant/availability',headers=t.staff,json={'status':'ACTIVE'}).status_code==403


def test_finished_receipt_cannot_be_reopened_by_next_student(station):
    t,c,a=station;enroll(t,c,a);activate(t,c);cid=checkout(t,c)
    scan(c,a,cid);scan(c,a,cid);assert pay(c,cid).status_code==200
    assert c.post(f'/api/v1/kiosk/checkouts/{cid}/finish',headers={'X-Kiosk-Request':'1'}).status_code==200
    assert pay(c,cid).status_code==403
    assert checkout(t,c) != cid


def test_concurrent_fingerprint_pay_is_one_debit(cworld, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    monkeypatch.setenv('CAMPUSPAY_PAYMENT_AUTH','fingerprint')
    t=cworld;c=t.client()
    r=c.post(f'/api/v1/admin/devices/{t.kiosk_id}/scanner-key',headers=t.admin)
    a={'X-Scanner-Token':r.json()['data']['agent_token']}
    c.get('/api/v1/scanner/jobs',headers=a)
    s=enroll(t,c,a);activate(t,c);cid=checkout(t,c);scan(c,a,cid);scan(c,a,cid)
    cookie=c.cookies.get('cp_kiosk');barrier=threading.Barrier(4)
    def attempt(_):
        with t.client() as client:
            client.cookies.set('cp_kiosk',cookie)
            barrier.wait()
            return pay(client,cid)
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses=list(pool.map(attempt,range(4)))
    assert all(r.status_code==200 for r in responses),[r.text for r in responses]
    assert balance(t,s.campus_id)==490 and ledger_count(t,'PURCHASE')==1


def test_stock_removed_after_scans_rolls_back_financial_effect(station):
    t,c,a=station;s=enroll(t,c,a);activate(t,c);cid=checkout(t,c);scan(c,a,cid);scan(c,a,cid)
    assert c.patch('/api/v1/products/'+t.products['Tea'],headers=t.admin,json={'stock_quantity':0}).status_code==200
    assert pay(c,cid).status_code==409
    assert balance(t,s.campus_id)==500 and ledger_count(t,'PURCHASE')==0


@pytest.mark.parametrize("stale", ["expired", "revoked"])
def test_stale_station_logout(station, stale):
    from sqlalchemy import select
    from modules.auth.kiosk_models import KioskSession
    t, c, a = station
    activate(t, c)
    with t.session() as db:
        row = db.execute(select(KioskSession).where(KioskSession.device_id == t.kiosk_id)).scalar_one()
        if stale == "expired":
            row.expires_at = utcnow() - timedelta(seconds=1)
        else:
            row.revoked = 1
        db.commit()
    assert c.get('/api/v1/kiosk/menu').status_code == 401
    for user, password in [('admin', 'wrong'), ('staff', PASSWORD)]:
        assert c.post('/api/v1/kiosk/logout', headers={'X-Kiosk-Request': '1'}, json={'username': user, 'password': password}).status_code in (401, 403)
        assert c.get('/login.html', follow_redirects=False).status_code == 303
    assert c.post('/api/v1/kiosk/logout', headers={'X-Kiosk-Request': '1'}, json={'username': 'admin', 'password': PASSWORD}).status_code == 200
    assert c.get('/login.html', follow_redirects=False).status_code == 200
