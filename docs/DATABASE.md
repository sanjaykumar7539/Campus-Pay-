# Database Design Document

**Project:** CampusPay

**Version:** 1.0

**Status:** Draft

---

# 1. Purpose

This document defines the logical database design for the CampusPay platform. It describes the core business entities, their relationships, and the principles governing data storage.

The objective is to provide a scalable, maintainable, and secure database foundation that supports the functional requirements defined in the Software Requirements Specification (SRS) and the system architecture documented in ARCHITECTURE.md.

This document focuses on the logical data model rather than implementation-specific SQL scripts.

---

# 2. Database Technology

The MVP uses PostgreSQL as the primary relational database.

PostgreSQL was selected because it provides:

- ACID-compliant transactions
- Strong referential integrity
- Excellent indexing support
- JSON/JSONB support
- High reliability
- Mature ecosystem
- Open-source licensing

Future enhancements may introduce Redis for caching and object storage for documents or media files.

---

# 3. Database Design Principles

CampusPay follows these database design principles:

- Relational database design
- UUID-based primary keys
- Foreign key relationships
- Normalized schema
- Minimal data redundancy
- Soft deletion where appropriate
- Auditability of critical operations
- Tenant-aware design
- Secure storage of sensitive information

---

# 4. High-Level Data Architecture

The database is organised around business domains.

Each business domain owns its entities while maintaining relationships with shared entities such as Institution and Campus User.

Major domains include:

- Institution Management
- Campus User Management
- Wallet
- Payments
- Merchant
- Attendance
- Notifications
- Reporting

---

# 5. Core Business Domains

## 5.1 Institution Domain

Responsible for storing institution-level information.

Primary Entity:

- Institution

---

## 5.2 Campus User Domain

Responsible for managing all users.

Primary Entities:

- CampusUser
- UserRole

---

## 5.3 Wallet Domain

Responsible for digital wallet management.

Primary Entities:

- Wallet
- WalletTransaction

---

## 5.4 Payment Domain

Responsible for payment processing.

Primary Entities:

- Payment
- PaymentMethod

---

## 5.5 Merchant Domain

Responsible for merchant management.

Primary Entity:

- Merchant

---

## 5.6 Attendance Domain

Responsible for attendance records.

Primary Entity:

- AttendanceRecord

---

## 5.7 Notification Domain

Responsible for system notifications.

Primary Entity:

- Notification

---

# 6. Entity Overview

| Entity | Purpose |
|---------|---------|
| Institution | Stores institution information |
| CampusUser | Stores students, faculty, staff and administrators |
| UserRole | Defines user permissions |
| Wallet | Digital wallet for each user |
| WalletTransaction | Records wallet credits and debits |
| Merchant | Campus merchants |
| Payment | Payment transactions |
| PaymentMethod | Payment source information |
| AttendanceRecord | Attendance logs |
| Notification | User notifications |

---

# 7. Entity Relationships

The logical relationships are as follows:

Institution

- has many Campus Users
- has many Merchants

Campus User

- owns one Wallet
- has many Attendance Records
- receives many Notifications
- performs many Payments

Wallet

- has many Wallet Transactions

Merchant

- receives many Payments

Payment

- belongs to one Wallet
- belongs to one Merchant
- belongs to one Campus User

---

# 8. Data Integrity Rules

The following integrity rules apply:

- Every Campus User belongs to exactly one Institution.
- Every Wallet belongs to one Campus User.
- Every Payment must reference a valid Wallet.
- Every Payment must reference a valid Merchant.
- Attendance records cannot exist without a valid Campus User.
- Notifications must reference an existing Campus User.
- Foreign key constraints shall enforce referential integrity.

---

# 9. Security Considerations

The database shall implement the following security controls:

- Passwords stored using secure hashing algorithms.
- Sensitive information encrypted where applicable.
- Role-based database access.
- Audit logging for financial transactions.
- Protection against SQL injection through parameterized queries.
- Regular database backups.

---

# 10. Scalability Considerations

The database design supports future growth through:

- UUID primary keys
- Indexed foreign keys
- Tenant-aware architecture
- Modular business domains
- Horizontal application scaling
- Read replica compatibility
- Future partitioning of transaction tables

---

# 11. Future Enhancements

Future versions may introduce:

- Loyalty and reward points
- Hostel management
- Library transactions
- Smart cafeteria ordering
- Transport payments
- Scholarship management
- Advanced financial analytics
- Data warehouse integration

---

# 12. Revision History

| Version | Date | Description |
|----------|------|-------------|
| 1.0 | YYYY-MM-DD | Initial database design document |