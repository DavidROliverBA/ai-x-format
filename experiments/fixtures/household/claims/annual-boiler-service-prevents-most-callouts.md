---
type: Claim
id: annual-boiler-service-prevents-most-callouts
title: An annual boiler service prevents most emergency callouts
description: Boilers serviced annually rarely need an emergency callout compared to unserviced boilers, based on the household's own repair record.
tags: [household, maintenance]

generated:
  by: human:household-admin
  at: 2026-02-05T09:00:00Z
verified:
  - by: human:household-admin
    at: 2026-02-05T10:00:00Z
status: stable
stale_after: 2027-02-05T00:00:00Z
sources:
  - id: repair-log
    resource: https://example.com/household/repair-log-2023-2026
    title: Household boiler repair log, 2023–2026

provenance:
  source: primary

links:
  - rel: supports
    to: boiler-service
    note: This is the case for keeping the annual service on the calendar rather than waiting for a fault.
---

# Claim

Across three years of the household's own repair log, the one year the
boiler service was skipped was also the year it needed an unplanned
emergency callout.[^repair-log] That is a small sample, but it is the
household's own evidence, and it is the case for keeping the
[annual boiler service](../concepts/boiler-service.md) on a fixed schedule
rather than waiting for something to break.

[^repair-log]: Household boiler repair log, 2023–2026
