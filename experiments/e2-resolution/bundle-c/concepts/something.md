---
type: Concept
id: something
title: Something (bundle C)
description: "A same-bundle target for `linker`'s deliberately-wrong `to: c/something` self-qualification."
tags: [fixture, e2-resolution]
generated:
  by: human:e2-fixture
  at: 2026-09-26T00:00:00Z
provenance:
  confidence: high
  source: primary
---

# Something (bundle C)

Exists so that `to: c/something` in [`linker`](./linker.md) *would* resolve
were self-qualification allowed — proving the same-bundle-qualification
error (SPEC §9.2) fires regardless of whether the id exists, not because it
doesn't.
