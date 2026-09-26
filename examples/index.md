# Example Payments Bundle

A minimal AI-X bundle showing a service being superseded, its data dependency,
an author, two claims that disagree, and a merge tombstone.

## Services

- [Payment Service](./concepts/payment-service.md) — authorises and captures customer payments (being replaced).
- [Payment Service v2](./concepts/payment-service-v2.md) — the replacement, event-driven.
- [Payments API](./concepts/payments-api.md) — tombstone; merged into the payment service.

## Claims

- [Synchronous capture limits payment throughput](./claims/sync-capture-limits-throughput.md) — the case for v2, cited per claim.
- [The orders database is not the payment bottleneck](./claims/orders-db-is-not-the-bottleneck.md) — contradicts the claim above; contradiction open.

## Data

- [Orders Table](./concepts/orders-table.md) — one row per completed order.

## People

- [Jane Doe](./people/jane-doe.md) — platform engineer, author of the payment services.
