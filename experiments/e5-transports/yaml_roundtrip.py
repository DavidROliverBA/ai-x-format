#!/usr/bin/env python3
"""
experiments/e5-transports/yaml_roundtrip.py

Helper for E5's transport (e): simulates what any tool that parses and
rewrites frontmatter (kcmd, a normalising linter, ...) does to a bundle even
when it claims to "carry every key". For every file under <source>, loads
any YAML frontmatter with PyYAML and dumps it back with
`yaml.safe_dump(sort_keys=False)`, writing the result (new frontmatter +
unchanged body) to the same relative path under <dest>. Files without
frontmatter (index.md, log.md) and non-.md files (manifest.ai-xf.yaml) are
copied byte-for-byte, unchanged.

Requires PyYAML — run via `uv run --with pyyaml python3 yaml_roundtrip.py`.

Usage:
    python3 yaml_roundtrip.py <source-dir> <dest-dir>
"""
import re
import sys
from pathlib import Path

import yaml

FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", re.DOTALL)


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    src_root, dst_root = Path(sys.argv[1]), Path(sys.argv[2])
    for p in sorted(src_root.rglob("*")):
        if p.is_dir():
            continue
        rel = p.relative_to(src_root)
        out = dst_root / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        raw = p.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            out.write_bytes(raw)
            continue
        m = FM_RE.match(text)
        if not m:
            out.write_bytes(raw)
            continue
        fm = yaml.safe_load(m.group(1))
        body = text[m.end():]
        dump = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True)
        out.write_text(f"---\n{dump}---\n{body}", encoding="utf-8")
        print(f"  rewrote {rel}")


if __name__ == "__main__":
    main()
