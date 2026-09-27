# Household Bundle

Fixture bundle for AI-XF federation experiments. A small, fictional domestic
domain (a home-baking side business, boiler servicing, home insurance
renewal) with no business relationship to the `payments` or `data-eng`
bundles. Shares one id (`customers`) with `data-eng` to test that unrelated
collisions never resolve across namespaces. No real people, addresses, or
companies.

## Concepts

- [Customers (Household Bakes)](./concepts/customers.md) — regulars of a small home-baking side business; shares an id with `data-eng/customers` but is otherwise unrelated.

## Runbooks

- [Annual Boiler Service Runbook](./concepts/boiler-service.md) — supported by the claim that annual servicing prevents most callouts.
- [Home Insurance Renewal Runbook](./concepts/insurance-renewal.md) — supported by the claim that comparison quotes beat auto-renewal.

## Claims

- [An annual boiler service prevents most emergency callouts](./claims/annual-boiler-service-prevents-most-callouts.md) — supports the boiler service runbook.
- [Getting renewal quotes beats accepting auto-renewal](./claims/insurance-renewal-quotes-beat-auto-renew.md) — supports the insurance renewal runbook.
