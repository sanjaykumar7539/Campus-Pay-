# Default logins — local checking only

## Quick start

1. Install Python 3.12 and extract this ZIP.
2. Double-click **START_DEMO.bat**. On the first run it installs dependencies (internet required) and creates sample accounts, menus, stations and student wallet balances.
3. Leave that window running and open **http://127.0.0.1:8000/login.html**.
4. Institution code: **EGS-ENGG**.

| Screen / account | Login ID | Initial password |
| --- | --- | --- |
| Admin | `admin` | `CampusDemo@123` |
| Merchant — Main Canteen | `canteen` | `CampusDemo@123` |
| Merchant — Canteen 2 | `canteen2` | `CampusDemo@123` |
| Merchant — Stationery shop | `stationery` | `CampusDemo@123` |

Select Admin for the admin account and Merchant for the canteen account. Passwords are case-sensitive. These credentials are public demo values, not production secrets.

## Student / kiosk

Students do **not** enter a personal login or password. Open **http://127.0.0.1:8000/kiosk.html** (or choose Student from the login page). Staff activates it once:

| Field | Value |
| --- | --- |
| Institution | `EGS-ENGG` |
| Admin login | `admin` |
| Initial admin password | `CampusDemo@123` |
| Common Canteen station ID | `DEMO-KIOSK-01` |

Choose one station. After activation the menu opens directly. Staff access / logout requires the current administrator login and password. The kiosk browser intentionally redirects other app pages back to the menu until unlocked; use a separate browser/profile for the staff portal.

Sample student IDs: `EGS-STD-0001` through `EGS-STD-0005`. Sample starting balances: ₹500, ₹300, ₹150, ₹5 and ₹200. These are demo credits only. No student PIN or password is provisioned. Fingerprints are initially NOT_ENROLLED.

You can check staff logins, menu, cart and administration without a scanner. Real fingerprint enrollment and payment still require the selected scanner's native adapter. Default logins do not bypass biometric authorization.

## Change the defaults after checking

1. Sign in to each staff account.
2. Open **Account settings**.
3. Enter its current password, enter a new login ID and/or password, then save.
4. Sign in again using the new credentials. Kiosk activation/unlock then uses the updated admin credentials.

The launcher creates accounts only on the first run. It **never resets** changed passwords, usernames, balances, menu or transaction history on later runs. Existing seeded demo data lives in `backend/campuspay_common_demo.db`. The launcher ignores `.env` and uses this separate local database; it does not modify the original `campuspay_demo.db` or your configured production database. Stop another server on port 8000 before starting it.

If you already have accounts in the older application/database, these defaults do not overwrite them. Use START_DEMO.bat for the separate default-account demo. Use the previous application's credentials for the existing installation.

Production mode rejects the public demo password, and the demo launcher refuses to run when ENVIRONMENT is production. Use the production setup guide and a clean approved financial setup before launch; changing passwords alone does not convert demo funds into real balances.

Manual alternative after dependencies are installed: `.venv\Scripts\python.exe start_demo.py` from the project root.
