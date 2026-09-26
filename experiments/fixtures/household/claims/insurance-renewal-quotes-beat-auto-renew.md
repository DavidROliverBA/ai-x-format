---
type: Claim
id: insurance-renewal-quotes-beat-auto-renew
title: Getting renewal quotes beats accepting auto-renewal
description: Comparing at least two alternative quotes before the renewal date has beaten the auto-renew price every year on the household's own record.
tags: [household, finance]

generated:
  by: human:household-admin
  at: 2026-03-05T09:00:00Z
status: draft
stale_after: 2026-11-05
sources:
  - id: renewal-price-log
    resource: https://example.com/household/renewal-price-log
    title: Household insurance renewal price log

provenance:
  confidence: low
  source: primary

links:
  - rel: supports
    to: insurance-renewal
    note: This is the case for always shopping quotes before the renewal date rather than letting it auto-renew.
---

# Claim

Every year on the household's price log, at least one comparison quote has
undercut the incumbent insurer's auto-renewal price, usually by shopping
around six weeks ahead of the renewal date.[^renewal-price-log] The sample is
small and the margin varies year to year — hence the low confidence — but it
is the case behind the
[insurance renewal runbook](../concepts/insurance-renewal.md) always
comparing quotes rather than letting the policy auto-renew.

[^renewal-price-log]: Household insurance renewal price log
