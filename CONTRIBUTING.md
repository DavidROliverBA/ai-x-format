# Contributing to AI-XF

AI-XF v0.3 is an early draft designed for backward-compatible growth. Contributions
and alternative implementations are welcome.

## Ways to help

- **Kick the spec.** Open an issue where `SPEC.md` is ambiguous, under-specified,
  or over-reaching. The design bias is *minimal* — argue a field out as readily
  as in.
- **Write a consumer or producer.** A visualiser, a graph loader, an exporter
  from another tool. The format is the contract; tooling is meant to be
  independently swappable.
- **Add conformance cases.** Bundles that *should* pass and bundles that *should*
  fail, with the level they target.

## Ground rules

- Keep AI-XF a **strict superset of OKF v0.2**. Any change that would make a
  conformant AI-XF bundle fail OKF validation is out of scope.
- Prefer conventions that stay "just markdown + YAML + files": readable without
  tooling, diffable in git, parseable without an SDK.
- Every normative change to `SPEC.md` must keep the reference validator
  (`tools/ai-xf-validate.py`) and the `examples/` bundle passing.

- Keep **format** and **policy** apart. `SPEC.md` says what a bundle can express;
  `CURATOR.md` suggests how a curator should behave. Behavioural rules do not
  become MUSTs.

## Validating locally

```bash
python3 tools/ai-xf-validate.py examples/ --level 3 --stats
```
