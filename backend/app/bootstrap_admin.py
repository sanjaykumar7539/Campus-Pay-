"""Create an empty institution and first administrator without demo users/funding."""
import getpass
from sqlalchemy import select
import app.models_registry
from core.config import get_settings
from core.database import make_engine, make_session_factory
from modules.institutions import service as institutions
from modules.users import service as users
from modules.auth import service as auth


def main():
    code = input("Institution code: ").strip()
    name = input("Institution name: ").strip()
    username = input("Administrator login: ").strip()
    password = getpass.getpass("Administrator password (12+ characters): ")
    if password != getpass.getpass("Confirm password: ") or len(password) < 12 or len(password.encode()) > 72:
        raise SystemExit("Passwords must match and be 12+ characters, at most 72 UTF-8 bytes")
    if not code or not name or not username:
        raise SystemExit("All fields are required")
    engine = make_engine(get_settings().database_url)
    with make_session_factory(engine)() as db:
        if institutions.find_by_code(db, code):
            raise SystemExit("Institution already exists. Use existing administrator account recovery procedures.")
        inst = institutions.create_institution(db, name=name, code=code)
        admin = users.create_user(db, institution_id=inst.id, name="Administrator", role="ADMIN", unique_identifier="ADMIN-INITIAL")
        auth.create_credential(db, institution_id=inst.id, campus_user_id=admin.id, username=username, password=password)
        db.commit()
    print("Institution and administrator created. No demo students or balances were added.")


if __name__ == "__main__":
    main()
