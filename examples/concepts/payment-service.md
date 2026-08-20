---
type: System
id: payment-service
title: Payment Service
description: Handles authorisation and capture for all customer payments.
resource: https://internal.example.com/services/payment
tags: [platform, payments]
aliases: [Payments API, PaymentSvc]

# OKF v0.2 trust & lifecycle
generated:
  by: human:jane-doe
  at: 2026-07-18T09:12:00Z
verified:
  - by: human:jane-doe
    at: 2026-07-18
status: deprecated
stale_after: 2026-12-31
sources:
  - uri: https://internal.example.com/runbooks/payments
    title: Payments runbook

# AIX additions
provenance:
  confidence: high
  source: primary

links:
  - rel: depends-on
    to: orders-table
    note: Reads order totals to compute the capture amount.
  - rel: superseded-by
    to: payment-service-v2
    note: v2 replaces the synchronous capture flow with events.
  - rel: authored-by
    to: jane-doe

media:
  - uri: https://internal.example.com/diagrams/payment-flow.png
    hash: sha256:9f2c8a41d6e07b3355c1a2f4e8b9d0c7a6f5e4d3c2b1a09876543210fedcba98
    title: Payment capture flow (v1, synchronous)
    describes: payment-service
---

# Overview

The payment service authorises and captures customer payments. It depends on the
[orders table](./orders-table.md) to compute capture amounts and is being
replaced by [payment service v2](./payment-service-v2.md).

Maintained by [Jane Doe](../people/jane-doe.md).

# Notes

Capture is currently synchronous, which couples throughput to the orders
database. v2 addresses this.
