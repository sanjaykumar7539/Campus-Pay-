import pytest
from core.config import get_settings, ConfigurationError
from app.hardening import install
from fastapi import FastAPI


@pytest.fixture
def production(monkeypatch):
    monkeypatch.setenv('ENVIRONMENT','production')
    monkeypatch.setenv('DATABASE_URL','postgresql+psycopg2://test:test@localhost/test')
    monkeypatch.setenv('SECRET_KEY','R4ndomForUnitTestsOnly_'+'X'*40)
    monkeypatch.setenv('CAMPUSPAY_PAYMENT_AUTH','fingerprint')
    monkeypatch.setenv('CAMPUSPAY_DEMO_FUNDING','false')
    monkeypatch.setenv('CAMPUSPAY_LEGACY_MANUAL_PAYMENT','false')
    monkeypatch.setenv('CAMPUSPAY_ALLOWED_HOSTS','pay.example.edu')
    monkeypatch.setenv('CAMPUSPAY_BCRYPT_ROUNDS','12')
    return monkeypatch


@pytest.mark.parametrize('key,value',[
    ('DATABASE_URL','sqlite:///test.db'),
    ('SECRET_KEY','REPLACE_WITH_AT_LEAST_32_RANDOM_CHARACTERS'),
    ('CAMPUSPAY_PAYMENT_AUTH','pin'),
    ('CAMPUSPAY_DEMO_FUNDING','true'),
    ('CAMPUSPAY_ALLOWED_HOSTS','*'),
    ('CAMPUSPAY_BCRYPT_ROUNDS','4'),
])
def test_unsafe_production_configuration_refused(production,key,value):
    production.setenv(key,value)
    with pytest.raises(ConfigurationError):
        install(FastAPI(),get_settings())


def test_valid_production_settings_install_without_connecting_to_database(production):
    install(FastAPI(),get_settings())
