---
type: System
id: payment-service-v2
title: Payment Service v2
description: Event-driven replacement for the payment service.
resource: https://internal.example.com/services/payment-v2
tags: [platform, payments]
timestamp: 2026-07-18T09:10:00Z

provenance:
  confidence: medium
  freshness: current
  source: primary
  verified: false
  reviewed: 2026-07-18

links:
  - rel: supersedes
    to: payment-service
    note: Replaces the synchronous capture flow.
  - rel: depends-on
    to: orders-table
  - rel: authored-by
    to: jane-doe
---

# Overview

Payment service v2 supersedes the original [payment service](./payment-service.md)
with an event-driven capture flow. It still depends on the
[orders table](./orders-table.md) but consumes it asynchronously.

Authored by [Jane Doe](../people/jane-doe.md).

# Status

In build. Provenance `verified: false` until the capture reconciliation tests
pass.
