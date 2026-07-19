---
title: Platform Delivery Constraints and Integration Rules
readiness_score: 3
systems: crm, billing, support, data-platform, workflow-engine
owner: enterprise-architecture
refresh_mode: async
refresh_cadence: daily
source_system: cmdb, platform telemetry, and architecture reviews
---
# Platform Delivery Constraints and Integration Rules

The preferred delivery pattern is to integrate through the workflow engine and data platform rather than point-to-point custom services.

Current technical constraints:
- billing APIs are stable but rate-limited
- CRM integration is well supported
- support platform has legacy exports and higher workflow overlap risk
- workflow engine changes require architecture review when more than three systems are involved

Ideas spanning four or more enterprise systems should be treated as medium-to-high execution complexity.
