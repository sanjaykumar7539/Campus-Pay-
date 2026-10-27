# Start here — Windows

## Quick check with default logins

Install Python 3.12, then double-click **START_DEMO.bat**. Open http://127.0.0.1:8000/login.html. Institution: **EGS-ENGG**. IDs: **admin**, **canteen**, **canteen2**, **stationery**. Initial password for all: **CampusDemo@123**. Read **DEMO_LOGINS.md** for kiosk station IDs and changing passwords. This creates a separate demo database and never resets changed passwords.

## Manual local evaluation (empty institution / existing database)

Install Python 3.12. Open PowerShell in the extracted CampusPay directory:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
Copy-Item .env.example .env
```

The default local database is backend/campuspay_demo.db. This source package does not include the original database. For an existing installation, preserve the database and follow the upgrade procedure below. For a new empty installation, create the schema and administrator:

```powershell
$env:ENVIRONMENT = 'local'
$env:CAMPUSPAY_PAYMENT_AUTH = 'fingerprint'
Set-Location backend
..\.venv\Scripts\python.exe -m alembic upgrade head
..\.venv\Scripts\python.exe -m app.bootstrap_admin
Set-Location ..
.\.venv\Scripts\python.exe main.py
```

Open http://127.0.0.1:8000/login.html. Enter the institution code and credentials you created. The staff portals keep the existing EGS visual branding; replace the logo and institution-specific text before another institution deploys this package.

Alternatively, for **synthetic local demonstrations only**, set CAMPUSPAY_DEMO_FUNDING=true and run `python -m app.seed` from backend using the virtual environment. It prints generated demo credentials once. Disable demo funding afterward. The seeded PINs are ignored by fingerprint checkout. No fingerprint adapter is bundled, so this does not enable real biometric payments.

## Admin setup sequence

1. Add a merchant/canteen with its staff account. Its initial Menu category is created automatically.
2. Add menu products and stock. Zero-stock products cannot be ordered. Refilled sold-out items must be explicitly made AVAILABLE.
3. Register a station assigned to that canteen. Copy its station ID.
4. Provision its scanner key and install it in the protected native scanner worker. A key is shown once. Rotating it revokes the old key and cancels pending scans.
5. Register each student. Registration creates an empty wallet and never asks for a PIN.
6. With the student present, confirm informed enrollment consent, select the scanner station and start enrollment. The student scans the same finger twice. The native matcher must prove the samples match.
7. On the kiosk computer, open /kiosk.html. Enter administrator credentials and the station ID once. Staff credentials are not retained in the student session.
8. The menu remains available for successive students. The station session expires after seven days or when replaced, revoked, or the device is disabled. Staff must reactivate it after expiry or browser-profile reset.

Enrollment requires an online scanner. A revoked enrollment blocks pending as well as future payments. Changing an already registered finger requires a supervised operator migration; this release intentionally refuses rebinding an enrollment to a different finger. Do not delete database rows or reuse scanner slot IDs to bypass this protection.

## Upgrade the existing database

1. Stop the existing server; preserve the original zip and create a verified backup of the existing database and configuration.
2. Extract this release to a new folder. Do not replace live files while requests are being processed.
3. Install the new dependencies into a new virtual environment.
4. Copy your existing SQLite database into backend only for local evaluation, or set DATABASE_URL to your staging PostgreSQL database. Do not copy production data onto public or shared devices.
5. From backend run `python -m alembic upgrade head`. DATABASE_URL now takes precedence over alembic.ini. Revision 0005 adds tables and the accepting_orders column; it does not remove existing balances or payment history.
6. Run the tests against staging, check /api/v1/ready and perform reconciliation. Validate backups and rollback on a separate environment.
7. Re-enroll fingerprints through the new workflow. PIN hashes cannot be converted into fingerprints.

Migrations are forward-only. Rollback means restoring the prior application and a verified matching database backup, with a plan for any intervening transactions. Never restore an old backup over newer financial activity without reconciliation.

## Testing

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m pytest -q
..\.venv\Scripts\python.exe -m pip_audit
```

Set CAMPUSPAY_TEST_POSTGRES_URL to a disposable PostgreSQL instance with CREATE DATABASE privileges to run the PostgreSQL tests. Never point tests at a production database. See VALIDATION.md for which checks were actually executed for this package.

## Wallet funding

This release retains the original demo funding endpoint for local tests only. It is disabled in production and is no longer presented as a real top-up operation in the admin UI. Production payment acknowledgement, authorized wallet recharge, refund, and merchant settlement workflows still need institution-specific implementation before launch. Do not populate live wallet balances with demo credits or direct SQL.
