"""Run from backend/ with `python ../scripts/configure_demo_kiosk_password.py`."""
from getpass import getpass
from pathlib import Path
from core.config import get_settings
from core.security import hash_secret
if get_settings().environment not in ('local','demo','test'):
    raise SystemExit('Refusing: kiosk-only demo password is not for production')
password=getpass('New local-demo kiosk password: ')
confirm=getpass('Confirm: ')
if len(password)<5 or password!=confirm:
    raise SystemExit('Password mismatch or too short')
path=Path(__file__).resolve().parents[1]/'backend/.kiosk_password_hash'
path.write_text(hash_secret(password)+'\n')
path.chmod(0o600)
print('Kiosk demo password hash saved (never upload this file).')
