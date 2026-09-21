---
type: DataAsset
id: orders-table
title: Orders Table
description: One row per completed customer order.
resource: https://internal.example.com/data/orders
tags: [data, orders]

generated:
  by: human:jane-doe
  at: 2026-05-28T14:30:00Z
verified:
  - by: process:schema-checker
    at: 2026-08-01
  - by: human:jane-doe
    at: 2026-05-28
status: stable
stale_after: 2027-05-28

provenance:
  confidence: high
  source: primary

links:
  - rel: referenced-by
    to: payment-service
    note: Payment capture reads this table.
---

# Schema

| Column | Type | Description |
|--------|------|-------------|
| `order_id` | STRING | Globally unique order identifier. |
| `customer_id` | STRING | Foreign key to the customer. |
| `total` | NUMERIC | Order total in minor units. |

# Consumers

Read by the [payment service](./payment-service.md) and its
[v2 replacement](./payment-service-v2.md) to compute capture amounts.
