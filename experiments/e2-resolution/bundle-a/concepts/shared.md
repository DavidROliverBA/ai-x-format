---
type: Concept
id: shared
title: Shared Concept (bundle A)
description: A concept sharing its id with `shared` in bundle B, on purpose — E2 collision fixture.
tags: [fixture, e2-resolution]
generated:
  by: human:e2-fixture
  at: 2026-09-26T00:00:00Z
provenance:
  confidence: high
  source: primary
---

# Shared (bundle A)

Fixture concept used to test cross-bundle id collision resolution
(SPEC §9.2, the Foam rule). A concept with the same `id`, [`shared`
in bundle B](../../bundle-b/concepts/shared.md), exists deliberately —
this is the collision under test.
