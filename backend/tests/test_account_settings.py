"""Credential changes require reauthentication, preserve tenant scope and revoke old sessions."""
import json
import pytest
from tests.helpers import PASSWORD, build_world, sql
from tests.conftest import alembic_upgrade


def login(w, username='admin', password=PASSWORD):
    return w.client().post('/api/v1/auth/login', json={
        'institution_code': w.code, 'username': username, 'password': password})


@pytest.mark.parametrize('actor', ['admin', 'staff'])
def test_change_id_and_password_revokes_sessions(world, actor):
    old = world.headers(actor)
    password = 'New-Campus-Secret-2026'
    result = world.client().patch('/api/v1/auth/credentials', headers=old, json={
        'current_password': PASSWORD, 'username': actor+'.new', 'new_password': password})
    assert result.status_code == 200, result.text
    assert result.json()['data']['sign_in_required'] is True
    assert world.client().get('/api/v1/auth/me', headers=old).status_code == 401
    assert login(world, actor).status_code == 401
    assert login(world, actor+'.new').status_code == 401
    new_login = login(world, actor+'.new', password)
    assert new_login.status_code == 200
    headers = {'Authorization': 'Bearer '+new_login.json()['data']['access_token']}
    assert world.client().get('/api/v1/auth/me', headers=headers).json()['data']['username'] == actor+'.new'
    assert world.client().patch('/api/v1/auth/credentials', headers=old, json={
        'current_password': password, 'username': 'hijacked'}).status_code == 401
    audit = sql(world, "SELECT metadata_json FROM audit_logs WHERE event_type='CREDENTIAL_UPDATED'")
    assert audit and password not in json.dumps([r[0] for r in audit]) and PASSWORD not in json.dumps([r[0] for r in audit])
    hashes = sql(world, 'SELECT password_hash FROM credentials WHERE username=:n', n=actor+'.new')
    assert hashes[0][0] != password


def test_bad_current_password_makes_no_changes(world):
    response = world.client().patch('/api/v1/auth/credentials', headers=world.admin, json={
        'current_password': 'wrong', 'username': 'changed'})
    assert response.status_code == 422
    assert response.json()['error']['code'] == 'CURRENT_PASSWORD_INVALID'
    assert world.client().get('/api/v1/auth/me', headers=world.admin).status_code == 200
    assert login(world).status_code == 200


def test_duplicate_login_id_is_atomic(world):
    response = world.client().patch('/api/v1/auth/credentials', headers=world.admin, json={
        'current_password': PASSWORD, 'username': 'staff', 'new_password': 'Different-Password-123'})
    assert response.status_code == 409
    assert login(world).status_code == 200
    assert world.client().get('/api/v1/auth/me', headers=world.admin).status_code == 200


def test_change_is_tenant_scoped_and_cannot_target_another_user(world, app):
    other = build_world(app)
    response = world.client().patch('/api/v1/auth/credentials', headers=world.admin, json={
        'current_password': PASSWORD, 'username': 'another_admin', 'campus_user_id': other.admin_id})
    assert response.status_code == 422
    for w in [world, other]:
        assert w.client().patch('/api/v1/auth/credentials', headers=w.admin, json={
            'current_password': PASSWORD, 'username': 'another_admin'}).status_code == 200
    assert login(world, 'another_admin').status_code == 200
    assert login(other, 'another_admin').status_code == 200


@pytest.mark.parametrize('fields', [{}, {'username':'  '}, {'username':'a'}, {'new_password':'short'},
    {'new_password':PASSWORD}, {'new_password':'é'*40}, {'new_password':''}])
def test_invalid_changes_are_rejected(world, fields):
    response = world.client().patch('/api/v1/auth/credentials', headers=world.admin,
                                  json={'current_password': PASSWORD, **fields})
    assert response.status_code == 422
    assert login(world).status_code == 200


def test_password_only_change_invalidates_session(world):
    headers = world.admin
    assert world.client().patch('/api/v1/auth/credentials', headers=headers, json={
        'current_password': PASSWORD, 'new_password': 'Only-New-Password-2026'}).status_code == 200
    assert world.client().get('/api/v1/auth/me', headers=headers).status_code == 401
    assert login(world, password='Only-New-Password-2026').status_code == 200


def test_unauthenticated_change_is_rejected(client):
    assert client.patch('/api/v1/auth/credentials', json={
        'current_password': PASSWORD, 'username':'another'}).status_code == 401


def test_existing_credentials_survive_upgrade(tmp_path):
    import sqlite3
    path = tmp_path/'existing.db'
    url = f'sqlite:///{path}'
    alembic_upgrade(url, '0002_p1_campus_commerce')
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO institutions(id,name,code,status) VALUES('i','Test','TEST','ACTIVE')")
        db.execute("INSERT INTO campus_users(id,institution_id,name,role,unique_identifier,status) VALUES('u','i','Admin','ADMIN','ADM','ACTIVE')")
        db.execute("INSERT INTO credentials(id,institution_id,campus_user_id,username,password_hash,status) VALUES('c','i','u','admin','preserved-hash','ACTIVE')")
    alembic_upgrade(url)
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT username,password_hash,token_version FROM credentials').fetchone() == ('admin','preserved-hash',0)
