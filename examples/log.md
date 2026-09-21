# Changelog

## 2026-09-21

- **Creation** — `orders-db-is-not-the-bottleneck`, from the 18 September capture load test.
- **Contradiction** — `orders-db-is-not-the-bottleneck` contradicts `sync-capture-limits-throughput`. Both kept; awaiting a human ruling.
- **Merge** — `payments-api` merged into `payment-service` (same system, found by alias search). Tombstone kept.
- **Update** — `payment-service`: capture note now cites the runbook per claim and points at the disputed throughput claim.
- **Update** — Migrated the bundle to AIX v0.3: OKF spellings corrected (`status: stable`, `sources[].resource`, actor convention).
- **Gap** — What limits capture throughput if not the orders database? No concept covers the acquirer connection pool.

## 2026-08-20

- **Update** — Migrated the bundle to AIX v0.2: OKF v0.2 trust fields, a `media` entry on `payment-service`, and a federation-qualified dependency on `data-eng/orders-events`.

## 2026-07-18

- **Creation** — Added `sync-capture-limits-throughput`.
- **Update** — Marked `payment-service` as superseded by `payment-service-v2`.
- **Creation** — Added `payment-service-v2`.

## 2026-05-28

- **Initialization** — Initial bundle.
- **Creation** — `payment-service`, `orders-table`, `jane-doe`.
