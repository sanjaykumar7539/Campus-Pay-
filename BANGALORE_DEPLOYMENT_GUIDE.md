# CampusPay — Bangalore Android kiosk field package (9 Oct 2026)

## Read this first
This is an integration-preparation release, **not a certified biometric-payment release**. The kiosk quotation states ELPRO ETK-006, Android 11, 4 GB RAM, 32 GB storage, 22-inch touch display, integrated fingerprint reader and 3-inch auto-cutter printer. User specifies scanner **Morpho MSO E2 1300**; the quotation itself does not certify this scanner model or the printer vendor/model. The integrated Android printer adapter includes `PosPrinterSDK.jar`, but hardware protocol compatibility must be checked on site.

### Ready in this package
- FastAPI backend and kiosk UI source; existing backend tests remain in `backend/tests/`.
- One successful authenticated scanner match now moves **PAY** challenge to `READY`; **ENROLL** still requires two consistent captures. Server still requires authenticated scanner agent, challenge nonce, replay protection, enrolled finger reference, active student, price checks and wallet payment endpoint.
- Kiosk setup screen takes username + password only. **Local demo** automatically sends station `DEMO-KIOSK-01`, `SCANNER` authentication mode and `THERMAL` receipt mode. These must be configured per station before production.
- Android printer companion source and `PosPrinterSDK.jar`; included prebuilt APK under `mobile/android/kiosk-companion/testing/` is **from the original upload**, not rebuilt/signed from modifications in this package. It is a printer diagnostics/test artifact; do not claim it enables Morpho matching.
- Local/demo-only separate kiosk password verifier and a password-hash setup script. **No kiosk password/hash is embedded in the ZIP**; existing normal admin and merchant credentials are not changed by the script.

### Blocking items for live fingerprint payment
1. Confirm kiosk's *actual* scanner hardware IDs and Android 11 SDK available for **Morpho MSO E2 1300**, including **1:N local identification**, capture, enroll, template lifecycle, and license. A generic RD Service/USB-detection app does **not** implement college 1:N matching.
2. Implement Android scanner-agent bridge against the official SDK. It must send only authenticated challenge responses (opaque `finger_ref`, unique `capture_id`, exact nonce) to the backend, never synthetic `matched=true` or fake identifiers. `scanner/adapter_contract.py` is currently a placeholder and raises `NotImplementedError`.
3. Verify exact thermal printer model/connection mode and whether `PosPrinterSDK.jar` supports it. Run real USB/Bluetooth/LAN tests. App handles print jobs but paper delivery is not sensor-verified.
4. Production persistent PostgreSQL backend, HTTPS, secret management, per-device credentials, enrollment consent, reconciliation, signed APK, real transactions tests, and a supported method for running long-lived local Android agents.

## What to take to Bangalore
- Kiosk Android 11 + admin access and permission to install APKs.
- Scanner maker + model + VID/PID, OEM Android SDK (AAR/JAR/SO + API docs + sample APK + license) and test enrollment permission.
- Printer maker/model/VID/PID, interface (USB/Bluetooth/LAN), paper roll and test print allowance.
- This ZIP + original printer SDK ZIP + APK file, laptop/USB data cable, hotspot, written test student account/wallet approval.
- Dedicated demo data only, no real student finger templates, passwords or finance data in an unprotected public demo.

## Before travel: Ubuntu local check
```
cd ~/Downloads/CampusPay-Android-Kiosk-Update/CampusPay
python3 scripts/preflight_bangalore.py
```
The scanner-adapter line will remain `PENDING` until SDK integration; that is intentional. For local demo backend start, ensure Python 3.12 venv, dependencies and database are prepared, then:
```
./backend/.venv/bin/python main.py
```
For an already-prepared local demo database and independently installed dependencies. Browser: `http://127.0.0.1:8000/kiosk.html`.

### Kiosk-only demo password
If using this release locally, `backend/.kiosk_password_hash` is intentionally **absent**. To configure the user-requested local demo password, *on your own trusted machine*:
```
cd backend
source .venv/bin/activate
python ../scripts/configure_demo_kiosk_password.py
```
Enter the demo-only password interactively. It does not reset the normal admin password. Only `local`/`demo`/`test` environments honor this separate hash. Keep the hash out of uploads, version control and production. If the file is absent, the original admin login remains required.

## Bangalore: simple on-site test order
1. Connect Android kiosk to trusted Wi-Fi. Confirm time/date, USB permissions, USB scanner and printer enumerations. Record device manufacturer/model and VID/PID.
2. Open your hosted CampusPay HTTPS kiosk URL from the Android browser. **Website loading does not prove either peripheral integration.** Verify menu, prices, cart, kiosk setup and no persistent passwords in the browser.
3. Install the existing printer companion *test* APK; check compatibility, permissions, printer SDK connection and test a **non-financial** print. Determine 80mm configuration if 3-inch printer; confirm actual printable dots/paper width with OEM.
4. Install the official Morpho SDK diagnostic/demo APK; verify Android 11 + USB access, fingerprint *capture*, approved *enrollment* and local *identification*. If SDK missing, stop fingerprint integration; do not bypass authentication.
5. After an approved adapter is implemented, provision scanner agent token securely on device. Ensure backend `scanner_online` becomes true **because an authenticated native agent is actually polling**, not due to a frontend toggle.
6. With consented demo users, test one enrolled student scan, unknown finger rejection, duplicate/replayed capture rejection, finger withdrawal, timeout, cancellation and kiosk session expiry.
7. With demo wallet only: check 1 successful payment, correct order total, **exactly one** ledger debit, receipt-job creation, exactly one paper receipt; rerun on slow network/restarts to check idempotency and uncertain print jobs.
8. Before live deployment: return to stronger station credentials, different station ID per kiosk, audited enrollment reset, production PostgreSQL and security review.

## Hosting decision
- **Immediate demonstration:** existing Ubuntu FastAPI service + a temporary authenticated/private HTTPS tunnel; avoid public exposure of real wallet or biometric data.
- **Stable site:** Vercel can host static frontend, but the existing same-origin `/api/v1` frontend expects a backend. Deploy persistent FastAPI separately with PostgreSQL or explicitly configure secure rewrites/proxy; do not deploy current SQLite database inside ephemeral Vercel Functions. Deployment has **not** been completed in this release.
- A hosted website alone cannot call vendor Android USB SDK from browser JavaScript. Native Android companion installed on the physical kiosk is required for scanner/receipt features.

## Known limitations in this specific release
- Firmware/device model and fingerprint SDK not provided; scanner capture and matching **not implemented**.
- Existing bundled APK **not rebuilt**; install/test only, not a final signed production release.
- Local-only kiosk credential design, demo station hardcoded. Not suitable as-is for public financial production.
- Thermal vendor library bundled, but ELPRO printer compatibility remains **unverified**.
- One-scan fingerprint transaction end-to-end not verified on real hardware.
- Existing tests and migrations must be rerun with matching application config and database after hardware adapter implementation.
