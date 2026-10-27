import pytest
from fastapi.testclient import TestClient
from core.demo_defaults import DEMO_PASSWORD, DEMO_INSTITUTION
from core.config import ConfigurationError
from core.errors import UnauthorizedError
from app.demo_setup import prepare_demo
from app.main import create_app
from modules.auth import service as auth


@pytest.fixture
def demo(tmp_path, monkeypatch):
    monkeypatch.setenv('ENVIRONMENT', 'test')
    monkeypatch.delenv('DATABASE_URL', raising=False)
    url = 'sqlite:///' + str(tmp_path / 'login-demo.db')
    assert prepare_demo(url)['created']
    application = create_app(url)
    yield url, application, TestClient(application)
    application.state.engine.dispose()


def signin(client, username, password=DEMO_PASSWORD):
    return client.post('/api/v1/auth/login', json={'institution_code':DEMO_INSTITUTION,'username':username,'password':password})


def test_all_default_staff_logins_and_kiosk_activation(demo):
    _,app,client=demo
    for username,role in [('admin','ADMIN'),('canteen','MERCHANT_STAFF')]:
        r=signin(client,username)
        assert r.status_code==200,r.text
        assert r.json()['data']['role']==role
    r=client.post('/api/v1/kiosk/setup',json={'institution_code':DEMO_INSTITUTION,'username':'admin','password':DEMO_PASSWORD,'device_id':'DEMO-KIOSK-01'})
    assert r.status_code==200,r.text
    menu=client.get('/api/v1/kiosk/menu').json()['data']
    assert menu['merchant']['name']=='Common Canteen'
    assert menu['categories'] and not menu['scanner_online']


def test_changed_credentials_survive_demo_restart_without_recredit(demo):
    url,app,client=demo
    token=signin(client,'admin').json()['data']['access_token']
    headers={'Authorization':'Bearer '+token}
    before=client.get('/api/v1/admin/students',headers=headers).json()['data']
    r=client.patch('/api/v1/auth/credentials',headers=headers,json={'current_password':DEMO_PASSWORD,'username':'my.admin','new_password':'Changed-Demo-Password-789'})
    assert r.status_code==200,r.text
    assert prepare_demo(url)['created'] is False
    assert signin(client,'admin').status_code==401
    result=signin(client,'my.admin','Changed-Demo-Password-789')
    assert result.status_code==200
    after=client.get('/api/v1/admin/students',headers={'Authorization':'Bearer '+result.json()['data']['access_token']}).json()['data']
    assert [(s['campus_id'],s['available_cu']) for s in before]==[(s['campus_id'],s['available_cu']) for s in after]
    assert all(not s['pin_configured'] and s['fingerprint_status']=='NOT_ENROLLED' for s in after)


def test_defaults_and_seed_disabled_in_production(demo,monkeypatch):
    url,app,_=demo
    monkeypatch.setenv('ENVIRONMENT','production')
    with pytest.raises(ConfigurationError):
        prepare_demo(url)
    with app.state.session_factory() as db:
        with pytest.raises(UnauthorizedError,match='demo password'):
            auth.login(db,institution_code=DEMO_INSTITUTION,username='admin',password=DEMO_PASSWORD)
