---
type: Concept
id: customers
title: Customers (Household Bakes)
description: Notes on the regular customers of a small home-baking side business run from the house.
tags: [household, baking, customers]

generated:
  by: human:household-admin
  at: 2026-01-10T18:00:00Z
status: stable
stale_after: 2026-07-10T00:00:00Z

provenance:
  confidence: medium
  source: primary
---

# Overview

"Household Bakes" is a small, fictional home-baking side business run out of
the house on weekends. Most orders come by word of mouth from a handful of
regulars: a couple of neighbours, a local coffee shop that takes a standing
weekly order, and a few repeat birthday-cake customers.

# Naming note

This concept deliberately shares the bare id `customers` with the data
engineering bundle's [Customers Table](../../data-eng/concepts/customers.md)
concept — a completely different thing (a production database table, not a
handwritten list of baking regulars). The two must never be treated as the
same concept. Only a namespace-qualified reference (`household/customers` vs
`data-eng/customers`) tells them apart; this bundle has no other link to
`data-eng` or `payments`.
