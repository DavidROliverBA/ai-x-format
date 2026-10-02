---
type: Claim
id: event-replay-is-cheaper-than-backfill
title: Event replay is cheaper than a batch backfill for recovering orders state
description: Replaying the orders-events stream from offset costs less compute than re-running the nightly batch backfill job for the same recovery window.
tags: [data, streaming, cost]

generated:
  by: human:sam-patel
  at: 2026-08-12T09:00:00Z
status: draft
stale_after: 2026-12-12T00:00:00Z
sources:
  - id: replay-cost-analysis
    resource: https://internal.example.com/data-eng/analysis/replay-vs-backfill-cost
    title: Replay vs backfill cost analysis, August 2026

provenance:
  confidence: medium
  source: primary

links:
  - rel: supports
    to: orders-events
    note: This is the case for keeping the stream's retention window long enough to replay from, rather than relying on batch recovery.
  - rel: contradicts
    to: retention-policy
    state: open
    by: human:sam-patel
    at: 2026-08-12T00:00:00Z
    note: The policy's disaster-recovery approach assumes batch backfill is the cheaper recovery path; this analysis disagrees for the orders table specifically. Both kept; awaiting a ruling.
---

# Claim

A recovery drill on 2026-08-10 replayed 14 days of the
[orders event stream](./orders-events.md) end to end for a fraction of the
compute cost of the equivalent nightly batch backfill job.[^replay-cost-analysis]
This is the case for extending the stream's retention window rather than
leaning on the backfill job as the primary recovery path.

This contradicts an assumption baked into the
[retention policy](../concepts/retention-policy.md), which currently treats
batch backfill as the default disaster-recovery method for order data. The
policy was not rewritten to agree — the contradiction stays `open` until a
data steward rules on it.

[^replay-cost-analysis]: Replay vs backfill cost analysis, August 2026
