---
type: DataAsset
id: customers
title: Customers Table
description: One row per known customer, keyed by customer_id; source table for the orders table's customer_id foreign key.
resource: https://internal.example.com/data-eng/data/customers
tags: [data, customers]

generated:
  by: human:sam-patel
  at: 2026-03-15T09:00:00Z
status: draft
stale_after: 2026-12-15T00:00:00Z

provenance:
  confidence: medium
  source: primary

links:
  - rel: referenced-by
    to: orders-table
    note: orders.customer_id is a foreign key into this table.
---

# Schema

| Column | Type | Description |
|--------|------|-------------|
| `customer_id` | STRING | Globally unique customer identifier. |
| `email` | STRING | Contact email, PII. |
| `created_at` | TIMESTAMP | Account creation time. |

# Consumers

Referenced by the [orders table](./orders-table.md) via its `customer_id`
foreign key. Not yet human-verified — this concept carries no `verified`
entry, so it sits in the unverified trust tier until a data steward signs
off.

# Naming note

Household's own bundle also has a concept with the bare id `customers` —
a small home-baking side business's customer list, unrelated to this table
in every respect except the coincidental id. The two must never be treated
as the same concept; only a namespace-qualified reference (`data-eng/customers`
vs `household/customers`) tells them apart.
