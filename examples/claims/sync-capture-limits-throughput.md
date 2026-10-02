---
type: Claim
id: sync-capture-limits-throughput
title: Synchronous capture limits payment throughput
description: Payment throughput is capped by synchronous reads against the orders database.
tags: [payments, performance]

generated:
  by: human:jane-doe
  at: 2026-07-18T09:30:00Z
verified:
  - by: human:jane-doe
    at: 2026-07-18T10:30:00Z
status: stable
stale_after: 2026-12-31T00:00:00Z
sources:
  - id: payments-runbook
    resource: https://internal.example.com/runbooks/payments
    title: Payments runbook
  - id: q2-capacity-review
    resource: https://internal.example.com/reviews/2026-q2-capacity
    title: Q2 capacity review

provenance:
  source: secondary

links:
  - rel: supports
    to: payment-service-v2
    by: human:jane-doe
    at: 2026-07-18T00:00:00Z
    note: This claim is the case for the event-driven rewrite.
  - rel: describes
    to: payment-service
---

# Claim

Each capture blocks on a read of the orders table, so
[payment service](../concepts/payment-service.md) throughput cannot exceed what
the orders database serves synchronously.[^payments-runbook] Peak-hour queueing
in Q2 was attributed to this coupling.[^q2-capacity-review]

This is the argument for [payment service v2](../concepts/payment-service-v2.md).

[^payments-runbook]: Payments runbook
[^q2-capacity-review]: Q2 capacity review
