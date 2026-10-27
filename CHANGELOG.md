# Changelog

All notable changes to the CampusPay project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased] - P1 campus commerce (feature/p1-campus-commerce)

### Added
- Backend under `backend/` (FastAPI modular monolith): Institution Ledger, Wallet, Payments, Merchant catalog/orders/fulfillment, Authentication (4-digit payment PIN), kiosk Devices, Reports, Audit.
- Alembic migrations 0001 (MVP baseline) and 0002 (P1; data-preserving MVP upgrade).
- Demo frontend (`frontend/demo/`), seed script, tests, ADR-0004 to ADR-0008 (Proposed).

### Changed
- Tenant isolation: no `Institution.first()`; Campus IDs, usernames, payment references unique per institution.
- Money is integer Campus Units (₹1 = 1 CU); the Institution Ledger is authoritative, Wallet is a representation.

### Deprecated
- MVP manual amount-driven payment (flag-gated, PIN required).

## [0.1.0] - 2026-07-27

### Added
- Initial repository scaffolding and monorepo structure.
- Comprehensive architectural and planning documentation placeholders.
- Setup and infrastructure outlines.
- GitHub issue and pull request templates.
- Empty baseline CI/CD workflow configurations.
