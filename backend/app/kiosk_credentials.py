"""Local/demo-only kiosk credential, never valid in production."""
from pathlib import Path
from sqlalchemy import select
from core.config import get_settings
from core.errors import UnauthorizedError
from core.security import verify_secret
from core.tenancy import Principal
from modules.auth.models import Credential
from modules.institutions import service as institutions
from modules.users import service as users

HASH_FILE = Path(__file__).resolve().parents[1] / '.kiosk_password_hash'


def verify_kiosk_login(db, institution_code, username, password):
    error = UnauthorizedError('Invalid kiosk credentials')
    if get_settings().environment not in ('local', 'demo', 'test'):
        raise error
    institution = institutions.find_by_code(db, institution_code)
    if not institution or institution.status != 'ACTIVE' or username.strip() != 'admin':
        raise error
    credential = db.execute(select(Credential).where(
        Credential.institution_id == institution.id,
        Credential.username == username.strip(),
        Credential.status == 'ACTIVE')).scalar_one_or_none()
    if not credential or not HASH_FILE.is_file():
        raise error
    if not verify_secret(password, HASH_FILE.read_text().strip()):
        raise error
    user = users.get_user(db, institution_id=institution.id, user_id=credential.campus_user_id)
    if user.status != 'ACTIVE' or user.role != 'ADMIN':
        raise error
    return Principal(user_id=user.id, institution_id=institution.id, role='ADMIN',
                     username=credential.username, token_version=credential.token_version)
