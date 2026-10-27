"""Provision a dedicated local demo once; never overwrite changed credentials."""
import os
from sqlalchemy import select, func
import app.models_registry  # noqa: F401
from core.config import get_settings, ConfigurationError
from core.database import make_engine, make_session_factory
from core.demo_defaults import DEMO_PASSWORD, DEMO_INSTITUTION
from modules.institutions.models import Institution
from modules.merchants.models import Merchant, ProductCategory
from modules.institutions import service as institutions
from modules.users import service as users
from modules.auth import service as auth
from modules.merchants import service as merchants
from modules.devices import service as devices
from modules.wallets import service as wallets
from app.seed import run_migrations, CANTEEN_MENU, STATIONERY_MENU, STUDENTS

STATIONS = {"DEMO-KIOSK-01": "Common Canteen"}


def ensure_stationery(db, institution_id):
    common = db.execute(select(Merchant).where(Merchant.institution_id == institution_id, Merchant.name == "Common Canteen")).scalar_one_or_none()
    if not common:
        return
    existing = db.execute(select(ProductCategory).where(ProductCategory.institution_id == institution_id, ProductCategory.merchant_id == common.id, ProductCategory.name == "Stationery")).scalar_one_or_none()
    if existing:
        return
    cat = merchants.create_category(db, institution_id=institution_id, merchant_id=common.id, name="Stationery", display_order=3, actor_user_id=None, actor_role="ADMIN")
    for items in STATIONERY_MENU.values():
        for label, price, availability, stock in items:
            merchants.create_product(db, institution_id=institution_id, category_id=cat['id'], name=label, price_cu=price, description="Campus stationery essentials", availability=availability, stock_quantity=stock, actor_user_id=None, actor_role="ADMIN")


def prepare_demo(database_url):
    if get_settings().environment not in ("local", "test", "demo") or not database_url.startswith("sqlite:///"):
        raise ConfigurationError("Default-account demo setup is restricted to local SQLite evaluation")
    run_migrations(database_url)
    engine = make_engine(database_url)
    previous_funding = os.environ.get("CAMPUSPAY_DEMO_FUNDING")
    try:
        with make_session_factory(engine)() as db:
            existing_inst = institutions.find_by_code(db, DEMO_INSTITUTION)
            if existing_inst:
                ensure_stationery(db, existing_inst.id)
                db.commit()
                return {"created": False, "stations": STATIONS}
            if db.execute(select(func.count()).select_from(Institution)).scalar_one():
                raise ConfigurationError("Demo setup refuses to seed a database containing another institution")
            inst = institutions.create_institution(db, name="E.G.S. Pillay Engineering College", code=DEMO_INSTITUTION)
            admin = users.create_user(db, institution_id=inst.id, name="Demo Administrator", role="ADMIN", unique_identifier="EGS-ADM-0001")
            auth.create_credential(db, institution_id=inst.id, campus_user_id=admin.id, username="admin", password=DEMO_PASSWORD)
            for username, station_id, name, menu in (
                ("canteen", "DEMO-KIOSK-01", STATIONS["DEMO-KIOSK-01"], CANTEEN_MENU),
            ):
                m = merchants.create_merchant(db, institution_id=inst.id, name=name, category="Stationery" if username == "stationery" else "Canteen", actor_id=admin.id, actor_role="ADMIN")
                staff = users.create_user(db, institution_id=inst.id, name=name + " Staff", role="MERCHANT_STAFF", unique_identifier="EGS-STF-" + username.upper())
                auth.create_credential(db, institution_id=inst.id, campus_user_id=staff.id, username=username, password=DEMO_PASSWORD)
                merchants.assign_staff(db, institution_id=inst.id, campus_user_id=staff.id, merchant_id=m.id)
                devices.register_kiosk(db, institution_id=inst.id, name=name + " Demo Station", merchant_id=m.id, device_id=station_id, actor_id=admin.id, actor_role="ADMIN")
                for index, (category, items) in enumerate(menu.items()):
                    cat = merchants.create_category(db, institution_id=inst.id, merchant_id=m.id, name=category, display_order=index, actor_user_id=admin.id, actor_role="ADMIN")
                    for label, price, availability, stock in items:
                        merchants.create_product(db, institution_id=inst.id, category_id=cat['id'], name=label, price_cu=price, description=None, availability=availability, stock_quantity=stock, actor_user_id=admin.id, actor_role="ADMIN")
            ensure_stationery(db, inst.id)
            os.environ["CAMPUSPAY_DEMO_FUNDING"] = "true"
            for campus_id, name, funding in STUDENTS:
                u = users.create_user(db, institution_id=inst.id, name=name, role="STUDENT", unique_identifier=campus_id)
                wallets.create_wallet(db, institution_id=inst.id, campus_user_id=u.id)
                wallets.credit_demo_funding(db, institution_id=inst.id, campus_user_id=u.id, amount_cu=funding, reference="DEMO-DEFAULT-" + campus_id, actor_id=admin.id, actor_role="ADMIN")
            db.commit()
            return {"created": True, "stations": STATIONS}
    finally:
        engine.dispose()
        if previous_funding is None:
            os.environ.pop("CAMPUSPAY_DEMO_FUNDING", None)
        else:
            os.environ["CAMPUSPAY_DEMO_FUNDING"] = previous_funding
