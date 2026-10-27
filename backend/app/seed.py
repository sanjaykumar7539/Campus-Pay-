"""Demo seed data for the E.G.S. Pillay Engineering College pilot.

    cd backend && alembic upgrade head && python -m app.seed

Credentials are NEVER hard-coded: passwords and PINs come from
CAMPUSPAY_DEMO_PASSWORD / CAMPUSPAY_DEMO_PIN when set, otherwise they are generated
randomly and printed once. The seed uses the DEMO funding path (origin=DEMO in the
Institution Ledger) — this is not the production recharge workflow.
Safe to re-run: it does nothing if the institution already exists.
"""
from __future__ import annotations

import os
import secrets
import string
import sys
from pathlib import Path
from typing import Callable, Optional

from alembic import command
from alembic.config import Config

from core.config import get_settings
from core.database import make_engine, make_session_factory

INSTITUTION_CODE = "EGS-ENGG"
INSTITUTION_NAME = "E.G.S. Pillay Engineering College"
BACKEND_DIR = Path(__file__).resolve().parents[1]

STUDENTS = [("EGS-STD-0001", "Arun Kumar", 500), ("EGS-STD-0002", "Divya Shree", 300),
            ("EGS-STD-0003", "Karthik Raja", 150),
            ("EGS-STD-0004", "Priya Dharshini", 5),      # deliberately low: insufficient-balance demo
            ("EGS-STD-0005", "Suresh Babu", 200)]

CANTEEN_MENU = {
    "Meals": [("Veg Meals", 60, "AVAILABLE", 30), ("Chicken Biryani", 90, "AVAILABLE", 20), ("Curd Rice", 40, "AVAILABLE", 25)],
    "Snacks": [("Samosa", 15, "AVAILABLE", 40), ("Veg Puff", 20, "AVAILABLE", 35), ("Medu Vada", 12, "AVAILABLE", 30)],
    "Beverages": [("Tea", 10, "AVAILABLE", 50), ("Coffee", 15, "AVAILABLE", 50), ("Lime Juice", 25, "AVAILABLE", 25), ("Badam Milk", 30, "SOLD_OUT", 0)],
}
STATIONERY_MENU = {
    "Notebooks": [("Ruled Notebook", 45, "AVAILABLE", 50), ("Record Book", 120, "AVAILABLE", 25)],
    "Writing": [("Blue Pen", 10, "AVAILABLE", 100), ("Pencil", 5, "AVAILABLE", 100), ("Geometry Box", 85, "UNAVAILABLE", 15)],
}


def run_migrations(database_url: str) -> None:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    cfg.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    cfg.attributes["url"] = database_url
    command.upgrade(cfg, "head")


def _random_secret(n: int = 12) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(n))


