---
type: Concept
id: only-a
title: Only In A
description: A concept that exists only in bundle A's namespace — no collision.
tags: [fixture, e2-resolution]
generated:
  by: human:e2-fixture
  at: 2026-09-26T00:00:00Z
provenance:
  confidence: high
  source: primary
---

# Only In A

Fixture concept unique to bundle A's namespace. Used to test that an
unqualified reference resolving in exactly one other federation bundle still
gets the Foam-rule warning (SPEC §9.2) — it is never resolved silently, even
with a single candidate.
