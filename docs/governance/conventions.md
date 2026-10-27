# CampusPay Engineering Conventions

**Document ID:** CP-CONV-001  
**Version:** 1.0  
**Status:** Approved  
**Owner:** CampusPay Engineering Team  
**Project:** CampusPay – Campus Financial Operating System  
**Last Updated:** 27 July 2026

---

# Purpose

This document establishes the engineering standards and development conventions used throughout the CampusPay project.

Its objectives are to:

- Promote consistency across the codebase.
- Improve maintainability.
- Reduce ambiguity.
- Simplify onboarding for new contributors.
- Establish a common engineering language.
- Prevent unnecessary architectural complexity.

All contributors are expected to follow these conventions unless an approved Architecture Decision Record (ADR) states otherwise.

---

# Engineering Principles

## Simplicity First

Prefer the simplest solution that satisfies the current validated requirements.

Avoid introducing complexity unless there is measurable evidence that it is required.

---

## Evidence Before Complexity

Architectural complexity must be justified by measurable operational or business needs.

Do not optimise for hypothetical future requirements.

---

## Platform Before Features

Every feature should strengthen the CampusPay platform rather than solving only one institution's requirements.

---

## Configuration Over Customisation

Institution-specific behaviour should be implemented through configuration wherever practical.

Avoid institution-specific source code.

---

## One Source of Truth

Every concept should have one authoritative location.

Examples:

- Business terms → terminology.md
- Architecture → ADRs
- Product requirements → PRD
- Software behaviour → SRS

---

## Readability Over Cleverness

Code should prioritise clarity over clever implementations.

A straightforward solution is preferred over an overly sophisticated one.

---

## Consistency Over Preference

Project conventions take precedence over individual coding preferences.

---

# Repository Structure

Every major capability shall exist as an independent module.

Example:

backend/

- auth
- institutions
- students
- faculty
- wallets
- payments
- attendance
- merchants
- notifications
- reports
- devices
- audit

Modules should not expose internal implementation details to other modules.

---

# Naming Conventions

## General Principles

Names should be:

- Clear
- Descriptive
- Consistent
- Singular where appropriate
- Free from unnecessary abbreviations

Avoid:

- temp
- data1
- helper
- util2
- misc

---

## Files

Use:

snake_case

Examples:

attendance_service.py

wallet_repository.py

payment_validator.py

---

## Classes

Use:

PascalCase

Examples:

WalletService

PaymentProcessor

AttendanceManager

---

## Functions

Use:

snake_case

Examples:

create_wallet()

record_attendance()

calculate_balance()

---

## Variables

Use:

snake_case

Examples:

wallet_balance

payment_amount

institution_id

---

## Constants

Use:

UPPER_CASE

Examples:

MAX_RETRY_COUNT

DEFAULT_TIMEOUT

API_VERSION

---

# Database Conventions

## Tables

Use:

snake_case

Plural nouns.

Examples:

institutions

campus_users

wallets

payments

attendance_records

devices

---

## Primary Keys

Every table shall contain:

id

using UUID unless otherwise justified.

---

## Foreign Keys

Format:

entity_id

Examples:

institution_id

wallet_id

merchant_id

---

## Timestamps

Use:

created_at

updated_at

deleted_at (if soft delete is implemented)

---

# API Conventions

CampusPay follows REST principles.

---

## Resources

Use plural nouns.

Examples:

GET /institutions

GET /wallets

POST /payments

GET /attendance

---

## Avoid

/getWallet

/createStudent

/updateBalance

/deleteMerchant

---

## HTTP Methods

GET

Read

POST

Create

PUT

Replace

PATCH

Partial Update

DELETE

Remove

---

## Response Format

Every API should return a consistent response structure.

Example:

{
    "success": true,
    "message": "Wallet created successfully.",
    "data": {}
}

Errors should use the same structure.

---

# Module Boundaries

Modules own:

- Business rules
- Validation
- Domain models
- Internal services

Modules should not:

- Access another module's private implementation.
- Modify another module's data directly.

Communication should occur through defined interfaces.

---

# Documentation Standards

Every document shall include:

- Document ID
- Version
- Status
- Owner
- Revision History

Every major engineering decision should reference related ADRs where appropriate.

---

# Versioning

Use Semantic Versioning.

MAJOR.MINOR.PATCH

Examples:

1.0.0

1.1.0

2.0.0

---

# Git Conventions

## Branch Naming

feature/wallet

feature/payments

feature/attendance

bugfix/login

hotfix/payment-timeout

docs/architecture

---

## Commit Messages

Examples:

feat(wallet): add recharge service

fix(auth): resolve JWT validation issue

docs(adr): add ADR-0003

refactor(payments): simplify settlement logic

---

# Logging Standards

Log meaningful operational events.

Do not log:

- Passwords
- Secrets
- Access Tokens
- Personal financial information

Use appropriate log levels.

DEBUG

INFO

WARNING

ERROR

CRITICAL

---

# Error Handling

Errors should be:

- Meaningful
- Actionable
- Consistent

Avoid exposing internal implementation details to API consumers.

---

# Security Standards

Never:

- Hardcode credentials.
- Store secrets in source code.
- Commit API keys.
- Disable authentication checks.
- Ignore validation failures.

---

# Testing Standards

Every business module should include:

- Unit Tests
- Integration Tests (where applicable)

Critical business logic should not rely solely on manual testing.

---

# Performance Guidelines

Optimise only after measurement.

Avoid premature optimisation.

Maintain readability before micro-optimisation.

---

# Architectural Governance

Every significant architectural decision shall be documented using an Architecture Decision Record (ADR).

If a proposed implementation conflicts with an approved ADR, the ADR must be reviewed before implementation proceeds.

---

# Decision-Making Checklist

Before introducing a new dependency, abstraction, framework, or architectural pattern, ask:

1. Does it solve a real problem?
2. Is there a simpler solution?
3. Does it align with the Vision?
4. Does it align with existing ADRs?
5. Can new developers understand it easily?
6. Will it reduce long-term maintenance effort?
7. Can it be removed if requirements change?

If the answer to multiple questions is "No", reconsider the decision.

---

# Engineering Motto

> **Simple by Default. Extensible by Design. Evidence Before Complexity.**

This principle should guide every architectural, engineering, and implementation decision within CampusPay.

---

# Related Documents

- PROJECT_VISION.md
- ADR-0001 – Adoption of a Multi-Tenant SaaS Architecture
- ADR-0002 – Adoption of a Modular Monolith Architecture
- terminology.md
- PRODUCT_REQUIREMENTS.md
- SRS.md

---

# Revision History

| Version | Date | Description |
|----------|------------|-----------------------------|
| 1.0 | 27 July 2026 | Initial engineering conventions |