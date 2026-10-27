# Validation report

Executed locally on Windows, Python 3.12, against the upgraded source and synthetic test data. Date: 2026-10-04.

| Check | Result |
| --- | --- |
| Full backend suite | **166 passed, 10 skipped**, 16 warnings; 37.62 seconds. |
| PostgreSQL-specific tests | **Not run**: no disposable PostgreSQL connection was available. Ten parameterized/database checks were skipped. |
| Kiosk JavaScript state regressions | **2 passed**: idle initial-setup screen; unresolved payment plus expired session remains blocked from starting another order. |
| Python compilation | Passed for backend and scanner source. |
| JavaScript syntax | All frontend/demo scripts passed Node syntax checks; station script rechecked after its final state fix. |
| Dependency audit | **No known vulnerabilities found** in the installed verification environment after dependency updates and JWT replacement. Full snapshot: docs/verification/dependency-audit.json. |
| Supplied database migration | Applied revision 0005 to a copy of the supplied SQLite database. Wallet count/total and payment, ledger, receipt counts unchanged. SQLite integrity and foreign-key checks passed. Original archive unchanged. |

## Security/financial checks covered by automated tests

- Two distinct scans of the same enrolled finger required before debit.
- Different-finger second capture, reused capture ID, stale/expired authorization, missing scanner authentication and offline scanner are rejected.
- Revoking an enrollment invalidates a ready authorization.
- Insufficient balance and stock removal after scans produce no financial mutation.
- Concurrent payment requests with the same authorization produce one debit.
- Receipt carries the balance snapshot and collection/support warning.
- Finished kiosk checkout cannot reopen its receipt through the kiosk payment endpoint.
- Cross-tenant station registration/enrollment is rejected.
- Shared kiosk session cannot authenticate to administrator APIs.
- Wrong password and merchant password cannot unlock the kiosk; the institution administrator can.
- Personal Student ID login/PIN fallback disabled in fingerprint mode.
- Production refuses SQLite, placeholder secrets, PIN mode, demo credits, weak bcrypt cost and wildcard hosts.
- Existing financial invariants, migrations, account settings, permissions and architectural boundaries remain covered by the retained suite.

## Browser verification

Used an isolated local server and disposable synthetic database with agent-browser. Verified:

1. Staff login and administrator dashboard rendering; no browser errors reported.
2. Student registration without PIN; student/fingerprint enrollment controls render.
3. Administrator activates a dedicated kiosk session and sees the menu.
4. Offline scanner prevents checkout; adding items updates the cart.
5. Two-scan checkout through a **test-only synthetic native scanner fixture** displays a paid receipt with the expected remaining balance and warning.
6. Receipt timeout returns to the menu. Clicking Print receipt & finish returns to the menu and clears the cart.
7. Wrong administrator password is rejected; correct password unlocks and logs out the kiosk.
8. Merchant dashboard, canteen availability, menu-entry and inventory controls render without reported browser errors.

Screenshots in docs/verification contain synthetic records only. The scanner fixture lived outside the release source and is not shipped; API tests contain explicitly test-scoped scanner assertions.

The final additional browser interaction to toggle merchant availability was not executed because automatic approval review hit an account usage limit. Backend availability and authorization tests passed. No approval bypass was used. Two later kiosk state fixes were checked by JavaScript syntax and state regression tests, not by another full browser run.

## Not verified / not supplied

Actual biometric enrollment/matching, finger-lift detection, scanner SDK, liveness/false-match properties, physical printer output, silent printing, OS Assigned Access, PostgreSQL execution, production load/soak testing, deployment, Docker build, CI execution, financial recharge/refund/settlement and operational acceptance remain outstanding. Printing was checked as a browser action/reset, not as physical paper delivery.

Passing these tests is not a claim of a completed production rollout. See PRODUCTION_READINESS.md and scanner/INTEGRATION.md.

## Default-login update validation

The user subsequently requested default credentials for local checking. A separate local launcher and idempotent demo provisioning were added. The account/settings/migration/architecture subset completed with **34 passed**. New tests verify all four staff accounts, stable kiosk activation, changing the admin username/password, preservation of those changes and wallet balances across repeated setup, no student PIN provisioning, and rejection of demo setup/passwords in production. The Python launcher and provisioning module passed compilation. START_DEMO.bat itself was not run in this environment; the provisioning and login flow were exercised by the API tests. Earlier browser screenshots predate this default-account update.
