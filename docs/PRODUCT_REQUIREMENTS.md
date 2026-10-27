# CampusPay Product Requirements Document (PRD)

**Document ID:** CP-PRD-001  
**Version:** 1.0  
**Status:** Approved  
**Owner:** CampusPay Engineering Team  
**Project:** CampusPay – Campus Financial Operating System  
**Last Updated:** 27 July 2026

---

# Executive Summary

CampusPay is a commercial, multi-tenant Campus Financial Operating System (Campus Financial OS) designed to unify financial, identity, attendance, merchant, and administrative services within educational institutions.

The objective of CampusPay is to replace fragmented campus systems with a single configurable platform that improves operational efficiency, financial transparency, and user experience.

This document defines the business capabilities, product scope, and functional modules of CampusPay.

It intentionally avoids implementation details, which are documented separately within the Software Requirements Specification (SRS), Architecture, Database, API, Security, and Deployment documents.

---

# Purpose

The purpose of this document is to define:

- Product capabilities
- Functional scope
- Business objectives
- User groups
- Product modules
- Business rules
- Product boundaries

This document serves as the primary reference for product planning and software development.

---

# Product Goals

CampusPay aims to:

- Digitise campus financial operations.
- Reduce dependence on cash transactions.
- Provide secure digital identity.
- Improve operational efficiency.
- Simplify attendance management.
- Improve reporting and analytics.
- Reduce administrative workload.
- Support multiple educational institutions through a configurable platform.
- Provide a scalable foundation for future expansion.

---

# Target Customers

CampusPay is intended for:

- Engineering Colleges
- Universities
- Arts & Science Colleges
- Polytechnics
- Schools
- Training Institutes
- Educational Groups

---

# Target Users

Primary users include:

- Students
- Faculty Members
- Administrative Staff
- Finance Department
- Campus Merchants
- System Administrators

Future users include:

- Parents
- Guardians
- Alumni
- Visitors

---

# Stakeholders

Internal stakeholders:

- Product Owners
- Engineering Team
- QA Team
- Support Team

External stakeholders:

- Educational Institutions
- Institution Management
- Students
- Faculty
- Merchants
- Regulatory Bodies

---

# Product Scope

The initial release (MVP) includes:

- Authentication
- Institution Management
- Campus User Management
- Wallet Management
- Payment Management
- Merchant Management
- Attendance Management
- Notification Management
- Reporting
- Device Management
- Administrative Dashboard

---

# Functional Modules

---

## Authentication

**Classification:** Core (MVP)

### Purpose

Provide secure access to CampusPay.

### Primary Users

- All Campus Users

### Business Capabilities

- User Login
- User Logout
- Password Management
- Session Management
- Multi-role Authentication

---

## Institution Management

**Classification:** Core (MVP)

### Purpose

Manage educational institutions operating on the CampusPay platform.

### Primary Users

- Platform Administrators

### Business Capabilities

- Institution Registration
- Institution Configuration
- Institution Status Management
- Institution Administration

---

## Campus User Management

**Classification:** Core (MVP)

### Purpose

Manage users belonging to an Institution.

### Primary Users

- Administrators

### Business Capabilities

- User Registration
- User Profile Management
- Role Assignment
- User Search
- User Status Management

---

## Wallet Management

**Classification:** Core (MVP)

### Purpose

Provide digital financial accounts for Campus Users.

### Primary Users

- Students
- Finance Department

### Business Capabilities

- Wallet Creation
- View Balance
- Recharge Wallet
- Transaction History
- Refund Processing

---

## Payment Management

**Classification:** Core (MVP)

### Purpose

Manage financial transactions across the platform.

### Primary Users

- Students
- Merchants
- Finance Department

### Business Capabilities

- Merchant Payments
- Wallet Payments
- Payment Validation
- Payment History
- Refund Processing

---

## Merchant Management

**Classification:** Core (MVP)

### Purpose

Manage merchants authorised to operate within an Institution.

### Primary Users

- Administrators

### Business Capabilities

- Merchant Registration
- Merchant Approval
- Merchant Profile Management
- Merchant Status Management

---

## Attendance Management

**Classification:** Core (MVP)

### Purpose

Digitally record attendance events.

### Primary Users

- Faculty
- Students

### Business Capabilities

- Attendance Recording
- Attendance History
- Attendance Reports
- Attendance Corrections

---

## Notification Management

**Classification:** Core (MVP)

### Purpose

Deliver important information to Campus Users.

### Primary Users

- All Campus Users

### Business Capabilities

- Payment Notifications
- Attendance Notifications
- Administrative Notifications
- System Alerts

---

## Reporting

**Classification:** Core (MVP)

### Purpose

Provide operational and financial insights.

### Primary Users

- Administrators
- Finance Department

### Business Capabilities

- Financial Reports
- Attendance Reports
- Merchant Reports
- User Reports
- Operational Dashboards

---

## Device Management

**Classification:** Core (MVP)

### Purpose

Manage authorised devices connected to CampusPay.

### Primary Users

- System Administrators

### Business Capabilities

- Device Registration
- Device Configuration
- Device Status Monitoring
- Device Lifecycle Management

---

# Non-Functional Requirements

The product shall prioritise:

- Security
- Reliability
- Scalability
- Maintainability
- Usability
- Performance
- Auditability
- Configurability

Detailed non-functional specifications are documented within the SRS.

---

# Out of Scope

The following capabilities are excluded from the initial release:

- Library Management
- Hostel Management
- Payroll
- Transportation
- Learning Management System (LMS)
- Cryptocurrency Payments
- Student Loans

These may be considered in future releases.

---

# Product Success Metrics

Success will be measured through:

- Institution Adoption
- Active Users
- Digital Payment Adoption
- Attendance Automation
- Transaction Success Rate
- Merchant Participation
- User Satisfaction
- Reduction in Manual Administration

---

# Release Strategy

## Phase 1

Platform Development

---

## Phase 2

Pilot Deployment

E.G.S. Pillay Engineering College

---

## Phase 3

Product Refinement

---

## Phase 4

Commercial Rollout

---

# Assumptions

The product assumes:

- Institutions support digital transformation.
- Users possess authenticated identities.
- Institutions can adopt configurable workflows.
- Regulatory requirements permit digital financial services.

---

# Constraints

CampusPay shall:

- Support multi-tenant operation.
- Preserve tenant isolation.
- Follow the approved ADRs.
- Maintain modular architecture.
- Remain configurable across institutions.

---

# Traceability

This document derives from:

- PROJECT_VISION.md
- BUSINESS_MODEL.md
- ADR-0001
- ADR-0002
- governance/terminology.md
- governance/conventions.md

Subsequent documents including the SRS, Architecture, Database, and API specifications shall trace their requirements back to this document.

---

# Related Documents

- PROJECT_VISION.md
- BUSINESS_MODEL.md
- SRS.md
- ARCHITECTURE.md
- DATABASE.md
- API.md

---

# Revision History

| Version | Date | Description |
|----------|------------|----------------------------|
| 1.0 | 27 July 2026 | Initial Product Requirements Document |