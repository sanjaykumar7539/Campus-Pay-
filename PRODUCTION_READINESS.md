# Production readiness — release boundary

This is an implemented and locally tested software upgrade. It is **not ready to accept live money solely by extracting this zip**. No real scanner, thermal printer, public deployment, production database, institution policy, or payment provider was supplied. The following are concrete acceptance requirements, not claims that they have been completed.

## Implemented in this release

Dedicated persistent kiosk sessions; server-checked administrator logout; restricted browser navigation within the app; merchant and tenant isolation; role-scoped canteen onboarding; separate merchant open/close state; fingerprint enrollment and revocation; two distinct capture IDs/nonces for the same finger; 90-second order-bound authorization; server-priced orders; wallet/ledger atomicity; stock revalidation; one debit on retries; immutable receipt balance snapshot; reprint recovery; security headers; readiness checks; audited enrollment/device changes; disabled PIN fallback; dependency upgrades.

## Must complete before live launch

| Area | Required work |
| --- | --- |
| Scanner | Select hardware, implement its supported SDK adapter and 1:N matcher, protect template storage, demonstrate finger-lift handling, assess false-match/liveness behavior, and run real hardware acceptance tests. |
| Financial operations | Implement approved payment acknowledgement → authorized wallet recharge, refunds, disputes, settlement and reconciliation procedures. Demo funding is not an acceptable live recharge workflow. Amounts currently support whole rupees only. |
| Database | Run migrations and the full suite against a disposable PostgreSQL staging instance, including simultaneous kiosk payments and inventory races; perform load testing sized to actual stations. SQLite results do not establish PostgreSQL safety. |
| HTTPS and access | Supply real secrets, trusted hostnames and TLS termination. Segment public kiosk/scanner/admin traffic. Restrict scanner endpoints to managed devices. Review privileged access/MFA requirements. |
| Rate limiting | Add shared gateway limits and login abuse controls for multi-worker/multi-host deployments. The application limiter is per-process and insufficient on its own for a distributed deployment. Validate trusted proxy/IP configuration. |
| Backup and recovery | Encrypted backups, restore drills, database point-in-time recovery, operational ownership, key rotation and incident handling. Test receipt reissue after process interruption. |
| Kiosk and printer | Configure OS Assigned Access, permitted URLs/shortcuts, scanner service and thermal printer. Browser logout controls do not lock down Windows. Browser afterprint does not prove paper delivery. |
| Enrollment support | Define informed consent, access/retention/deletion controls, duplicate enrollment handling, supervised re-enrollment and a non-PIN support route for students unable to use biometrics. |
| Monitoring | Alert on readiness failure, scanner offline, unusual matching failures, payment failures, ledger mismatch and printer support incidents. Do not log credentials or biometric data. |
| Scale and administration | Large-campus student pagination/search, bulk import, notification policy, approval workflows and financial exports require product-specific follow-up. Existing admin reads still load all students. |

## Deployment configuration

Use .env.production.example as a template and supply secrets through your deployment platform. Startup refuses production SQLite, demo funding, legacy payments, PIN authorization, weak/missing signing secrets, low bcrypt cost, or wildcard/missing allowed hosts. Application code still requires an external HTTPS gateway; the headers alone do not establish TLS.

Run migrations as a controlled release step with a database role authorized for DDL. Use a separate least-privilege application role at runtime. Start Uvicorn behind your managed proxy; do not expose local development directly. Monitor GET /api/v1/ready (503 when database/schema is unavailable). GET /api/v1/health is descriptive, not proof of database readiness.

Use the supplied CI example with a disposable PostgreSQL service. Review dependency updates and run pip-audit again at deployment time. The audit is a snapshot of known advisories, not a security certification.

An optional non-root container recipe is in infrastructure/docker/Dockerfile. Build from the repository root using `docker build -f infrastructure/docker/Dockerfile -t campuspay .`. Supply environment/secrets at runtime, use an external PostgreSQL database and a TLS proxy, and run `python -m alembic upgrade head` as a separate release job. The Docker recipe and CI workflow were supplied for staging use; they were not executed on this Windows verification machine.

## Security boundaries and known limits

- Scanner assertions are trusted native-device claims. Possession of its key is a strong capability; compromise of the scanner service defeats matching assertions.
- Two same-finger scans satisfy the requested interaction; they do not constitute independent MFA.
- Staff sessions continue to use the existing short-lived bearer-token design in browser session storage. Privileged SSO/MFA and a stricter CSP without legacy inline staff handlers are further hardening work.
- Kiosk activation lasts seven days, can be replaced or invalidated, and requires staff recovery after expiry. No administrator credential is stored in the kiosk cookie.
- Receipt timeout and finish clear browser state and close retrieval through that kiosk's finished checkout. Staff may still retrieve the retained accounting receipt with authorized access.
- Existing historical PIN tables/tests are retained for migration compatibility. Production startup prevents selecting the legacy PIN payment mode.
- No database or real secrets are included in the distributed source archive. Keep the original database and follow a staged migration; do not start an empty database expecting existing balances to appear.
