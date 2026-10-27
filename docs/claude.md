# CLAUDE.md

# CampusPay AI Engineering Guide

Version: 1.0

---

# Purpose

This document defines the engineering rules that every AI-generated file for the CampusPay project must follow.

It serves as the primary instruction set for AI assistants contributing to this repository.

If any instruction conflicts with another project document, do not make assumptions. Stop and explain the conflict.

---

# Project Objective

CampusPay is a multi-tenant digital campus payment and management platform.

The immediate objective is to deliver a stable MVP prototype.

Priority:

1. Working software
2. Correct architecture
3. Clean code
4. Extensibility
5. Performance optimisation (later)

Never sacrifice correctness for unnecessary optimisation.

---

# Project Documents

Always follow these documents.

1. PROJECT_VISION.md
2. BUSINESS_MODEL.md
3. PRODUCT_REQUIREMENTS.md
4. SRS.md
5. ARCHITECTURE.md
6. DATABASE.md
7. API.md

Do not contradict these documents.

---

# Engineering Philosophy

Follow these principles:

- Simplicity over complexity.
- Readability over cleverness.
- Correctness over speed.
- Modularity over duplication.
- Maintainability over shortcuts.

Avoid over-engineering.

---

# Architecture Rules

Never change the architecture without approval.

Do not:

- rename modules
- merge unrelated modules
- invent new modules
- remove existing modules

Respect separation of concerns.

Business logic belongs inside services.

Routers should only:

- receive requests
- validate requests
- call services
- return responses

Never place business logic inside routers.

---

# Technology Stack

Backend

- Python 3.12
- FastAPI
- SQLAlchemy 2.x
- Alembic
- PostgreSQL

Authentication

- JWT

API

- REST

Data Format

- JSON

---

# Repository Rules

Never:

- rename directories
- move files
- delete files
- reorganise project structure

unless explicitly instructed.

When modifying existing code:

- preserve behaviour
- minimise changes
- avoid breaking other modules

---

# Database Rules

Follow DATABASE.md exactly.

Do not invent:

- tables
- columns
- relationships

Every table should have:

- UUID primary key
- timestamps where appropriate
- foreign key constraints

Maintain referential integrity.

---

# API Rules

Follow API.md.

API endpoints should:

- use REST principles
- use JSON
- validate input
- return meaningful errors
- use correct HTTP status codes

Never invent endpoints that are not required.

---

# Security Rules

Always:

- hash passwords
- validate input
- prevent SQL injection
- protect authenticated endpoints
- never expose secrets
- never hardcode credentials

Use environment variables for configuration.

---

# Code Style

Generate production-quality code.

Prefer:

- small functions
- descriptive names
- clear structure
- reusable components

Avoid:

- duplicated logic
- magic numbers
- deeply nested functions
- unnecessary abstraction

---

# Documentation

Public classes and functions should include concise documentation.

Complex logic should include brief explanatory comments.

Do not write comments that simply restate the code.

---

# Error Handling

Never silently ignore errors.

Raise meaningful exceptions.

Return consistent API responses.

Log unexpected failures.

---

# Testing

Generate testable code.

Separate business logic from infrastructure.

Avoid tightly coupled modules.

---

# AI Behaviour

If requirements are unclear:

Ask questions.

Do not guess.

If architecture must change:

Explain why before generating code.

If a request conflicts with project documents:

Identify the conflict instead of inventing a solution.

---

# Current Development Phase

Current Goal:

Deliver a working MVP prototype.

Prioritise implementation of:

1. Authentication
2. Dashboard
3. Wallet
4. Payments
5. Attendance
6. Basic Administration

Ignore future features unless explicitly requested.

---

# Definition of Done

A feature is complete only if:

- code compiles
- follows architecture
- follows database design
- follows API design
- handles errors
- is readable
- does not break existing functionality

---

# Golden Rule

When in doubt:

Follow the project documentation.

If the documentation does not answer the question,

ask before making architectural decisions.