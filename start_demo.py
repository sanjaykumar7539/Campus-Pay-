"""Local-only launcher with public demo logins and a separate database."""
import os
import secrets
import sys
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent
    if os.getenv("ENVIRONMENT", "local").lower() not in ("local", "test", "demo"):
        raise SystemExit("Demo launcher is disabled in production. Use main.py for a configured installation.")
    backend = root / "backend"
    sys.path.insert(0, str(backend))
    os.chdir(backend)
    # Ignore .env and existing database settings: never touch the user's old database.
    os.environ.update(ENVIRONMENT="demo", DATABASE_URL="sqlite:///./campuspay_common_demo.db",
        CAMPUSPAY_PAYMENT_AUTH="fingerprint", CAMPUSPAY_DEMO_FUNDING="false", CAMPUSPAY_LEGACY_MANUAL_PAYMENT="false")
    os.environ["SECRET_KEY"] = secrets.token_urlsafe(48)
    from core.demo_defaults import DEMO_PASSWORD, DEMO_INSTITUTION
    from app.demo_setup import prepare_demo
    result = prepare_demo(os.environ["DATABASE_URL"])
    port = int(os.getenv("CAMPUSPAY_PORT", "8002"))
    print(f"\nCampusPay UPDATED DEMO: http://127.0.0.1:{port}/login.html")
    print("Institution:", DEMO_INSTITUTION)
    if result["created"]:
        print("Login IDs: admin / canteen")
        print("Initial password for both accounts:", DEMO_PASSWORD)
    else:
        print("Existing demo retained. Changed passwords and balances were NOT reset.")
        print("Original login details are in DEMO_LOGINS.md; use your new password if changed.")
    print(f"Kiosk: http://127.0.0.1:{port}/kiosk.html")
    if os.getenv("CAMPUSPAY_HOST") == "0.0.0.0":
        print("LAN MODE enabled: On Android open http://<WINDOWS-LAN-IP>:%s/kiosk.html" % port)
        print("WARNING: Demo credentials over HTTP. Use ONLY a trusted isolated network.")
    print("Activate/unlock kiosk using the current ADMIN login and password.")
    for station, label in result["stations"].items():
        print("Station:", station, "-", label)
    print("Change each staff login/password through Account settings.")
    print("A real scanner adapter is still required to enroll fingers and pay.\n")
    import uvicorn
    uvicorn.run("app.main:app", host=os.getenv("CAMPUSPAY_HOST", "127.0.0.1"), port=port, reload=False)


if __name__ == "__main__":
    main()
