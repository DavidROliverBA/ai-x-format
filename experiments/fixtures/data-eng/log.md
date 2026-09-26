# Changelog

## 2026-09-26

- **Update** — Migrated bundle to AI-X v0.3; confirmed federation-qualified links to `example-payments/payment-service-v2` and `example-payments/orders-table` use the `namespace/id` form.

## 2026-09-01

- **Update** — `orders-table` re-verified by the automated schema checker (machine-confirmed tier; still awaiting human review).

## 2026-08-12

- **Creation** — `event-replay-is-cheaper-than-backfill`, from the 10 August recovery drill and its cost analysis.
- **Contradiction** — `event-replay-is-cheaper-than-backfill` contradicts `retention-policy`'s batch-backfill assumption. Both kept; awaiting a data steward's ruling.

## 2026-06-01

- **Creation** — `orders-events`, the Kafka stream derived from `orders-table`.
- **Update** — `orders-table`: added `derived-from`/`source-of` pairing with the new event stream.

## 2026-04-10

- **Creation** — `orders-table`, the schema-of-record for orders. Cross-referenced against the payments bundle's `orders-table` copy (same table, different vantage point).

## 2026-03-15

- **Creation** — `customers`, the schema-of-record for customer data.

## 2026-02-01

- **Initialization** — Bundle created for the data engineering team's schema and stream ownership.
- **Creation** — `retention-policy`, covering both `orders-table` and `customers`.
