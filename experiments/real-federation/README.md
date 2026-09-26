# E7: a real federation

Not a fixture. Two bundles exported from the author's working vault with
`ai-x-export` (`psychology`, 102 concepts; `ai-concepts`, 63 concepts) plus
`examples/`, held together by `federation.ai-x.yaml`. The bundles live in
sibling repositories (`../../../psychology-kb`, `../../../ai-concepts-kb`),
which is why the manifest uses `source: path`; they are not published.

Re-run:

```bash
python3 ../../tools/ai-x-validate.py ~/github/psychology-kb  --level 3 --federation federation.ai-x.yaml --stats
python3 ../../tools/ai-x-validate.py ~/github/ai-concepts-kb --level 3 --federation federation.ai-x.yaml --stats
```

Results in `../RESULTS.md` § E7.
