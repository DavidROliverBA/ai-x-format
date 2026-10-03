# Federation experiments

Runnable evidence for what belongs in AI-XF v0.4. The plan, with pass criteria
written before anything ran, is
`docs/plans/2026-09-26-federation-experiments-plan.md` in the author's vault;
the numbers land in [`RESULTS.md`](./RESULTS.md).

| Dir | Experiment | Question |
|---|---|---|
| `fixtures/` | Phase 0 | Three bundles (`payments` = `../examples`, `data-eng`, `household`) with two deliberate id collisions, shared vocabularies, a federation manifest, and 20 questions with known answers |
| `e1-transport/` | E1 | Does a consumer resolve every cross-bundle reference, and reproduce what it read, under submodule / subtree / subtree + manifest? |
| `e2-resolution/` | E2 | Under an id collision, what happens to a qualified, an unqualified, and an explicit `ai-xf://` reference? |
| `e3-index/` | E3 | qmd collections vs one collection vs plain BM25 over the union: precision and namespace survival |
| `e4-mcp/` | E4 | Can an agent answer the 20 questions through a tools-only MCP server, citing the right `namespace/id`? |
| `e5-transports/` | E5 | Which trust fields survive git, rsync, iCloud, and the Knowledge Catalog round trip byte-for-byte? |
| `e6-oci/` | E6 | ORAS + Cosign: does verification catch a tampered bundle, and what does it cost? |
| `real-federation/` | E7 | Two bundles exported from a working vault plus `examples/`: what does federation look like on real data? |
| `e8-freshness/` | E8 | Add / edit / rename / delete through the real exporter: does a bundle reconcile or accumulate, and can a consumer tell? |
| `e9-knowledgex/` | E9 | Does AI-XF interoperate with a third-party OKF producer (KnowledgeX), in both directions? |
| `e10-database/` | E10 | Up: what happens when a department of concurrent writers moves bundles into Postgres (round trip, locking, CQRS, blue/green)? |
| `e11-migration/` | E11 | In: what a Confluence space or SharePoint Word library keeps, loses or leaks on the way into AI-XF, naive versus mapped |
| `e12-longview/` | E12 | Across: an AI-XF bundle federated into Longview's database and exported back out |

Everything here is a fixture, not a product. Re-run with the commands in each
directory's `run.sh`; each experiment records the tool and client versions it
ran against.
