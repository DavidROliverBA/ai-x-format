---
type: System
id: payment-service
title: Payment Service
description: Handles authorisation and capture for all customer payments.
resource: https://internal.example.com/services/payment
tags: [platform, payments]
timestamp: 2026-07-18T09:12:00Z
aliases: [Payments API, PaymentSvc]

provenance:
  confidence: high
  freshness: current
  source: primary
  verified: true
  reviewed: 2026-07-18

links:
  - rel: depends-on
    to: orders-table
    note: Reads order totals to compute the capture amount.
  - rel: superseded-by
    to: payment-service-v2
    note: v2 replaces the synchronous capture flow with events.
  - rel: authored-by
    to: jane-doe
---

# Overview

The payment service authorises and captures customer payments. It depends on the
[orders table](./orders-table.md) to compute capture amounts and is being
replaced by [payment service v2](./payment-service-v2.md).

Maintained by [Jane Doe](../people/jane-doe.md).

# Notes

Capture is currently synchronous, which couples throughput to the orders
database. v2 addresses this.
