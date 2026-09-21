---
type: Claim
id: orders-db-is-not-the-bottleneck
title: The orders database is not the payment bottleneck
description: A load test shows the orders database has headroom at peak; the limit is elsewhere.
tags: [payments, performance]

generated:
  by: curator/1.0
  at: 2026-09-21T08:00:00Z
status: draft
stale_after: 2026-12-21
sources:
  - id: sept-load-test
    resource: https://internal.example.com/tests/2026-09-18-capture-load
    title: Capture load test, 18 September 2026

provenance:
  source: secondary

links:
  - rel: contradicts
    to: sync-capture-limits-throughput
    state: open
    by: curator/1.0
    at: 2026-09-21
    note: New load test disagrees with the Q2 attribution. Both claims kept; awaiting a human ruling.
---

# Claim

Under the September load test the orders database ran at 40% utilisation while
capture latency still degraded.[^sept-load-test] The limit therefore sits
elsewhere, most likely in the acquirer connection pool.

This contradicts the claim that
[synchronous capture limits throughput](./sync-capture-limits-throughput.md).
The curator agent recorded the disagreement and left both claims intact; it did
not rewrite either one. The contradiction stays `open` until a person rules.

[^sept-load-test]: Capture load test, 18 September 2026
