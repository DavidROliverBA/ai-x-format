---
type: Policy
id: retention-policy
title: Orders and Customer Data Retention Policy
description: Retention and deletion policy for order and customer data holdings, including the batch backfill job used for disaster recovery.
tags: [data, governance, policy]

generated:
  by: human:sam-patel
  at: 2026-02-01T09:00:00Z
verified:
  - by: human:priya-shah
    at: 2026-02-05T00:00:00Z
status: stable
stale_after: 2027-02-01T00:00:00Z
sources:
  - id: data-retention-standard
    resource: https://internal.example.com/data-eng/policies/retention-standard
    title: Data retention standard v3

provenance:
  source: secondary

links:
  - rel: relates-to
    to: orders-table
  - rel: relates-to
    to: customers
---

# Policy

Order records in the [orders table](./orders-table.md) are retained for
seven years for tax purposes; customer records in the
[customers table](./customers.md) are retained for the lifetime of the
account plus two years, per the data retention standard.[^data-retention-standard]

# Disaster recovery

The policy currently assumes recovery of either table happens via a nightly
batch backfill job. See the open contradiction against
[event replay is cheaper than backfill](../claims/event-replay-is-cheaper-than-backfill.md),
which questions that assumption for the orders table specifically.

[^data-retention-standard]: Data retention standard v3
