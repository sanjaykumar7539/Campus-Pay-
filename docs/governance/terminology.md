# CampusPay Terminology

**Document ID:** CP-TERM-001  
**Version:** 1.0  
**Status:** Approved  
**Owner:** CampusPay Engineering Team  
**Project:** CampusPay – Campus Financial Operating System  
**Last Updated:** 27 July 2026

---

# Purpose

This document establishes the official business and technical vocabulary used throughout the CampusPay project.

Its objectives are to:

- Ensure consistent terminology across all documentation.
- Eliminate ambiguity in business and technical discussions.
- Standardise naming used in requirements, architecture, APIs, databases, and user interfaces.
- Provide a single authoritative reference for project terminology.

All future documentation shall use the definitions contained within this document.

---

# Scope

This document applies to:

- Product documentation
- Architecture documentation
- Software Requirements Specification (SRS)
- Product Requirements Document (PRD)
- Database design
- API design
- Source code
- User Interface
- Administrative documentation

---

# Naming Principles

The following principles govern terminology throughout CampusPay.

- Use business terminology before technical terminology.
- Prefer clear and descriptive names.
- Avoid abbreviations unless widely recognised.
- One concept shall have one official name.
- Different concepts shall not share the same name.
- Terminology shall remain stable unless formally revised.

---

# Business Terminology

## Institution

A legally recognised educational organisation using CampusPay.

Examples include:

- College
- University
- Polytechnic
- School
- Training Institute

Institution is the official business term used throughout CampusPay.

---

## Tenant

A logical isolation boundary representing exactly one Institution within the multi-tenant platform.

Tenant is a technical implementation concept.

Institution is the corresponding business concept.

---

## Campus User

Any authenticated individual authorised to use CampusPay.

Examples include:

- Student
- Faculty Member
- Administrative Staff
- Merchant
- System Administrator

Campus User is the collective term used throughout the platform.

---

## Student

A Campus User enrolled in an Institution.

Students may access wallet, payments, attendance, and other authorised services.

---

## Faculty Member

A Campus User responsible for teaching or academic activities.

---

## Administrative Staff

A Campus User responsible for operational or administrative activities.

---

## Merchant

An authorised business or service provider permitted to accept payments through CampusPay.

---

## Wallet

A digital financial account associated with a Campus User.

The wallet stores balances and records financial transactions.

---

## Payment

A financial transaction initiated through CampusPay.

Payments may occur between Campus Users and authorised Merchants or Institutions.

---

## Transaction

A permanent financial record representing movement of value.

Every payment generates one or more transactions.

---

## Attendance

A recorded event indicating the presence or participation of a Campus User within an authorised activity.

---

## Device

A registered hardware endpoint authorised to interact with CampusPay.

Examples include payment terminals, attendance devices, kiosks, or mobile devices.

---

# Identity & Access Terminology

## Authentication

The process of verifying the identity of a Campus User or Device.

---

## Authorisation

The process of determining which actions an authenticated entity is permitted to perform.

---

## Role

A named collection of permissions assigned to a Campus User.

Examples:

- Student
- Faculty
- Merchant
- Administrator

---

## Permission

An individual capability granted to a Campus User through one or more Roles.

---

# Financial Terminology

## Balance

The current amount of funds available within a Wallet.

---

## Settlement

The process of reconciling completed financial transactions.

---

## Refund

The return of previously transferred funds.

---

## Recharge

The process of adding funds to a Wallet.

---

## Ledger

The complete financial record of transactions maintained by CampusPay.

---

# Technical Terminology

## Module

A self-contained business capability within the Modular Monolith architecture.

Examples:

- Wallets
- Payments
- Attendance
- Notifications

---

## Service

A software component responsible for executing business operations within a Module.

---

## API

Application Programming Interface used for communication between software systems.

---

## Endpoint

A specific API resource that performs an operation or provides data.

---

## Event

A significant occurrence within the platform that may trigger additional processing.

Examples include:

- Payment Completed
- Attendance Recorded
- Wallet Recharged

---

## Audit Log

A permanent record of significant operational events for accountability, security, and compliance.

---

# Reserved Terminology

The following terms are considered canonical throughout CampusPay.

| Preferred Term | Avoid |
|----------------|-------|
| Institution | College, School, Organisation |
| Campus User | User, Member |
| Wallet | Account, Balance Account |
| Merchant | Vendor, Shop |
| Payment | Purchase |
| Transaction | Entry |
| Attendance | Presence |
| Device | Terminal (unless referring specifically to a payment terminal) |
| Module | Component (when referring to business modules) |

---

# Future Terminology

The following concepts are reserved for future releases.

- Parent
- Guardian
- Alumni
- Visitor
- Marketplace
- Smart Campus Service
- Digital Certificate

Definitions will be added when these capabilities become part of the product.

---

# Governance

Changes to this document should be made only when:

- New business concepts are introduced.
- Existing terminology becomes ambiguous.
- Product scope changes require additional definitions.

Changes should be reviewed before adoption across the project.

---

# Related Documents

- PROJECT_VISION.md
- ADR-0001 – Adoption of a Multi-Tenant SaaS Architecture
- ADR-0002 – Adoption of a Modular Monolith Architecture
- PRODUCT_REQUIREMENTS.md
- SRS.md

---

# Revision History

| Version | Date | Description |
|----------|------------|-----------------------------|
| 1.0 | 27 July 2026 | Initial terminology document |