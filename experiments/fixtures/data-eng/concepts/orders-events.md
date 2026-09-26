---
type: System
id: orders-events
title: Orders Event Stream
description: Kafka topic publishing order lifecycle events (created, updated, cancelled) for downstream consumers.
resource: https://internal.example.com/data-eng/streams/orders-events
tags: [data, streaming, orders]

generated:
  by: human:sam-patel
  at: 2026-06-01T10:00:00Z
verified:
  - by: human:sam-patel
    at: 2026-06-01
status: stable
stale_after: 2027-06-01
sources:
  - id: orders-events-design
    resource: https://internal.example.com/data-eng/designs/orders-events
    title: Orders event stream design

provenance:
  confidence: high
  source: primary

links:
  - rel: derived-from
    to: orders-table
    note: Events are emitted on writes to this table.
  - rel: depended-on-by
    to: example-payments/payment-service-v2
    note: Federation-qualified — payment service v2 consumes this stream asynchronously instead of reading the orders table synchronously.
---

# Overview

The orders event stream is derived from the [orders table](./orders-table.md):
every insert or update to that table emits an event onto this
topic.[^orders-events-design] Consumers subscribe instead of polling the
table directly.

# Consumers

The payments bundle's [payment service v2](https://internal.example.com/services/payment-v2)
depends on this stream to compute capture amounts asynchronously, replacing
its predecessor's synchronous read of the orders table. That dependency is
declared on the payments side as a federation-qualified `depends-on:
data-eng/orders-events`; this concept declares the inverse `depended-on-by`
edge back to `example-payments/payment-service-v2`.

[^orders-events-design]: Orders event stream design
