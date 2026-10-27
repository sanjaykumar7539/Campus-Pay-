# ADR-0001: Adoption of a Multi-Tenant SaaS Architecture

**ADR ID:** ADR-0001  
**Title:** Adoption of a Multi-Tenant SaaS Architecture  
**Status:** Accepted  
**Date:** 27 July 2026  
**Decision Makers:** CampusPay Engineering Team

---

# Context

CampusPay is being developed as a modern Campus Financial Operating System intended to digitise financial transactions, digital identity, attendance, merchant services, and administrative operations within educational institutions.

The first real-world deployment of CampusPay will be conducted at **E.G.S. Pillay Engineering College**. While this institution serves as the pilot environment for validation and refinement, the long-term objective is to commercialise CampusPay as a reusable software platform for multiple colleges, universities, and educational organisations.

A key architectural decision must therefore be made before system design begins:

Should CampusPay be designed as a single-institution application or as a multi-tenant Software-as-a-Service (SaaS) platform?

This decision affects nearly every aspect of the system, including:

- Data architecture
- Authentication and authorisation
- User management
- Configuration
- Deployment
- Security
- Scalability
- Future commercial viability

---

# Decision

CampusPay **will adopt a multi-tenant SaaS architecture from the beginning of the project.**

Although the initial production deployment will occur at **E.G.S. Pillay Engineering College**, the platform will be engineered as a configurable product capable of serving multiple independent educational institutions without requiring changes to the application source code.

Each institution (tenant) will operate within its own logically isolated environment while sharing the same application platform.

Institution-specific behaviour shall be achieved through configuration rather than code customisation wherever practical.

---

# Rationale

This decision was made for the following reasons.

## 1. Commercial Scalability

CampusPay is intended to become a commercial software product rather than a one-off institutional solution.

A multi-tenant architecture enables onboarding of new institutions without maintaining separate codebases.

---

## 2. Maintainability

Maintaining a single application platform significantly reduces development, testing, deployment, and maintenance effort.

Bug fixes and feature improvements can benefit all tenants simultaneously.

---

## 3. Consistency

All institutions will operate using the same core business rules while allowing institution-specific configuration where required.

This promotes consistency, simplifies support, and improves software quality.

---

## 4. Future Growth

The chosen architecture supports expansion from:

- Single College
- Multiple Colleges
- Universities
- Educational Groups
- International Deployments

without fundamental architectural redesign.

---

## 5. Cost Efficiency

A shared platform reduces infrastructure duplication and operational overhead while enabling efficient resource utilisation.

---

# Alternatives Considered

## Alternative 1 — Single Institution Architecture

Develop CampusPay exclusively for one educational institution.

### Advantages

- Faster initial implementation
- Lower initial architectural complexity

### Disadvantages

- Poor scalability
- Difficult commercialisation
- Code duplication for future customers
- Higher long-term maintenance cost

**Decision:** Rejected

---

## Alternative 2 — Separate Codebase Per Institution

Maintain independent deployments and source code for every institution.

### Advantages

- High degree of institution-specific customisation

### Disadvantages

- Extremely high maintenance effort
- Feature divergence
- Difficult upgrades
- Significant operational overhead

**Decision:** Rejected

---

## Alternative 3 — Multi-Tenant SaaS Platform

A single configurable platform serving multiple institutions.

### Advantages

- Scalable
- Commercially viable
- Lower maintenance cost
- Easier upgrades
- Consistent architecture
- Centralised quality improvements

### Disadvantages

- Slightly higher initial architectural complexity
- Stronger emphasis on tenant isolation and security

**Decision:** Accepted

---

# Architectural Implications

This decision establishes the following architectural principles.

## Tenant-Centric Design

Every business entity shall belong to an institution (tenant).

Examples include:

- Students
- Faculty
- Wallets
- Payments
- Attendance Records
- Merchants
- Devices
- Reports

---

## Configuration over Customisation

Institution-specific requirements should be implemented using configuration rather than modifying application code.

---

## Tenant Isolation

Data belonging to one institution shall never be accessible by another institution.

Logical isolation must be enforced across:

- Authentication
- Authorisation
- APIs
- Database queries
- Administrative interfaces

---

## Shared Platform

All tenants shall operate on the same application platform while maintaining isolated operational data.

---

## Extensibility

Future institutions should be onboarded through administrative configuration rather than software redevelopment.

---

# Consequences

## Positive

- Commercially scalable architecture
- Lower maintenance costs
- Simplified upgrades
- Consistent engineering standards
- Easier feature rollout
- Improved product sustainability

---

## Negative

- Increased initial design complexity
- Additional attention required for security
- More comprehensive testing strategy
- Greater emphasis on tenant isolation

These trade-offs are considered acceptable in exchange for long-term scalability and commercial viability.

---

# Related Documents

- PROJECT_VISION.md
- PRODUCT_REQUIREMENTS.md
- SRS.md
- ARCHITECTURE.md
- DATABASE.md

---

# Review Schedule

This decision should be reviewed if:

- The product strategy fundamentally changes.
- Regulatory requirements necessitate architectural changes.
- A future deployment model cannot be supported by the current multi-tenant approach.

Until such conditions arise, this ADR remains authoritative.

---

# Revision History

| Version | Date | Description |
|----------|------------|-------------------------------|
| 1.0 | 27 July 2026 | Initial architecture decision |