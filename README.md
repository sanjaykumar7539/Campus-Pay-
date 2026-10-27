# CampusPay — fingerprint kiosk upgrade

An upgrade of the supplied CampusPay project, retaining its wallet/ledger transaction core and staff portals.

**Release status: tested software candidate, not a certified or deployed production system.** The scanner model is undecided. Real biometric matching is deliberately not simulated by the application. Payments stay unavailable until a trusted scanner adapter is connected. Read [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) before using real money or biometric data.

## What changed

- Admin: register students and wallets without PINs; start supervised two-scan fingerprint enrollment; view enrollment status and revoke fingerprints; add canteens with staff accounts; add products; register and disable stations; rotate scanner credentials; retrieve receipts; reconcile wallets and ledger.
- Merchant: manage own menu and inventory; open/close own canteen for new orders; fulfill paid orders. A merchant cannot undo an administrator's account deactivation or manage another merchant.
- Student kiosk: staff activates a dedicated station once, then students see the menu directly. No personal student login or PIN. Select items, choose Order & pay, scan an enrolled finger, lift it, scan the same finger again, then debit the matching student's wallet.
- Receipt: itemized paid order, remaining balance, collection/support warning, print action, and return to the menu. The station also clears a completed receipt after 30 seconds. Failed printing never triggers another debit.
- Security: HttpOnly kiosk cookie, server-side revocation, short-lived two-scan grants, one-use capture IDs/nonces, device and tenant checks, idempotent payment, production configuration checks, security headers and readiness probe.
- Updated and pinned Python dependencies; replaced python-jose with PyJWT after a dependency audit.

## Mobile authentication update

Mobile devices now use two server-verified WebAuthn confirmations with an enrolled platform passkey; integrated kiosk readers retain the two-scan flow. Admin can enroll the account holder's mobile passkey. Receipts appear automatically and return to the menu after 15 seconds. See [docs/MOBILE_AUTH.md](docs/MOBILE_AUTH.md) for the required HTTPS origin configuration and phone testing. WebAuthn cannot enforce fingerprint-only authentication.

## Android kiosk hardware update

Android companion source and testing APK support the supplied printer SDK through USB, Bluetooth and LAN, 58/80mm raster receipts, separate printer credentials and a server-verified print queue. Explicit kiosk authentication modes prevent Android kiosks from being treated as phones. Mobile sessions and scanner queues are separated. Morpho E2 RD diagnostics are included; standalone student matching still requires the vendor MSO SDK. See [Tanglish Android setup](docs/ANDROID_KIOSK_SETUP_TANGLISH.md). Real-device and production acceptance remain pending.

## Default-login demo

For ready-made local accounts, double-click **START_DEMO.bat**. See [DEMO_LOGINS.md](DEMO_LOGINS.md) for all login IDs, the initial password, station IDs and password-change steps. It uses a separate local demo database and preserves changed credentials on restart.

## Start here

1. [START_HERE_WINDOWS.md](START_HERE_WINDOWS.md): local setup and upgrading an existing database.
2. [scanner/INTEGRATION.md](scanner/INTEGRATION.md): implement the selected scanner SDK adapter.
3. [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md): required deployment work and remaining features.
4. [docs/KIOSK_WINDOWS.md](docs/KIOSK_WINDOWS.md): lock down the physical ordering machine.
5. [VALIDATION.md](VALIDATION.md): executed checks and explicit test limitations.

Public demo credentials are included at the user's request and are blocked in production. No real fingerprint samples, scanner credentials, environment secrets, or database are shipped in this source archive. Preserve your existing database from the original CampusPay.zip and back it up before migration. Existing documentation under docs/ describing PIN-based P1 flows is historical; this README and the new guides describe the upgraded fingerprint flow.

## Source layout

- backend/app/kiosk_service.py and kiosk_router.py: device sessions, enrollment and checkout orchestration.
- backend/modules/auth/kiosk_models.py: persistent grants, sessions and opaque enrollment references.
- backend/modules/payments/: atomic wallet/ledger purchase and immutable receipt snapshot.
- frontend/demo/: updated admin, merchant and kiosk screens.
- scanner/: native worker and explicit unimplemented hardware adapter contract.
- backend/tests/test_fingerprint_kiosk.py: test-only synthetic scanner assertions, including concurrency.

Two scans of the same finger are a two-step biometric confirmation, not two independent authentication factors. A shared device session never identifies the paying student; only the scanner's enrolled match does.
