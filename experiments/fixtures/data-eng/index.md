# Data Engineering Bundle

Fixture bundle for AI-XF federation experiments. The data engineering team's
view of the orders and customers data, the event stream payment service v2
consumes, and the retention policy governing both tables. Deliberately shares
two ids (`orders-table`, `customers`) with other bundles in the federation.

## Systems

- [Orders Event Stream](./concepts/orders-events.md) — Kafka topic of order lifecycle events, consumed by `example-payments/payment-service-v2`.

## Data

- [Orders Table](./concepts/orders-table.md) — schema of record for orders; same id as `example-payments/orders-table`, different bundle, different vantage point.
- [Customers Table](./concepts/customers.md) — schema of record for customers; same id as `household/customers`, unrelated content.

## Policy

- [Retention Policy](./concepts/retention-policy.md) — retention and deletion rules for orders and customer data.

## Claims

- [Event replay is cheaper than a batch backfill](./claims/event-replay-is-cheaper-than-backfill.md) — contradicts an assumption in the retention policy; contradiction open.
