---
type: Concept
id: shared
title: Shared Concept (bundle B)
description: A concept sharing its id with `shared` in bundle A, on purpose — E2 collision fixture.
tags: [fixture, e2-resolution]
generated:
  by: human:e2-fixture
  at: 2026-09-26T00:00:00Z
provenance:
  confidence: high
  source: primary
---

# Shared (bundle B)

Fixture concept used to test cross-bundle id collision resolution
(SPEC §9.2, the Foam rule). A concept with the same `id`, [`shared`
in bundle A](../../bundle-a/concepts/shared.md), exists deliberately —
this is the collision under test.
