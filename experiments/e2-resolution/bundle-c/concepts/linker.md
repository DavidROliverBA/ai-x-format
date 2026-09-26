---
type: Concept
id: linker
title: Linker
description: Exercises every `to:` reference form the --federation resolver has to handle — unqualified own-bundle-miss, qualified, explicit ai-x://, same-bundle self-qualification, and unresolved qualified.
tags: [fixture, e2-resolution]
generated:
  by: human:e2-fixture
  at: 2026-09-26T00:00:00Z
provenance:
  confidence: high
  source: primary

links:
  # (1) Unqualified, does not resolve in bundle C itself, resolves in exactly
  # one other federation bundle (a) — Foam rule, warning naming `a`, chosen `a`.
  - rel: relates-to
    to: only-a
    note: Unqualified — resolves only in bundle a (Foam rule, single candidate).
  # (2) Unqualified, resolves in BOTH bundle a and bundle b — Foam rule,
  # warning naming both, chosen `a` (alphabetically first).
  - rel: relates-to
    to: shared
    note: Unqualified — resolves in both a and b (Foam rule, collision).
  # (3) Qualified, resolves in the federation index — no finding.
  - rel: relates-to
    to: a/only-a
    note: Qualified — resolves cleanly against bundle a.
  # (4) Explicit ai-x:// form, resolves in the federation index — no finding.
  - rel: relates-to
    to: ai-x://b/shared
    note: Explicit ai-x:// form — resolves cleanly against bundle b.
  # (5) Qualified with THIS bundle's own namespace — MUST NOT (SPEC §9.2) — error,
  # even though `something` exists in this bundle and would otherwise resolve.
  - rel: relates-to
    to: c/something
    note: Same-bundle qualification — always an error, regardless of resolution.
  # (6) Qualified, does not resolve anywhere in the federation — warning, tolerated.
  - rel: relates-to
    to: b/missing
    note: Qualified — no such id in bundle b (or anywhere else in the federation).
---

# Linker

This concept exists only to carry the six `links` entries under test (see
frontmatter). Body links below are provided for every entry even though
SPEC §6.4's MUST-mirror rule applies only to genuinely same-bundle targets —
none of these six resolve inside this bundle, so mirroring here is
illustrative, not required.

- [Only In A](only-a) — unqualified, resolves only in bundle a.
- [Shared](shared) — unqualified, resolves in both a and b.
- [Only In A, qualified](a/only-a) — federation-qualified `namespace/id`.
- [Shared, via ai-x://](ai-x://b/shared) — the explicit `ai-x://namespace/id`
  form. `body_link_targets` recognises this scheme and also registers the
  bare `b/shared` form, so it would mirror either spelling of the `to:`.
- [Something, wrongly self-qualified](c/something) — MUST NOT per SPEC §9.2.
- [Missing in B](b/missing) — qualified, unresolved anywhere.