def seed(database_url: Optional[str] = None, out: Callable[[str], None] = print) -> Optional[dict]:
    # Imported here so importing this module never pulls the whole app.
    from modules.auth import service as auth
    from modules.devices import service as devices
    from modules.institutions import service as institutions
    from modules.merchants import service as merchants
    from modules.users import service as users
    from modules.wallets import service as wallets

    url = database_url or get_settings().database_url
    run_migrations(url)
    engine = make_engine(url)
    db = make_session_factory(engine)()
    os.environ["CAMPUSPAY_DEMO_FUNDING"] = "true"  # the seed IS demo funding
    try:
        if institutions.find_by_code(db, INSTITUTION_CODE):
            out(f"Already seeded ({INSTITUTION_CODE}). Nothing to do.")
            return None
        password = os.getenv("CAMPUSPAY_DEMO_PASSWORD") or _random_secret()
        shared_pin = os.getenv("CAMPUSPAY_DEMO_PIN")
        inst = institutions.create_institution(db, name=INSTITUTION_NAME, code=INSTITUTION_CODE)
        actor = "seed-script"

        admin = users.create_user(db, institution_id=inst.id, name="Institution Administrator", role=users.ADMIN,
                                  unique_identifier="EGS-ADM-0001", actor_id=actor)
        auth.create_credential(db, institution_id=inst.id, campus_user_id=admin.id, username="admin",
                               password=password, actor_id=actor)

        canteen = merchants.create_merchant(db, institution_id=inst.id, name="Main Canteen", category="Canteen", actor_id=actor)
        canteen2 = merchants.create_merchant(db, institution_id=inst.id, name="Canteen 2", category="Canteen", actor_id=actor)
        stationery = merchants.create_merchant(db, institution_id=inst.id, name="Campus Stationery Shop",
                                               category="Stationery", actor_id=actor)
        merchants.create_merchant(db, institution_id=inst.id, name="Old Print Shop", category="Printing",
                                  status="INACTIVE", actor_id=actor)  # inactive-merchant demo

        for username, uid, merchant, label in (("canteen", "EGS-STF-CANTEEN", canteen, "Canteen Staff"),
                                               ("stationery", "EGS-STF-STATIONERY", stationery, "Stationery Staff")):
            staff = users.create_user(db, institution_id=inst.id, name=label, role=users.MERCHANT_STAFF,
                                      unique_identifier=uid, actor_id=actor)
            auth.create_credential(db, institution_id=inst.id, campus_user_id=staff.id, username=username,
                                   password=password, actor_id=actor)
            merchants.assign_staff(db, institution_id=inst.id, campus_user_id=staff.id, merchant_id=merchant.id)

        kiosks = {}
        for name, merchant in (("Main Canteen Kiosk 1", canteen), ("Main Canteen Kiosk 2", canteen),
                               ("Canteen 2 Kiosk 1", canteen2), ("Stationery Kiosk 1", stationery)):
            kiosks[name] = devices.register_kiosk(db, institution_id=inst.id, name=name, merchant_id=merchant.id,
                                                  actor_id=actor).id

        for merchant, menu in ((canteen, CANTEEN_MENU), (stationery, STATIONERY_MENU)):
            for order_no, (cat_name, items) in enumerate(menu.items()):
                cat = merchants.create_category(db, institution_id=inst.id, merchant_id=merchant.id, name=cat_name,
                                                display_order=order_no, actor_user_id=actor, actor_role=users.ADMIN)
                for item in items:
                    merchants.create_product(db, institution_id=inst.id, category_id=cat["id"], name=item[0],
                                             price_cu=item[1], description=None,
                                             availability=item[2] if len(item) > 2 else "AVAILABLE", stock_quantity=item[3] if len(item) > 3 else 25,
                                             actor_user_id=actor, actor_role=users.ADMIN)

        pins = {}
        for campus_id, name, funding in STUDENTS:
            student = users.create_user(db, institution_id=inst.id, name=name, role=users.STUDENT,
                                        unique_identifier=campus_id, actor_id=actor)
            wallets.create_wallet(db, institution_id=inst.id, campus_user_id=student.id, actor_id=actor)
            wallets.credit_demo_funding(db, institution_id=inst.id, campus_user_id=student.id, amount_cu=funding,
                                        reference=f"SEED-{campus_id}", actor_id=actor, actor_role=users.ADMIN)
            pin = shared_pin or "".join(secrets.choice(string.digits) for _ in range(4))
            auth.set_payment_pin(db, institution_id=inst.id, campus_user_id=student.id, pin=pin, actor_id=actor)
            pins[campus_id] = pin
        db.commit()

        out("Seed complete.")
        out(f"Institution code : {INSTITUTION_CODE}  ({INSTITUTION_NAME})")
        out(f"Logins (password {'from CAMPUSPAY_DEMO_PASSWORD' if os.getenv('CAMPUSPAY_DEMO_PASSWORD') else 'GENERATED - shown once'}): "
            f"admin / canteen / stationery  ->  {password}")
        out("Students (Campus ID -> starting balance, payment PIN):")
        for campus_id, name, funding in STUDENTS:
            out(f"  {campus_id}  {name:<16} {funding:>4} CU   PIN {pins[campus_id]}")
        out("Kiosks: " + ", ".join(kiosks))
        return {"password": password, "pins": pins, "kiosks": kiosks}
    finally:
        db.close()
        engine.dispose()


if __name__ == "__main__":
    seed()
    sys.exit(0)
