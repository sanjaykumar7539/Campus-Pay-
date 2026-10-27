# Upgrade file inventory

Original source: CampusPay.zip supplied by the user. Original archive preserved.

## Modified files

- .env.example
- .github/workflows/tests.yml
- backend/app/admin_students_router.py
- backend/app/main.py
- backend/app/models_registry.py
- backend/app/seed.py
- backend/core/rate_limit.py
- backend/core/security.py
- backend/migrations/env.py
- backend/modules/auth/service.py
- backend/modules/devices/router.py
- backend/modules/devices/service.py
- backend/modules/merchants/models.py
- backend/modules/merchants/router.py
- backend/modules/merchants/service.py
- backend/modules/payments/receipts.py
- backend/modules/payments/service.py
- backend/requirements.txt
- backend/tests/conftest.py
- backend/tests/test_financial_invariants.py
- backend/tests/test_migrations.py
- frontend/demo/account.html
- frontend/demo/account.js
- frontend/demo/admin.html
- frontend/demo/admin.js
- frontend/demo/app.js
- frontend/demo/index.html
- frontend/demo/kiosk.html
- frontend/demo/login.html
- frontend/demo/login.js
- frontend/demo/merchant.html
- frontend/demo/merchant.js
- frontend/demo/shell.js
- frontend/demo/student-preview.html
- frontend/demo/student.html
- frontend/demo/student.js
- main.py
- README.md
- START_HERE_WINDOWS.md

## Added files

- .dockerignore
- .env.production.example
- backend/app/bootstrap_admin.py
- backend/app/demo_setup.py
- backend/app/hardening.py
- backend/app/kiosk_router.py
- backend/app/kiosk_service.py
- backend/app/management_router.py
- backend/core/demo_defaults.py
- backend/migrations/versions/0005_fingerprint_kiosk.py
- backend/modules/auth/kiosk_models.py
- backend/requirements-dev.txt
- backend/tests/test_demo_defaults.py
- backend/tests/test_fingerprint_kiosk.py
- backend/tests/test_production_guards.py
- CHANGELOG_UPGRADE.md
- DEMO_LOGINS.md
- docs/KIOSK_WINDOWS.md
- docs/MENU_IMAGE_CREDITS.md
- docs/verification/admin-dashboard.png
- docs/verification/dependency-audit.json
- docs/verification/kiosk-menu.png
- docs/verification/merchant-dashboard.png
- docs/verification/migration-validation.json
- docs/verification/synthetic-receipt.png
- frontend/demo/assets/menu-fallback.svg
- frontend/demo/menu-images.js
- frontend/demo/portal.css
- frontend/demo/station.css
- frontend/demo/station.js
- frontend/tests/station.test.cjs
- infrastructure/docker/Dockerfile
- PRODUCTION_READINESS.md
- scanner/adapter_contract.py
- scanner/agent.py
- scanner/INTEGRATION.md
- START_DEMO.bat
- start_demo.py
- VALIDATION.md

## Distribution exclusions

The original demo database, bytecode/cache directories, environment secrets and temporary test runtime are not shipped. Preserve the original database and follow START_HERE_WINDOWS.md to migrate it. Historical scaffold directories and documents are retained.
