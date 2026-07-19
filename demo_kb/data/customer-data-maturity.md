---
title: Customer and Operations Data Maturity Baseline
maturity_score: 2
covered_sources: crm, billing, support, product telemetry
owner: data-governance
---
# Customer and Operations Data Maturity Baseline

CRM and billing data exist but customer identity is not fully reconciled across support and product telemetry. Daily refresh is available for CRM and billing, while support exports remain batch-driven.

Current gaps:
- no canonical customer 360 identifier across all four domains
- telemetry access is limited to platform engineering
- support case taxonomy is inconsistent by region
- lineage is partial and feature definitions are not yet standardized

Projects depending on joined customer behavior across CRM, billing, support, and product telemetry should expect enablement work before production deployment.
