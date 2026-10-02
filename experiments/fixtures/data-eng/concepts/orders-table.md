---
type: DataAsset
id: orders-table
title: Orders Table (schema of record)
description: Canonical orders table owned by the data engineering team; one row per order, source of truth for the schema.
resource: https://internal.example.com/data-eng/data/orders
tags: [data, orders, schema]

generated:
  by: human:sam-patel
  at: 2026-04-10T09:00:00Z
verified:
  - by: process:schema-checker
    at: 2026-09-01T00:00:00Z
status: stable
stale_after: 2027-04-10T00:00:00Z

provenance:
  confidence: high
  source: primary

links:
  - rel: source-of
    to: orders-events
    note: Every write to this table emits an event onto the orders stream.
  - rel: relates-to
    to: example-payments/orders-table
    note: Same table, seen from the consumer side. The payments bundle's copy reflects how the payment service reads it, not the schema of record — that lives here.
---

# Schema

Data engineering owns this table's schema. It is the source of writes; reads
happen either directly or via the [orders event stream](./orders-events.md),
which is source-of by this table.

| Column | Type | Description |
|--------|------|-------------|
| `order_id` | STRING | Globally unique order identifier. |
| `customer_id` | STRING | Foreign key to the customer. |
| `total` | NUMERIC | Order total in minor units. |
| `status` | STRING | Order lifecycle state. |

# Relationship to the payments bundle's copy

The [payments bundle also describes an `orders-table` concept](https://internal.example.com/data/orders)
under its own id — same physical table, different bundle, same id string.
That copy documents the table from the consumer side (what the payment
service reads); this concept is the schema owner's side. The two ids
collide deliberately and are not linked as the same concept — they are
cross-referenced (`relates-to`) so a federation consumer can tell they
describe the same table without merging the two records.

# Verification

Verified by an automated schema checker, not yet by a human reviewer —
machine-confirmed trust tier.
