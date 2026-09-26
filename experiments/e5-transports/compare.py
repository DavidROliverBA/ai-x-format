#!/usr/bin/env python3
"""
experiments/e5-transports/compare.py

Frontmatter-aware, key-by-key diff for E5 (trust survival through
transports) — MyVault plan `docs/plans/2026-09-26-federation-experiments-
plan.md`, E5. Self-contained: only reads from the two directories given on
the command line, never touches `examples/`, `tools/aix-validate.py`, or
other `experiments/*` directories.

Two things are measured for every file that exists at the same relative
path under both directories:

  1. Whole-file byte identity (`diff -q` style).
  2. Frontmatter split into top-level keys (`type`, `id`, `generated`,
     `verified`, `sources`, `status`, `stale_after`, `provenance`, `links`,
     `media`, ...), each classified:

       preserved   text of the key's block is byte-identical
       normalised  text differs but the parsed value is semantically equal
                   (quoting, date/timestamp representation, flow vs block
                   sequences, line wrapping, indentation style)
       lost        the key is missing in the destination, or the parsed
                   value actually differs

Body content (below the closing `---`) is compared separately and reported
as informational — it is not part of the "which trust keys survive" question
E5 asks, but a `body_identical: no` is worth surfacing.

PyYAML is used if importable (`uv run --with pyyaml python3 compare.py ...`)
for accurate semantic equality, in particular for the date/datetime
normalisation that YAML's implicit timestamp resolution triggers. Without
PyYAML, a minimal fallback parser (same spirit as, but independent of,
tools/aix-validate.py's) is used; it is deliberately simple and only needs
to be right for the flat/1-nested-level/list-of-maps shapes AIX frontmatter
actually uses.

Usage:
    python3 compare.py diff <source-dir> <dest-dir> --transport NAME [--json-out PATH]
    python3 compare.py summary <json-file> [<json-file> ...]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import OrderedDict
from datetime import date, datetime, timezone
from pathlib import Path

# --- YAML loading (PyYAML if available, else a minimal fallback) -----------

try:
    import yaml  # type: ignore

    HAVE_PYYAML = True

    def load_yaml(text: str):
        return yaml.safe_load(text)
except Exception:  # pragma: no cover - fallback path
    HAVE_PYYAML = False

    def load_yaml(text: str):
        return _mini_yaml(text)


def _coerce(v: str):
    s = v.strip()
    if s == "" or s == "~" or s.lower() == "null":
        return None
    if s.lower() in ("true", "false"):
        return s.lower() == "true"
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        return [_coerce(x) for x in inner.split(",")] if inner else []
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return date.fromisoformat(s)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}T[\d:.]+Z?", s):
        return s  # leave timestamps as strings in the fallback parser
    return s


def _mini_yaml(text: str):
    """Minimal parser: top-level scalars/lists/maps, one level of nesting,
    and lists-of-maps (as used by AIX `generated`, `sources`, `links`, ...).
    Not a general YAML parser — matches the subset AIX frontmatter uses."""
    root: dict = {}
    lines = [ln.rstrip("\n") for ln in text.split("\n")]
    i, n = 0, len(lines)

    def indent(ln: str) -> int:
        return len(ln) - len(ln.lstrip(" "))

    while i < n:
        ln = lines[i]
        if not ln.strip() or ln.lstrip().startswith("#"):
            i += 1
            continue
        if indent(ln) != 0:
            i += 1
            continue
        key, _, rest = ln.partition(":")
        key, rest = key.strip(), rest.strip()
        if rest:
            root[key] = _coerce(rest)
            i += 1
            continue
        block = []
        j = i + 1
        while j < n and (not lines[j].strip() or indent(lines[j]) > 0):
            block.append(lines[j])
            j += 1
        root[key] = _mini_parse_block(block)
        i = j
    return root


def _mini_parse_block(block: list[str]):
    items = [ln for ln in block if ln.strip() and not ln.lstrip().startswith("#")]
    if not items:
        return None
    base = min(len(ln) - len(ln.lstrip(" ")) for ln in items)
    is_list = all(
        ln.lstrip().startswith("- ") or ln.strip() == "-"
        for ln in items
        if (len(ln) - len(ln.lstrip(" "))) == base
    )
    if is_list:
        result, cur, key_indent = [], None, None
        for ln in items:
            ind = len(ln) - len(ln.lstrip(" "))
            body = ln.lstrip()
            if ind == base and body.startswith("-"):
                if cur is not None:
                    result.append(cur)
                key_indent = ind + 2
                body = body[1:].strip()
                if not body:
                    cur = {}
                elif ":" in body:
                    k, _, v = body.partition(":")
                    cur = {k.strip(): _coerce(v)}
                else:
                    cur = _coerce(body)
            elif isinstance(cur, dict) and ":" in body:
                k, _, v = body.partition(":")
                cur[k.strip()] = _coerce(v)
        if cur is not None:
            result.append(cur)
        return result
    result = {}
    for ln in items:
        if (len(ln) - len(ln.lstrip(" "))) != base:
            continue
        k, _, v = ln.strip().partition(":")
        result[k.strip()] = _coerce(v.strip())
    return result


# --- frontmatter splitting ---------------------------------------------------

FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", re.DOTALL)
KEY_LINE_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_.\-]*)\s*:")


def split_frontmatter(text: str):
    """Return (frontmatter_raw, body) or (None, text) if no frontmatter."""
    m = FM_RE.match(text)
    if not m:
        return None, text
    return m.group(1), text[m.end():]


def split_blocks(fm_raw: str):
    """Split frontmatter text into top-level key blocks, preserving order.

    Returns (order, {key: raw_block_text}, [standalone comment lines]).
    A block's raw text includes its own `key:` line and every deeper-
    indented / blank line that follows, with trailing blank lines trimmed.
    """
    lines = fm_raw.split("\n")
    blocks: "OrderedDict[str, list[str]]" = OrderedDict()
    comments: list[str] = []
    cur_key = None
    for ln in lines:
        if ln.strip() == "":
            if cur_key is not None:
                blocks[cur_key].append(ln)
            continue
        indent = len(ln) - len(ln.lstrip(" "))
        if indent == 0:
            stripped = ln.strip()
            if stripped.startswith("#"):
                comments.append(ln)
                continue
            m = KEY_LINE_RE.match(stripped)
            if m:
                cur_key = m.group(1)
                blocks.setdefault(cur_key, [])
                blocks[cur_key].append(ln)
                continue
            if cur_key is not None:
                blocks[cur_key].append(ln)
            continue
        if cur_key is not None:
            blocks[cur_key].append(ln)
    for k in list(blocks):
        while blocks[k] and blocks[k][-1].strip() == "":
            blocks[k].pop()
    order = list(blocks.keys())
    return order, {k: "\n".join(v) for k, v in blocks.items()}, comments


# --- semantic equality --------------------------------------------------------

def normalize(v):
    """Canonicalise a parsed YAML value so formatting-only differences
    (date vs datetime, tz representation, key/list order within a value)
    disappear and only real content differences remain."""
    if isinstance(v, dict):
        return {k: normalize(v[k]) for k in v}
    if isinstance(v, list):
        return [normalize(x) for x in v]
    if isinstance(v, datetime):
        dt = v if v.tzinfo else v.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(v, date):
        return v.isoformat()
    return v


def describe_formatting_diff(src_block: str, dst_block: str) -> str:
    reasons = []
    if re.search(r":\s*\[", src_block) and not re.search(r":\s*\[", dst_block):
        reasons.append("flow list -> block list")
    src_list_indent = re.search(r"\n( *)- ", src_block)
    dst_list_indent = re.search(r"\n( *)- ", dst_block)
    if src_list_indent and dst_list_indent and len(src_list_indent.group(1)) != len(dst_list_indent.group(1)):
        reasons.append("list indentation style")
    if re.search(r"T\d{2}:\d{2}:\d{2}Z?", src_block) and re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", dst_block):
        reasons.append("timestamp: 'T..Z' -> ' ..+00:00'")
    if src_block.count("\n") != dst_block.count("\n"):
        reasons.append("line rewrapped")
    if not reasons:
        reasons.append("formatting differs")
    return "; ".join(reasons)


# --- per-file, per-key comparison --------------------------------------------

def compare_file(rel: str, src_path: Path, dst_path: Path) -> dict:
    src_bytes = src_path.read_bytes()
    if not dst_path.exists():
        return {"rel": rel, "byte_identical": False, "file_status": "missing-in-dest", "keys": {}}
    dst_bytes = dst_path.read_bytes()
    byte_identical = src_bytes == dst_bytes

    try:
        src_text = src_bytes.decode("utf-8")
        dst_text = dst_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return {"rel": rel, "byte_identical": byte_identical, "file_status": "binary", "keys": {}}

    src_fm_raw, src_body = split_frontmatter(src_text)
    dst_fm_raw, dst_body = split_frontmatter(dst_text)
    if src_fm_raw is None:
        # Not a frontmatter file (index.md, log.md, ...) — byte comparison only.
        return {"rel": rel, "byte_identical": byte_identical, "file_status": "no-frontmatter", "keys": {}}
    if dst_fm_raw is None:
        return {"rel": rel, "byte_identical": byte_identical, "file_status": "frontmatter-lost", "keys": {}}

    src_order, src_blocks, src_comments = split_blocks(src_fm_raw)
    _, dst_blocks, dst_comments = split_blocks(dst_fm_raw)

    keys: dict[str, dict] = {}
    for key in src_order:
        src_block = src_blocks[key]
        dst_block = dst_blocks.get(key)
        if dst_block is None:
            keys[key] = {"status": "lost", "note": "key missing from destination"}
            continue
        if src_block.rstrip("\n") == dst_block.rstrip("\n"):
            keys[key] = {"status": "preserved", "note": ""}
            continue
        try:
            src_val = load_yaml(src_block + "\n").get(key)
            dst_val = load_yaml(dst_block + "\n").get(key)
        except Exception as e:  # noqa: BLE001
            keys[key] = {"status": "lost", "note": f"unparsable after transport: {e}"}
            continue
        if normalize(src_val) == normalize(dst_val):
            keys[key] = {"status": "normalised", "note": describe_formatting_diff(src_block, dst_block)}
        else:
            keys[key] = {"status": "lost", "note": "value changed"}

    return {
        "rel": rel,
        "byte_identical": byte_identical,
        "file_status": "ok",
        "body_identical": src_body == dst_body,
        "comments_lost": (len(src_comments) > 0 and src_comments != dst_comments),
        "keys": keys,
    }


def discover_files(root: Path) -> list[str]:
    out = []
    for p in sorted(root.rglob("*")):
        if p.is_dir():
            continue
        if ".git" in p.parts or p.name == ".DS_Store":
            continue
        out.append(str(p.relative_to(root)))
    return out


def run_diff(source: Path, dest: Path, transport: str) -> dict:
    rels = discover_files(source)
    files = [compare_file(rel, source / rel, dest / rel) for rel in rels]

    keyed_files = [f for f in files if f["keys"]]
    per_key: "OrderedDict[str, dict]" = OrderedDict()
    for f in keyed_files:
        for key, info in f["keys"].items():
            agg = per_key.setdefault(key, {"preserved": 0, "normalised": 0, "lost": 0, "notes": set()})
            agg[info["status"]] += 1
            if info["note"]:
                for token in info["note"].split("; "):
                    agg["notes"].add(token)

    order = {"lost": 0, "normalised": 1, "preserved": 2}
    per_key_overall = OrderedDict()
    for key, agg in per_key.items():
        overall = min((s for s in ("lost", "normalised", "preserved") if agg[s] > 0), key=lambda s: order[s])
        per_key_overall[key] = {
            "overall": overall,
            "preserved": agg["preserved"],
            "normalised": agg["normalised"],
            "lost": agg["lost"],
            "notes": sorted(agg["notes"]),
        }

    n_files = len(files)
    n_byte_identical = sum(1 for f in files if f["byte_identical"])

    return {
        "transport": transport,
        "n_files": n_files,
        "n_byte_identical": n_byte_identical,
        "files": files,
        "per_key": per_key_overall,
    }


def render_markdown(result: dict) -> str:
    lines = [f"### Transport: {result['transport']}", ""]
    lines.append(f"Files compared: **{result['n_files']}**. Byte-identical: **{result['n_byte_identical']}/{result['n_files']}**.")
    lines.append("")
    if not result["per_key"]:
        lines.append("_No frontmatter files found to compare._")
        return "\n".join(lines)
    lines.append("| Key | Status | preserved/normalised/lost (files) | Notes |")
    lines.append("|---|---|---|---|")
    for key, agg in result["per_key"].items():
        counts = f"{agg['preserved']}/{agg['normalised']}/{agg['lost']}"
        notes = "; ".join(agg["notes"]) if agg["notes"] else ""
        lines.append(f"| `{key}` | {agg['overall']} | {counts} | {notes} |")
    not_byte_identical = [f["rel"] for f in result["files"] if not f["byte_identical"]]
    if not_byte_identical:
        lines.append("")
        lines.append(f"Files NOT byte-identical: {', '.join(not_byte_identical)}")
    return "\n".join(lines)


def cmd_diff(args):
    source = Path(args.source).resolve()
    dest = Path(args.dest).resolve()
    result = run_diff(source, dest, args.transport)
    print(render_markdown(result))
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(result, indent=2, default=str))


def cmd_summary(args):
    results = [json.loads(Path(p).read_text()) for p in args.json_files]
    print("| Transport | Keys preserved | Keys normalised | Keys lost | Files byte-identical |")
    print("|---|---|---|---|---|")
    for r in results:
        pk = r["per_key"]
        p = sum(1 for a in pk.values() if a["overall"] == "preserved")
        n = sum(1 for a in pk.values() if a["overall"] == "normalised")
        l = sum(1 for a in pk.values() if a["overall"] == "lost")
        ident = "yes" if r["n_byte_identical"] == r["n_files"] else f"no ({r['n_byte_identical']}/{r['n_files']})"
        print(f"| {r['transport']} | {p} | {n} | {l} | {ident} |")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("diff", help="compare two bundle directories")
    d.add_argument("source")
    d.add_argument("dest")
    d.add_argument("--transport", default="unknown")
    d.add_argument("--json-out")
    d.set_defaults(func=cmd_diff)

    s = sub.add_parser("summary", help="render the transport-summary table from diff JSON files")
    s.add_argument("json_files", nargs="+")
    s.set_defaults(func=cmd_summary)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
