# P1 Campus Commerce — MVP → Governed Architecture Mapping

Status: implementation note (does not replace ARCHITECTURE.md). Decisions are recorded in ADR-0004 … ADR-0008 (Proposed).

## 1. Reconciliation summary
| Input | Finding |
|---|---|
| Governed repo (main snapshot 2026-09-19) | Documentation-led scaffold; `backend/modules/*` held only `.gitkeep`; ADR-0003 fixes module folders; no Order/Catalog/Ledger/PIN/kiosk concepts in SRS/PRD/Architecture. |
| MVP (`campuspay-mvp.zip`) | FastAPI + SQLAlchemy, SQLite/PostgreSQL, `create_all()`, paise money, plaintext demo credentials, `Institution.first()`, global Campus ID and payment-reference uniqueness, unscoped list endpoints, read-modify-write balance (no lock), non-idempotent recharge, 6 passing payment tests. |
| Operating Model v0.2 | Source of Campus Units, Ledger authority, PIN, fulfillment states and the MG open-decision register. It is **not present in the repository snapshot**. |

Governance findings (documents left untouched): `ADR-0000-template.md` is byte-identical to ADR-0001 (it is not a template); the ADR index lists no ADR except the template; CI workflows do not run backend tests.

## 2. Mapping
| MVP | Governed location |
|---|---|
| `app/models.py` | per-module `models.py` under `backend/modules/*` |
| `app/modules/*.py` routers+logic | module `router.py` (HTTP only) + `service.py` (published interface) |
| `app/security.py` (users in code) | `core/security.py` + DB credentials in `modules/auth` |
| `app/database.py`, `main.py` | `core/database.py`, `app/main.py` (composition root) |
| `admin.py` dashboard | `modules/reports` |
| `WalletTransaction` as ledger | `modules/ledger` (authoritative) + wallet movement record |
| `frontend/*.html` | `frontend/demo/` (plain HTML/JS; Next.js admin placeholder untouched) |
| MVP test file | `backend/tests/test_legacy_manual_payment.py` (+ new suites) |

## 3. Module dependency matrix (enforced by tests)
institutions: — · audit: — · ledger: — · users: audit · devices: audit · auth: users, institutions, audit · wallets: users, ledger, audit · merchants: users, devices, audit · payments: auth, institutions, merchants, users, wallets, audit · reports: audit, devices, ledger, merchants, payments, users, wallets.

## 4. State machines (separate)
Order: CREATED → PAID | CANCELLED (unpaid only). Payment: INITIATED → COMPLETED | FAILED. Receipt: (none) → ISSUED (after commit; retryable). Fulfillment: PAID → PREPARING → READY → COLLECTED.

## 5. Open decisions (not decided by P1)
MG-01 PIN lockout/reset/unlock (mechanism only, configurable, no default) · MG-02 final identity mechanism (abstraction; only `CAMPUS_ID`) · MG-03 recharge (demo funding only, flagged `origin=DEMO`) · MG-04/05 adjustments · MG-06 refunds · MG-07/14 settlement · MG-08 menu authority (configurable roles) · MG-09 price change on carts/orders (orders keep snapshots) · MG-10/11 printer/reprint · MG-12 food-counter verification · MG-13 network failure (idempotent retry only) · MG-15 paid-order cancellation (refused) · MG-16 ledger/wallet discrepancy (detect + fail closed) · MG-W01–W04 wallet statuses (MVP ACTIVE/INACTIVE/SUSPENDED carried, no transitions API).

## 6. Run
```
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
export DATABASE_URL=sqlite:///./campuspay_demo.db SECRET_KEY=change-me-demo-signing-key CAMPUSPAY_DEMO_FUNDING=true
export CAMPUSPAY_DEMO_PASSWORD='CampusDemo#2026' CAMPUSPAY_DEMO_PIN=4826
.venv/bin/python -m app.seed
.venv/bin/uvicorn app.main:app --port 8000
```
Open http://localhost:8000 (institution code `EGS-ENGG`; users `admin`, `canteen`, `stationery`). Existing MVP database: `alembic stamp 0001_mvp_baseline && alembic upgrade head`.
Tests: `cd backend && CAMPUSPAY_TEST_POSTGRES_URL=postgresql+psycopg2://USER:PASS@HOST:5432/postgres python -m pytest tests -q` (PostgreSQL tests are skipped when the variable is unset).
